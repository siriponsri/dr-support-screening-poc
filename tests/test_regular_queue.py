"""Review-app queue client and daily batch runner. Offline: mock transports and fakes only."""

import hashlib
import json

from fastapi import HTTPException
import httpx
import pytest

from dr_support.services.regular_batch import BatchRunner, BatchStore
from dr_support.services.regular_queue import PAIR_KEY, WORDING, RegularGate, RegularQueueError, RegularTransport

TOKEN = "t" * 40
SHA_A = hashlib.sha256(b"a").hexdigest()
SHA_B = hashlib.sha256(b"b").hexdigest()


class FakeHost:
    """The control service's /v1/regular API plus a model route that records what it received."""

    def __init__(self):
        self.status = {"ai_open": True, "invocations_available": 10, "quarantined": False, "revoked": False,
                       "model_server": "READY", "model_epoch": "rs_new", "own_open_tickets": [], "queued": 0,
                       "running": 0}
        self.tickets, self.states, self.model_calls, self.cancelled = {}, [], [], []
        self.sequence = ["QUEUED", "READY"]

    def __call__(self, request):
        path = request.url.path
        if path.startswith("/v1/regular"):
            assert request.headers["authorization"] == "Bearer " + TOKEN
        if path == "/v1/regular/status":
            return httpx.Response(200, json=self.status)
        if path == "/v1/regular/warm":
            self.states.append("WARM")
            return httpx.Response(200, json={"model_server": "STARTING"})
        if path == "/v1/regular/tickets":
            body = json.loads(request.content)
            ticket_id = "tkt_" + "1" * 32
            self.tickets[ticket_id] = {**body, "ticket_id": ticket_id, "state": self.sequence[0], "last_reason": None}
            return httpx.Response(200, json=self.tickets[ticket_id])
        if path.endswith("/cancel"):
            ticket_id = path.split("/")[-2]
            self.cancelled.append(ticket_id)
            return httpx.Response(200, json={**self.tickets[ticket_id], "state": "CANCELLED"})
        if path.startswith("/v1/regular/tickets/"):
            ticket = self.tickets[path.split("/")[-1]]
            ticket["state"] = self.sequence[min(len(self.sequence) - 1, self.sequence.index(ticket["state"]) + 1)] \
                if ticket["state"] in self.sequence else ticket["state"]
            return httpx.Response(200, json=ticket)
        self.model_calls.append((path, dict(request.headers)))
        return httpx.Response(200, json={"ok": True})


def gate_for(host, **options):
    transport = httpx.MockTransport(host)
    return RegularGate("http://control", TOKEN, "ws-a", transport=transport, sleep=lambda _: None,
                       **options), transport


def test_a_grading_call_is_sent_only_with_a_ready_ticket_and_the_image_pair_key():
    host = FakeHost()
    gate, inner = gate_for(host)
    client = httpx.Client(transport=RegularTransport(gate, inner), base_url="http://control")
    PAIR_KEY.set(SHA_B)
    client.post("/v1/predict/dr", json={"model_id": "retfound-aptos5", "modality": "CFP", "image_sha256": SHA_A})
    path, headers = host.model_calls[0]
    ticket = next(iter(host.tickets.values()))
    assert headers["x-dr-ticket"] == ticket["ticket_id"] and headers["x-dr-workstation"] == "ws-a"
    assert ticket["source_sha256"] == SHA_A and ticket["pair_key"] == SHA_B and ticket["kind"] == "grader"


@pytest.mark.parametrize("change, code", [({"ai_open": False}, "OUTSIDE_AI_HOURS"),
                                          ({"invocations_available": 0}, "DAILY_INVOCATIONS_EXHAUSTED"),
                                          ({"quarantined": True}, "AUTHORITY_QUARANTINED_RECONCILE_FIRST")])
def test_closed_hours_spent_limit_or_quarantine_refuse_before_any_ticket_or_model_call(change, code):
    host = FakeHost()
    host.status.update(change)
    gate, inner = gate_for(host)
    client = httpx.Client(transport=RegularTransport(gate, inner), base_url="http://control")
    with pytest.raises(RegularQueueError) as raised:
        client.post("/v1/predict/dr", json={"model_id": "retfound-aptos5", "modality": "CFP", "image_sha256": SHA_A})
    assert raised.value.code == code and raised.value.message == WORDING[code]
    assert host.tickets == {} and host.model_calls == []
    assert "Nothing was sent" in raised.value.message


def test_a_queue_wait_past_its_bound_cancels_the_ticket_and_sends_nothing():
    host = FakeHost()
    host.sequence = ["QUEUED"]
    clock = iter(range(0, 10_000, 50))
    gate, inner = gate_for(host, clock=lambda: next(clock), ready_wait_seconds=120)
    with pytest.raises(RegularQueueError) as raised:
        gate.acquire(kind="grader", model_id="retfound-aptos5", modality="CFP", source_sha256=SHA_A, pair_key=None)
    assert raised.value.code == "QUEUE_WAIT_TIMEOUT" and host.cancelled == ["tkt_" + "1" * 32]
    assert host.model_calls == []


def test_prism_preparation_while_the_server_is_stopped_asks_it_to_start_and_says_try_again():
    host = FakeHost()
    host.status["model_server"] = "STOPPED"
    gate, inner = gate_for(host)
    reply = RegularTransport(gate, inner).handle_request(httpx.Request("POST", "http://control/v1/prism-bound/prepare"))
    assert reply.status_code == 503 and reply.json() == {"error": "PREPARE_UNAVAILABLE"}
    assert host.states == ["WARM"] and host.model_calls == []


def test_prism_preparation_on_a_new_child_renegotiates_and_uses_the_live_epoch():
    host = FakeHost()
    gate, inner = gate_for(host)
    calls = []
    gate.renegotiate = lambda: calls.append("negotiate")
    request = httpx.Request("POST", "http://control/v1/prism-bound/prepare", headers={"X-Prism-Epoch": "rs_old"})
    RegularTransport(gate, inner).handle_request(request)
    assert calls == ["negotiate"] and host.model_calls[0][1]["x-prism-epoch"] == "rs_new"


def test_a_prism_execute_gets_a_prism_ticket_for_its_bound_source():
    host = FakeHost()
    gate, inner = gate_for(host)
    body = {"ticket_id": "host-ticket", "plan_sha256": SHA_B,
            "binding": {"model_id": "prism-dr-5fold", "modality": "UWF", "source_sha256": SHA_A}}
    RegularTransport(gate, inner).handle_request(httpx.Request("POST", "http://control/v1/prism-bound/execute",
                                                               json=body))
    ticket = next(iter(host.tickets.values()))
    assert ticket["kind"] == "prism" and ticket["pair_key"] == SHA_A and host.model_calls[0][1]["x-dr-ticket"]


def test_public_status_has_plain_fields_only():
    host = FakeHost()
    host.status["own_open_tickets"] = [{"ticket_id": "tkt_x", "state": "QUEUED"}]
    gate, _ = gate_for(host)
    value = gate.public_status()
    assert value["own_waiting"] == 1 and "own_open_tickets" not in value and "model_epoch" not in value


# ---------------------------------------------------------------- batch runner

class FakeApp:
    def __init__(self):
        self.stages = {"img1": ("retfound-aptos5", "CFP"), "img2": ("uspec-uwf-grading", "UWF"), "img3": None}
        self.saved = {("img0", "global")}
        self.calls, self.fail = [], {}
        self.open = True

    def has_result(self, image_id, task):
        return (image_id, task) in self.saved

    def run_grader(self, image_id, model_id, modality, invocation_id):
        self.calls.append((image_id, model_id, modality, invocation_id))
        if image_id in self.fail:
            raise HTTPException(*self.fail.pop(image_id))
        self.saved.add((image_id, "global"))


def runner_for(tmp_path, app):
    return BatchRunner(BatchStore(tmp_path), workspace_id="ws_1", stage_for=app.stages.get,
                       has_result=app.has_result, run_grader=app.run_grader, queue_open=lambda: app.open,
                       deferred_details=set(WORDING.values()))


def test_a_batch_runs_each_confirmed_image_once_and_skips_saved_or_unconfirmed(tmp_path):
    app = FakeApp()
    runner = runner_for(tmp_path, app)
    batch = runner.create(["img0", "img1", "img2", "img3", "img1"])
    assert batch["total"] == 4 and batch["counts"] == {"SAVED": 1, "PENDING": 2, "NEEDS_CONFIRM_IMAGE": 1,
                                                       "PRISM_SAVED": 0}
    while runner.step():
        pass
    summary = runner.list()[0]
    assert [call[0] for call in app.calls] == ["img1", "img2"] and summary["counts"]["SAVED"] == 3
    assert summary["active"] is False
    assert all(row["prism"] == "WAITING_FOR_REVIEW" for row in summary["items"])


def test_a_refusal_before_sending_waits_but_any_other_failure_needs_action_without_resend(tmp_path):
    from dr_support.services.regular_batch import BatchDeferred
    app = FakeApp()
    runner = runner_for(tmp_path, app)
    runner.create(["img1", "img2"])
    app.fail["img1"] = (503, WORDING["OUTSIDE_AI_HOURS"])
    with pytest.raises(BatchDeferred):
        runner.step()
    assert runner.list()[0]["counts"]["PENDING"] == 2
    app.fail["img1"] = (504, "The model server did not reply in time.")
    runner.step()
    runner.step()
    rows = {row["image_id"]: row for row in runner.list()[0]["items"]}
    assert rows["img1"]["grader"] == "NEEDS_ACTION" and rows["img2"]["grader"] == "SAVED"
    assert [call[0] for call in app.calls] == ["img1", "img1", "img2"]
    assert not runner.step()  # img1 is never resent automatically.


def test_closed_queue_defers_without_calling_the_model(tmp_path):
    from dr_support.services.regular_batch import BatchDeferred
    app = FakeApp()
    app.open = False
    runner = runner_for(tmp_path, app)
    runner.create(["img1"])
    with pytest.raises(BatchDeferred):
        runner.step()
    assert app.calls == [] and runner.list()[0]["note"]


def test_a_stage_interrupted_while_running_is_never_resent_after_restart(tmp_path):
    app = FakeApp()
    runner = runner_for(tmp_path, app)
    batch = runner.create(["img1"])
    stored = runner.store.load(batch["batch_id"])
    stored["items"]["img1"]["grader"]["state"] = "RUNNING"
    runner.store.save(stored)
    restarted = runner_for(tmp_path, app)
    assert restarted.list()[0]["items"][0]["grader"] == "NEEDS_ACTION" and not restarted.step()
    assert app.calls == []


def test_cancel_stops_waiting_images_only(tmp_path):
    app = FakeApp()
    runner = runner_for(tmp_path, app)
    batch = runner.create(["img0", "img1", "img2"])
    runner.step()
    summary = runner.cancel(batch["batch_id"])
    assert summary["counts"]["CANCELLED"] == 1 and summary["counts"]["SAVED"] == 2 and not runner.step()


# ---------------------------------------------------------------- review-app routes

def test_regular_routes_create_run_and_report_a_batch_through_the_existing_infer(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from dr_support.api import _factory
    monkeypatch.setenv("DR_SUPPORT_REGULAR_BATCH_DIR", str(tmp_path))
    app = FastAPI()
    admitted = {"modality_admission": "FUNDUS_ACCEPTED", "quality_state": "GRADABLE", "source_origin": "SYNTHETIC"}
    app.state.admissions = {"cfp1": {**admitted, "retinal_modality": "CFP"},
                            "uwf1": {**admitted, "retinal_modality": "UWF"},
                            "new1": {**admitted, "modality_admission": "NEEDS_REVIEW", "retinal_modality": "UNKNOWN"}}
    app.state.providers = {"retfound-aptos5": object(), "uspec-uwf-grading": object()}
    cases = {image_id: {"inference_history": []} for image_id in app.state.admissions}
    app.state.store = SimpleNamespace(get=cases.__getitem__)
    calls = []

    def infer(request, task, *, invocation_id=None):
        calls.append((request.image_id, request.model_id, task, invocation_id))
        cases[request.image_id]["inference_history"].append(
            {"task": task, "model_id": request.model_id, "result": {"grade": 0}})

    gate = SimpleNamespace(public_status=lambda: {"ai_open": True, "invocations_available": 5, "quarantined": False,
                                                  "model_server": "READY"})
    _factory.install_regular_routes(app, gate, infer, "ws_1")
    client = TestClient(app)
    assert client.get("/v1/regular/status").json()["model_server"] == "READY"
    created = client.post("/v1/batches", json={"all_ready": True}).json()
    assert created["total"] == 2 and created["counts"]["PENDING"] == 2
    while app.state.regular_batches.step():
        pass
    listed = client.get("/v1/batches").json()["batches"][0]
    assert listed["counts"]["SAVED"] == 2
    assert sorted(call[1] for call in calls) == ["retfound-aptos5", "uspec-uwf-grading"]
    assert all(call[2] == "global" and call[3].startswith("regular-batch_") for call in calls)
    assert client.post("/v1/batches", json={"all_ready": True}).status_code == 409
    assert client.post("/v1/batches/batch_0000000000000000/cancel").status_code == 404


# ---------------------------------------------------------------- launcher

def test_the_regular_launcher_refuses_before_any_ssh_or_token_read(monkeypatch):
    from types import SimpleNamespace

    from scripts.qa import m1_server_app as launcher
    monkeypatch.setattr(launcher, "ssh", lambda *a, **k: pytest.fail("no SSH before opt-in"))
    args = SimpleNamespace(allow_remote_token_read=False, model_port=47860, workstation="ws-a")
    with pytest.raises(launcher.SessionError, match="REMOTE_TOKEN_READ_REQUIRES_EXPLICIT_OPT_IN"):
        launcher.serve_regular(args)
    args = SimpleNamespace(allow_remote_token_read=True, model_port=47860, workstation="bad name/../x")
    with pytest.raises(launcher.SessionError, match="SIMPLE_WORKSTATION_ID_REQUIRED"):
        launcher.serve_regular(args)


def test_the_launcher_waits_for_the_model_server_only_inside_ai_hours():
    from types import SimpleNamespace

    from scripts.qa import m1_server_app as launcher
    states = iter(["STOPPED", "STARTING", "READY"])
    warmed = []
    gate = SimpleNamespace(status=lambda: {"ai_open": True, "model_server": next(states), "quarantined": False},
                           warm=lambda: warmed.append(1))
    assert launcher.wait_for_model_server(gate, sleep=lambda _: None)["model_server"] == "READY"
    assert len(warmed) == 2
    closed = SimpleNamespace(status=lambda: {"ai_open": False, "model_server": "STOPPED"}, warm=lambda: None)
    with pytest.raises(launcher.SessionError, match="OUTSIDE_AI_HOURS"):
        launcher.wait_for_model_server(closed, sleep=lambda _: None)
