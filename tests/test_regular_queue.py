"""Review-app queue client and daily batch runner. Offline: mock transports and fakes only."""

import hashlib
import json

from fastapi import HTTPException
import httpx
import pytest

from dr_support.services.regular_batch import BatchDeferred, BatchRunner, BatchStore, PrismPrepareRefused
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


def test_a_gateway_refusal_before_dispatch_is_a_not_sent_queue_refusal():
    host = FakeHost()
    original = host.__call__

    def busy(request):
        if request.url.path == "/v1/predict/dr":
            return httpx.Response(503, json={"code": "QUEUE_BUSY_NOT_SENT", "detail": "busy"})
        return original(request)
    gate, _ = gate_for(host)
    transport = RegularTransport(gate, httpx.MockTransport(busy))
    client = httpx.Client(transport=transport, base_url="http://control")
    with pytest.raises(RegularQueueError) as raised:
        client.post("/v1/predict/dr", json={"model_id": "retfound-aptos5", "modality": "CFP", "image_sha256": SHA_A})
    assert raised.value.code == "QUEUE_BUSY_NOT_SENT" and "Nothing was sent" in raised.value.message


def test_public_status_has_plain_fields_only():
    host = FakeHost()
    host.status["own_open_tickets"] = [{"ticket_id": "tkt_x", "state": "QUEUED"}]
    gate, _ = gate_for(host)
    value = gate.public_status()
    assert value["own_waiting"] == 1 and "own_open_tickets" not in value and "model_epoch" not in value


# ---------------------------------------------------------------- batch runner (two stages)

class FakeApp:
    def __init__(self):
        self.stages = {"img1": ("retfound-aptos5", "CFP"), "img2": ("uspec-uwf-grading", "UWF"), "img3": None}
        self.saved = {("img0", "global"), ("img0", "lesion-roi")}
        self.calls, self.fail, self.prism_fail = [], {}, {}
        self.open = True

    def has_result(self, image_id, task):
        return (image_id, task) in self.saved

    def run_grader(self, image_id, model_id, modality, invocation_id):
        self.calls.append(("grader", image_id, model_id))
        if image_id in self.fail:
            raise HTTPException(*self.fail.pop(image_id))
        self.saved.add((image_id, "global"))

    def run_prism(self, image_id):
        self.calls.append(("prism", image_id))
        if image_id in self.prism_fail:
            raise self.prism_fail.pop(image_id)
        self.saved.add((image_id, "lesion-roi"))


def runner_for(tmp_path, app):
    return BatchRunner(BatchStore(tmp_path), workspace_id="ws_1", stage_for=app.stages.get,
                       has_result=app.has_result, run_grader=app.run_grader, run_prism=app.run_prism,
                       queue_open=lambda: app.open, deferred_details=set(WORDING.values()))


def drain(runner):
    while True:
        try:
            if not runner.step():
                return
        except BatchDeferred:
            return


def test_every_confirmed_image_gets_its_grader_then_prism_and_is_complete_only_with_both(tmp_path):
    app = FakeApp()
    runner = runner_for(tmp_path, app)
    batch = runner.create(["img0", "img1", "img2", "img3", "img1"])
    assert batch["total"] == 4 and batch["complete"] == 1
    assert batch["counts"]["grader"] == {"SAVED": 1, "PENDING": 2, "NEEDS_CONFIRM_IMAGE": 1}
    drain(runner)
    summary = runner.list()[0]
    assert app.calls == [("grader", "img1", "retfound-aptos5"), ("prism", "img1"),
                         ("grader", "img2", "uspec-uwf-grading"), ("prism", "img2")]
    assert summary["complete"] == 3 and summary["active"] is False
    rows = {row["image_id"]: row for row in summary["items"]}
    assert rows["img3"]["complete"] is False and rows["img3"]["prism"] == "NEEDS_CONFIRM_IMAGE"


def test_a_prism_precondition_failure_is_shown_with_its_reason_and_is_not_complete(tmp_path):
    app = FakeApp()
    app.prism_fail["img1"] = PrismPrepareRefused(409, "Source/admission is not eligible for PRISM.")
    runner = runner_for(tmp_path, app)
    runner.create(["img1"])
    drain(runner)
    row = runner.list()[0]["items"][0]
    assert row["grader"] == "SAVED" and row["prism"] == "NOT_ELIGIBLE" and row["complete"] is False
    assert row["prism_detail"] == "Source/admission is not eligible for PRISM." and row["prism_label"] == "PRISM not run"


def test_prism_preparation_while_the_server_loads_waits_without_sending(tmp_path):
    app = FakeApp()
    app.prism_fail["img1"] = PrismPrepareRefused(503, "PRISM is not available right now. Try again shortly.")
    runner = runner_for(tmp_path, app)
    runner.create(["img1"])
    drain(runner)
    assert runner.list()[0]["items"][0]["prism"] == "PENDING"
    drain(runner)
    assert runner.list()[0]["items"][0]["prism"] == "SAVED"


def test_an_unknown_prism_outcome_needs_action_and_is_never_resent(tmp_path):
    app = FakeApp()
    unknown = HTTPException(502, "The PRISM result could not be confirmed and nothing was saved. Do not resend "
                                 "this image; the operator can check what happened. Manual review remains available.")
    app.prism_fail["img1"] = unknown
    runner = runner_for(tmp_path, app)
    runner.create(["img1"])
    drain(runner)
    row = runner.list()[0]["items"][0]
    assert row["prism"] == "NEEDS_ACTION" and "Do not resend" in row["prism_detail"]
    assert [call for call in app.calls if call[0] == "prism"] == [("prism", "img1")]


def test_a_refusal_before_sending_waits_but_any_other_failure_needs_action_without_resend(tmp_path):
    app = FakeApp()
    runner = runner_for(tmp_path, app)
    runner.create(["img1", "img2"])
    app.fail["img1"] = (503, WORDING["OUTSIDE_AI_HOURS"])
    with pytest.raises(BatchDeferred):
        runner.step()
    assert runner.list()[0]["counts"]["grader"]["PENDING"] == 2
    app.fail["img1"] = (504, "The model server did not reply in time.")
    drain(runner)
    rows = {row["image_id"]: row for row in runner.list()[0]["items"]}
    assert rows["img1"]["grader"] == "NEEDS_ACTION" and rows["img1"]["prism"] == "SAVED"
    assert rows["img2"]["complete"] is True
    assert [call for call in app.calls if call[0] == "grader" and call[1] == "img1"] == \
        [("grader", "img1", "retfound-aptos5")] * 2  # The deferred refusal sent nothing; no resend after 504.


def test_closed_queue_defers_without_calling_the_model(tmp_path):
    app = FakeApp()
    app.open = False
    runner = runner_for(tmp_path, app)
    runner.create(["img1"])
    with pytest.raises(BatchDeferred):
        runner.step()
    assert app.calls == [] and runner.list()[0]["note"]


def test_type_or_rights_withdrawn_mid_batch_stops_the_next_stage(tmp_path):
    app = FakeApp()
    runner = runner_for(tmp_path, app)
    runner.create(["img1"])
    runner.step()                 # Grader saved.
    app.stages["img1"] = None     # Source rights or type withdrawn before PRISM.
    runner.step()
    row = runner.list()[0]["items"][0]
    assert row["prism"] == "NEEDS_CONFIRM_IMAGE" and row["complete"] is False
    assert ("prism", "img1") not in app.calls


def test_a_stage_interrupted_while_running_is_never_resent_after_restart(tmp_path):
    app = FakeApp()
    runner = runner_for(tmp_path, app)
    batch = runner.create(["img1"])
    stored = runner.store.load(batch["batch_id"])
    stored["items"]["img1"]["grader"]["state"] = "RUNNING"
    runner.store.save(stored)
    restarted = runner_for(tmp_path, app)
    row = restarted.list()[0]["items"][0]
    assert row["grader"] == "NEEDS_ACTION"
    drain(restarted)
    assert ("grader", "img1", "retfound-aptos5") not in app.calls  # PRISM may still run; the grader is not resent.


def test_cancel_stops_waiting_stages_only(tmp_path):
    app = FakeApp()
    runner = runner_for(tmp_path, app)
    batch = runner.create(["img0", "img1", "img2"])
    runner.step()
    summary = runner.cancel(batch["batch_id"])
    assert summary["counts"]["grader"] == {"SAVED": 2, "CANCELLED": 1}
    assert summary["counts"]["prism"]["CANCELLED"] == 2 and not runner.step()


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
    cases = {image_id: {"revision": 3, "inference_history": []} for image_id in app.state.admissions}
    app.state.store = SimpleNamespace(get=cases.__getitem__)
    calls = []

    class Preview:
        def prepare(self, image_id, revision):
            calls.append((image_id, "prism-dr-5fold", "prepare", revision))
            return {"plan_id": "p" * 48, "source_sha256": SHA_A, "wire_sha256": SHA_B, "plan_sha256": SHA_A,
                    "mask": {"sha256": None}, "transform": {"sha256": SHA_B}, "model_version": "r2"}

        def submit(self, image_id, token, request):
            assert token == "p" * 48 and request.revision == 3 and request.plan_sha256 == SHA_A
            calls.append((image_id, "prism-dr-5fold", "lesion-roi", None))
            cases[image_id]["inference_history"].append(
                {"task": "lesion-roi", "model_id": "prism-dr-5fold", "result": {"detections": []}})
    app.state.prism_preview = Preview()

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
    assert created["total"] == 2 and created["counts"]["grader"]["PENDING"] == 2
    while app.state.regular_batches.step():
        pass
    listed = client.get("/v1/batches").json()["batches"][0]
    assert listed["complete"] == 2 and listed["counts"]["prism"] == {"SAVED": 2}
    graders = [call for call in calls if call[2] == "global"]
    assert sorted(call[1] for call in graders) == ["retfound-aptos5", "uspec-uwf-grading"]
    assert all(call[3].startswith("regular-batch_") for call in graders)
    assert [call[2] for call in calls if call[0] == "cfp1"] == ["global", "prepare", "lesion-roi"]
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
