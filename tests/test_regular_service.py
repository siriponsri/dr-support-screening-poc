"""Regular-service gateway, admission binding and GPU lifecycle with a fake child. Offline only."""

import asyncio
import base64
from datetime import timedelta
import hashlib
import importlib
import json
from pathlib import Path
import sys

import httpx
import pytest

from test_regular_authority import LINEAGE, FakeClock, bangkok

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/model-server"))
ra = importlib.import_module("regular_authority")
rs = importlib.import_module("regular_service")
ops = importlib.import_module("m1_operations")

TOKEN = "t" * 40
AUTH = {"Authorization": "Bearer " + TOKEN}
PIN = {"source_revision": "r1", "checkpoint_sha256": {"w": "a" * 64}, "preprocessing": "p1",
       "provider_source_sha256": "b" * 64}
MODELS = {"retfound-aptos5": {"pins": {**PIN, "model_id": "retfound-aptos5"}, "capability_id": "global_dr"},
          "uspec-uwf-grading": {"pins": {**PIN, "model_id": "uspec-uwf-grading"}, "capability_id": "global_dr"},
          "prism-dr-5fold": {"pins": {"model_id": "prism-dr-5fold", "source_revision": "r2", "preprocessing": "p2",
                                      "config_sha256": "c" * 64, "checkpoint_sha256": {"f": "d" * 64}},
                             "capability_id": "core_lesion_localization"}}
IMAGE = b"synthetic image bytes"
IMAGE_SHA = hashlib.sha256(IMAGE).hexdigest()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class FakeChild:
    """Writes the same receipts as m1_session.ChildAdmission and dispatches only after admission."""

    def __init__(self, root, fake):
        self.root, self.fake = root, fake
        self.state, self.run, self.pid = "STOPPED", None, 4242
        self.starts, self.stops, self.forwarded = [], [], []
        self.jobs_done, self.busy, self.mode, self.sequence = 0, None, "ok", 0
        self.stop_record = self._failed = self.preflight_refusal = None
        self.docs = {"/health": {"status": "PASS", "assets_verified": True, "warnings": ["w"]},
                     "/v1/models": [{"model_id": "retfound-aptos5", "ready": True}]}

    def age(self):
        return 0

    def jobs(self):
        return self.jobs_done

    def failed_reason(self):
        return self._failed

    def preflight(self):
        return self.preflight_refusal

    def can_admit(self):
        return self.state == "READY" and self.busy is None

    def admit(self, intent_id):
        self.busy, self.jobs_done = intent_id, self.jobs_done + 1

    def finish(self, intent_id, *, success):
        self.busy = None

    def start(self, epoch):
        self.run = self.root / epoch
        self.run.mkdir()
        self.state = "STARTING"
        self.starts.append(epoch)

    def tick(self):
        if self.state == "STARTING":
            self.state = "READY"

    def stop(self, reason):
        self.stops.append(reason)
        self.state = "STOPPED"
        self.stop_record = {"cleanup_confirmed": self.mode != "dirty_stop", "end_utc": self.fake.now.isoformat()}

    def take_stop_record(self):
        record, self.stop_record = self.stop_record, None
        return record

    async def forward(self, method, path, headers, body):
        if method == "GET":
            return 200, b"application/json", json.dumps(self.docs[path]).encode()
        payload = json.loads(body)
        if path == rs.PRISM_EXECUTE:
            binding = payload["binding"]
            facts = ops.facts(MODELS, source_sha256=binding["source_sha256"], model_id=binding["model_id"],
                              modality=binding["modality"])
        else:
            facts = ops.facts(MODELS, source_sha256=payload["image_sha256"], model_id=payload["model_id"],
                              modality=payload["modality"])
        self.sequence += 1
        request_id = f"m1_{self.sequence:04d}_{sha(body)[:16]}"
        rs.new_json(self.run / f"{request_id}.request.json", {"request_id": request_id, "pid": self.pid,
                                                              "request_sha256": sha(body), "facts": facts,
                                                              "correlation": {}})
        for _ in range(2000):
            if (self.run / f"{request_id}.refused.json").is_file():
                code = json.loads((self.run / f"{request_id}.refused.json").read_bytes())["code"]
                return 409, b"application/json", json.dumps({"code": code}).encode()
            if (self.run / f"{request_id}.admitted.json").is_file():
                break
            await asyncio.sleep(.002)
        else:
            raise AssertionError("no admission receipt")
        self.forwarded.append(request_id)
        if self.mode == "uncertain":
            rs.new_json(self.run / f"{request_id}.uncertain.json", {"request_id": request_id, "pid": self.pid})
            return 504, b"application/json", b'{"detail":"timeout"}'
        success = self.mode != "fail"
        if path == rs.PRISM_EXECUTE:
            async def terminal():  # PRISM finishes at its job's terminal state, after the 202.
                await asyncio.sleep(.05)
                rs.new_json(self.run / f"{request_id}.finished.json", {
                    "request_id": request_id, "pid": self.pid, "success": True, "response_sha256": "e" * 64,
                    "result_sha256": None})
            self.task = asyncio.get_running_loop().create_task(terminal())
            return 202, b"application/json", b'{"job_id":"job_12345678"}'
        rs.new_json(self.run / f"{request_id}.finished.json", {"request_id": request_id, "pid": self.pid,
                                                               "success": success, "response_sha256": "e" * 64,
                                                               "result_sha256": None})
        return (200, b"application/json", b'{"grade":1}') if success else (500, b"application/json", b"{}")


@pytest.fixture
def rig(tmp_path):
    fake = FakeClock(bangkok("2026-11-02", "09:00"))
    authority = ra.Authority(tmp_path / "authority.sqlite3", config=ra.ServiceConfig(), clock=fake.clock(),
                             lineage=LINEAGE)
    child = FakeChild(tmp_path, fake)
    service = rs.ControlService(authority, child, token=TOKEN, models=MODELS, operations=ops,
                                discovery_path=tmp_path / "discovery.json", monotonic=lambda: fake.mono)
    return fake, authority, child, service


def run(coroutine):
    return asyncio.run(coroutine)


def ticket_body(key="k1", source=IMAGE_SHA, model="retfound-aptos5", modality="CFP", kind="grader"):
    return {"idempotency_key": key, "request_digest": sha(key.encode()), "kind": kind, "model_id": model,
            "modality": modality, "source_sha256": source, "pair_key": IMAGE_SHA}


def predict_body(image=IMAGE):
    return {"model_id": "retfound-aptos5", "modality": "CFP", "image_sha256": sha(image),
            "image_b64": base64.b64encode(image).decode()}


async def client_for(service):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=service), base_url="http://control")


def headers(workstation="ws-a", ticket=None):
    value = {**AUTH, "X-DR-Workstation": workstation}
    if ticket:
        value["X-DR-Ticket"] = ticket
    return value


async def scheduled_ticket(service, client, key="k1", workstation="ws-a", **body):
    created = (await client.post("/v1/regular/tickets", json=ticket_body(key, **body),
                                 headers=headers(workstation))).json()
    service.step()   # Funds a segment and starts the child.
    service.step()   # Child READY: promote fairly.
    service.step()
    return created["ticket_id"]


def test_every_route_requires_the_backend_token(rig):
    _, _, _, service = rig

    async def scenario():
        async with await client_for(service) as client:
            assert (await client.get("/v1/regular/status", headers={"X-DR-Workstation": "ws-a"})).status_code == 401
            assert (await client.post("/v1/predict/dr", json=predict_body())).status_code == 401
    run(scenario())


def test_a_scheduled_grader_call_is_charged_once_before_dispatch_and_finishes_done(rig):
    _, authority, child, service = rig

    async def scenario():
        async with await client_for(service) as client:
            ticket = await scheduled_ticket(service, client)
            assert child.starts and authority.capacity()["gpu_seconds_reserved"] == 300
            assert (await client.get(f"/v1/regular/tickets/{ticket}", headers=headers())).json()["state"] == "READY"
            reply = await client.post("/v1/predict/dr", json=predict_body(), headers=headers(ticket=ticket))
            assert reply.status_code == 200 and reply.json() == {"grade": 1}
            assert authority.get(ticket, principal=rs.PRINCIPAL)["state"] == "DONE"
            assert authority.capacity()["invocations_used"] == 1 and len(child.forwarded) == 1
    run(scenario())


def test_a_model_call_without_a_scheduled_ticket_never_reaches_the_child(rig):
    _, authority, child, service = rig

    async def scenario():
        async with await client_for(service) as client:
            await scheduled_ticket(service, client)
            reply = await client.post("/v1/predict/dr", json=predict_body(), headers=headers())
            assert reply.status_code == 409 and reply.json()["code"] == "REGULAR_TICKET_REQUIRED"
            assert child.sequence == 0 and authority.capacity()["invocations_used"] == 0
    run(scenario())


def test_a_call_for_another_image_is_refused_before_admission_and_gives_back_its_slots(rig):
    _, authority, child, service = rig

    async def scenario():
        async with await client_for(service) as client:
            ticket = await scheduled_ticket(service, client)
            reply = await client.post("/v1/predict/dr", json=predict_body(b"another image"),
                                      headers=headers(ticket=ticket))
            assert reply.status_code == 409 and reply.json()["code"] == "REQUEST_DOES_NOT_MATCH_TICKET"
            assert child.forwarded == [] and authority.get(ticket, principal=rs.PRINCIPAL)["state"] == "EXPIRED"
            assert authority.capacity()["invocations_used"] == 0 and authority.capacity()["invocations_held"] == 0
    run(scenario())


def test_another_workstation_cannot_see_use_or_cancel_a_ticket(rig):
    _, authority, child, service = rig

    async def scenario():
        async with await client_for(service) as client:
            ticket = await scheduled_ticket(service, client)
            assert (await client.get(f"/v1/regular/tickets/{ticket}", headers=headers("ws-b"))).status_code == 409
            assert (await client.post(f"/v1/regular/tickets/{ticket}/cancel", headers=headers("ws-b"))).status_code == 409
            reply = await client.post("/v1/predict/dr", json=predict_body(), headers=headers("ws-b", ticket))
            assert reply.status_code == 409 and child.sequence == 0
            own = (await client.get("/v1/regular/status", headers=headers("ws-b"))).json()["own_open_tickets"]
            assert own == []
    run(scenario())


def test_an_uncertain_outcome_is_charged_unknown_and_quarantines_new_work(rig):
    _, authority, child, service = rig
    child.mode = "uncertain"

    async def scenario():
        async with await client_for(service) as client:
            ticket = await scheduled_ticket(service, client)
            await client.post("/v1/predict/dr", json=predict_body(), headers=headers(ticket=ticket))
            assert authority.get(ticket, principal=rs.PRINCIPAL)["state"] == "UNKNOWN"
            status = (await client.get("/v1/regular/status", headers=headers())).json()
            assert status["quarantined"] is True and status["invocations_used"] == 1
            reply = await client.post("/v1/regular/tickets", json=ticket_body("k2"), headers=headers())
            assert reply.status_code == 409 and "QUARANTINED" in reply.json()["code"]
    run(scenario())


def test_the_child_starts_only_inside_ai_hours_and_stops_after_300_s_idle(tmp_path):
    fake = FakeClock(bangkok("2026-11-02", "05:00"))
    authority = ra.Authority(tmp_path / "a.sqlite3", config=ra.ServiceConfig(), clock=fake.clock(), lineage=LINEAGE)
    child = FakeChild(tmp_path, fake)
    service = rs.ControlService(authority, child, token=TOKEN, models=MODELS, operations=ops,
                                monotonic=lambda: fake.mono)

    async def scenario():
        async with await client_for(service) as client:
            await client.post("/v1/regular/warm", headers=headers())
            service.step()
            assert child.starts == [] and authority.capacity()["gpu_seconds_reserved"] == 0
    run(scenario())
    fake.advance(5 * 3600)  # 10:00, same boot.
    service.warm_until = fake.mono + 300
    service.step()
    service.step()
    assert child.state == "READY" and len(child.starts) == 1
    fake.advance(301)
    service.step()
    assert child.state == "STOPPED" and child.stops == ["IDLE"]
    assert authority.capacity()["gpu_seconds_reserved"] == 300  # Charged in full, never refunded.


def test_continued_work_funds_the_next_contiguous_segment_before_the_current_one_ends(rig):
    fake, authority, child, service = rig

    async def scenario():
        async with await client_for(service) as client:
            await scheduled_ticket(service, client)
            first_end = service.funded_until
            fake.advance(210)  # 90 s left with work still queued.
            service.step()
            assert service.funded_until == first_end + timedelta(seconds=300)
            assert authority.capacity()["gpu_seconds_reserved"] == 600 and child.state == "READY"
    run(scenario())


def test_unconfirmed_child_cleanup_quarantines_gpu_work(rig):
    fake, authority, child, service = rig
    child.mode = "dirty_stop"
    service.warm_until = fake.mono + 300
    service.step()
    service.step()
    fake.advance(301)
    service.step()   # Idle stop; cleanup not confirmed.
    service.step()
    assert authority.status()["quarantined"] is True


def test_discovery_is_served_from_the_last_loaded_child_while_stopped(rig):
    fake, authority, child, service = rig

    async def scenario():
        async with await client_for(service) as client:
            assert (await client.get("/health", headers=AUTH)).status_code == 503
            service.warm_until = fake.mono + 300
            service.step()
            service.step()
            assert (await client.get("/v1/models", headers=AUTH)).status_code == 200
            assert (await client.get("/health", headers=AUTH)).json()["warnings"] == ["w"]
            fake.advance(301)
            service.step()
            assert child.state == "STOPPED"
            health = (await client.get("/health", headers=AUTH)).json()
            assert health["status"] == "PASS" and rs.ON_DEMAND_WARNING in health["warnings"]
            assert (await client.get("/v1/models", headers=AUTH)).json()[0]["model_id"] == "retfound-aptos5"
            prism = await client.get("/v1/prism-bound/capabilities", headers=AUTH)
            assert prism.status_code == 503 and prism.json()["code"] == "MODEL_SERVER_NOT_READY"
    run(scenario())


def test_a_failed_call_is_charged_and_drains_the_child_without_backoff(rig):
    fake, authority, child, service = rig
    child.mode = "fail"

    async def scenario():
        async with await client_for(service) as client:
            ticket = await scheduled_ticket(service, client)
            reply = await client.post("/v1/predict/dr", json=predict_body(), headers=headers(ticket=ticket))
            assert reply.status_code == 500
            assert authority.get(ticket, principal=rs.PRINCIPAL)["state"] == "FAILED"
            assert authority.capacity()["invocations_used"] == 1 and authority.status()["quarantined"] is False
    run(scenario())


def test_the_gateway_never_reads_credentials_from_requests_or_logs_bodies():
    source = (ROOT / "scripts/model-server/regular_service.py").read_text(encoding="utf-8")
    assert "print(body" not in source and "logging" not in source
    assert "REMOTE_MODEL_TOKEN" not in source


def test_a_prism_execute_is_charged_on_the_image_pair_hold_and_finishes_at_its_terminal_state(rig):
    _, authority, child, service = rig

    async def scenario():
        async with await client_for(service) as client:
            grader = await scheduled_ticket(service, client, key="g1")
            await client.post("/v1/predict/dr", json=predict_body(), headers=headers(ticket=grader))
            prism = (await client.post("/v1/regular/tickets", headers=headers(), json=ticket_body(
                "p1", model="prism-dr-5fold", modality="CFP", kind="prism"))).json()["ticket_id"]
            service.step()
            body = {"ticket_id": "host", "plan_sha256": "f" * 64,
                    "binding": {"model_id": "prism-dr-5fold", "modality": "CFP", "source_sha256": IMAGE_SHA}}
            reply = await client.post("/v1/prism-bound/execute", json=body, headers=headers(ticket=prism))
            assert reply.status_code == 202
            assert authority.get(prism, principal=rs.PRINCIPAL)["state"] == "DONE"
            assert authority.get(prism, principal=rs.PRINCIPAL)["hold_id"] ==                 authority.get(grader, principal=rs.PRINCIPAL)["hold_id"]
            assert authority.capacity()["invocations_used"] == 2 and authority.capacity()["invocations_held"] == 0
            wrong = await client.post("/v1/predict/dr", json=predict_body(), headers=headers(ticket=prism))
            assert wrong.status_code == 409
    run(scenario())


def test_a_gateway_restart_settles_open_calls_without_refunds_and_pauses_for_the_operator(rig):
    _, authority, child, service = rig

    async def scenario():
        async with await client_for(service) as client:
            admitted = await scheduled_ticket(service, client, key="a1")
            ticket = authority.get(admitted, principal=rs.PRINCIPAL)
            authority.admit(admitted, principal=rs.PRINCIPAL, workstation="ws-a", model_id="retfound-aptos5",
                            modality="CFP", source_sha256=IMAGE_SHA, request_digest=ticket["request_digest"])
            ready = (await client.post("/v1/regular/tickets", json=ticket_body("b1"), headers=headers("ws-b"))).json()
            authority.schedule()
            assert service.recover_after_restart() == {"unknown": 1, "released": 1}
            assert authority.get(admitted, principal=rs.PRINCIPAL)["state"] == "UNKNOWN"
            assert authority.get(ready["ticket_id"], principal=rs.PRINCIPAL)["state"] == "EXPIRED"
            status = authority.status()
            assert status["quarantined"] is True and status["running"] == 0
            assert authority.capacity()["invocations_used"] == 1 and authority.capacity()["invocations_held"] == 1
    run(scenario())


def test_a_late_receipt_for_a_settled_ticket_never_breaks_the_scheduler(rig):
    _, authority, child, service = rig
    child.mode = "uncertain"

    async def scenario():
        async with await client_for(service) as client:
            ticket = await scheduled_ticket(service, client)
            await client.post("/v1/predict/dr", json=predict_body(), headers=headers(ticket=ticket))
            request_id = next(iter(service.receipts))
            rs.new_json(child.run / f"{request_id}.finished.json", {"request_id": request_id, "pid": child.pid,
                                                                    "success": True, "response_sha256": "e" * 64,
                                                                    "result_sha256": None})
            service.step()   # Must not raise.
            assert authority.get(ticket, principal=rs.PRINCIPAL)["state"] == "UNKNOWN"
    run(scenario())


def test_a_call_that_cannot_get_the_dispatch_slot_in_time_is_released_unsent(rig, monkeypatch):
    _, authority, child, service = rig
    monkeypatch.setattr(rs, "DISPATCH_WAIT_SECONDS", .05)

    async def scenario():
        async with await client_for(service) as client:
            ticket = await scheduled_ticket(service, client)
            await service.dispatch_lock.acquire()   # Another call holds the single slot.
            reply = await client.post("/v1/predict/dr", json=predict_body(), headers=headers(ticket=ticket))
            service.dispatch_lock.release()
            assert reply.status_code == 503 and reply.json()["code"] == "QUEUE_BUSY_NOT_SENT"
            assert child.sequence == 0 and authority.get(ticket, principal=rs.PRINCIPAL)["state"] == "EXPIRED"
            assert authority.capacity()["invocations_held"] == 0
    run(scenario())


def test_a_busy_gpu_or_port_funds_nothing_and_starts_nothing(rig):
    fake, authority, child, service = rig
    child.preflight_refusal = "GPU0_NOT_IDLE_NO_ADOPTION"
    service.warm_until = fake.mono + 300
    service.step()
    assert child.starts == [] and authority.capacity()["gpu_seconds_reserved"] == 0
    assert service.last_reason == "GPU0_NOT_IDLE_NO_ADOPTION"


def test_only_one_call_is_promoted_at_a_time(rig):
    _, authority, child, service = rig

    async def scenario():
        async with await client_for(service) as client:
            for workstation in ("ws-a", "ws-b", "ws-c"):
                await client.post("/v1/regular/tickets", json=ticket_body("k-" + workstation), headers=headers(workstation))
            for _ in range(3):
                service.step()
            assert authority.status()["ready"] == 1 and authority.status()["queued"] == 2
    run(scenario())


def test_the_scheduler_loop_survives_an_unexpected_error_and_pauses_new_work(rig, monkeypatch):
    _, authority, child, service = rig
    calls = []

    def broken():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("disk")
        raise asyncio.CancelledError()
    monkeypatch.setattr(service, "step", broken)

    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await service.loop(period=0)
    run(scenario())
    assert len(calls) == 2 and service.last_reason == "SCHEDULER_ERROR_OSError"
    assert authority.status()["quarantined"] is True


def test_an_idempotency_key_is_never_shared_across_workstations(rig):
    _, authority, child, service = rig

    async def scenario():
        async with await client_for(service) as client:
            await client.post("/v1/regular/tickets", json=ticket_body("same"), headers=headers("ws-a"))
            reply = await client.post("/v1/regular/tickets", json=ticket_body("same"), headers=headers("ws-b"))
            assert reply.status_code == 409 and reply.json()["code"] == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"
    run(scenario())
