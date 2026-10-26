"""AC-11 offline fault injection on the review app's remote grading path.

MockTransport only: no network, model server, GPU or hospital data. Each case
probes successfully, then breaks the predict call (or the probe) and checks the
safety rules: no saved result, no change to the clinician's work, exactly one
predict call (no automatic retry) and no token in the reply. Known wording
defects are recorded as strict expected failures so a fix flips them.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from dr_support.providers.prism_remote_bound import ExplicitHttpChannel
from dr_support.services.prism_remote_transport import TransportError
from test_remote import FIXTURE_IMAGE, _wire_remote_app

TOKEN = "synthetic-remote-secret"
MODELS = [{"model_id": "retfound-aptos5", "task": "global", "modalities": ["CFP"], "status": "LOADED",
           "release_status": "RESEARCH_ONLY"}]
CLINICAL_FIELDS = ("global", "inference_history", "reviewed_grade", "grade_status", "human_annotations",
                   "clinician_review", "lesion")


def failing_predict(failure, calls):
    def handle(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "PASS", "assets_verified": True})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=MODELS)
        calls.append(request.url.path)
        return failure(request)
    return handle


def clinical_state(app):
    case = app.state.store.get(FIXTURE_IMAGE.image_id) or {}
    return {key: case.get(key) for key in CLINICAL_FIELDS}


def analyze(monkeypatch, handler):
    app = _wire_remote_app(monkeypatch, handler, token=TOKEN)
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    client = TestClient(app)
    before = clinical_state(app)
    response = client.post("/v1/infer/global", json={"image_id": FIXTURE_IMAGE.image_id, "model_id": "retfound-aptos5"})
    return app, client, response, before


def raise_(error):
    def failure(request):
        raise error("synthetic fault", request=request)
    return failure


FAULTS = {
    "connection refused": (raise_(httpx.ConnectError), {502}),
    "connection dropped": (raise_(httpx.ReadError), {502}),
    "read timeout": (raise_(httpx.ReadTimeout), {504}),
    "server error 500": (lambda request: httpx.Response(500, json={"detail": "synthetic"}), {502}),
    "token rejected 401": (lambda request: httpx.Response(401, json={"detail": "unauthorized"}), {502}),
    "forbidden 403": (lambda request: httpx.Response(403, json={"detail": "forbidden"}), {502}),
    "malformed json": (lambda request: httpx.Response(200, content=b"{not json"), {502}),
    "wrong contract": (lambda request: httpx.Response(200, json={"unexpected": True}), {502}),
}


@pytest.mark.parametrize("name", list(FAULTS))
def test_a_broken_predict_saves_nothing_and_never_retries(monkeypatch, name):
    failure, statuses = FAULTS[name]
    calls = []
    app, client, response, before = analyze(monkeypatch, failing_predict(failure, calls))
    assert response.status_code in statuses
    assert calls == ["/v1/predict/dr"]  # Exactly one predict call: no automatic retry.
    assert clinical_state(app) == before
    assert TOKEN not in response.text


def test_an_unreachable_server_is_refused_before_any_predict_and_recovers(monkeypatch):
    state, calls = {"down": True}, []

    def handle(request):
        if state["down"]:
            raise httpx.ConnectError("synthetic fault", request=request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "PASS", "assets_verified": True})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=MODELS)
        calls.append(request.url.path)
        raise httpx.ReadError("synthetic fault", request=request)
    app, client, response, before = analyze(monkeypatch, handle)
    assert response.status_code == 503 and "manual review remains available" in response.json()["detail"]
    assert calls == [] and clinical_state(app) == before
    state["down"] = False  # The link comes back: the next request is probed again, nothing is stuck.
    again = client.post("/v1/infer/global", json={"image_id": FIXTURE_IMAGE.image_id, "model_id": "retfound-aptos5"})
    assert again.status_code == 502 and calls == ["/v1/predict/dr"]


def test_a_rejected_token_at_the_probe_is_refused_before_any_predict(monkeypatch):
    calls = []

    def handle(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "PASS", "assets_verified": True})
        if request.url.path == "/v1/models":
            return httpx.Response(401, json={"detail": "unauthorized"})
        calls.append(request.url.path)
        return httpx.Response(500)
    app, client, response, before = analyze(monkeypatch, handle)
    assert response.status_code == 503 and calls == [] and clinical_state(app) == before
    assert TOKEN not in response.text


# Known clinician-wording defects (docs/planning/HOSPITAL_M1_AC11_MS07_GAP_ANALYSIS_20261026.md).
# They are not fixed here; a fix needs owner approval and will make these pass.


@pytest.mark.xfail(strict=True, reason="AC-11 gap G1: transport error text reaches the clinician")
@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadError])
def test_gap_g1_a_dropped_connection_is_shown_in_plain_words(monkeypatch, error):
    app, client, response, before = analyze(monkeypatch, failing_predict(raise_(error), []))
    detail = response.json()["detail"]
    assert "transport" not in detail.lower() and "synthetic fault" not in detail


@pytest.mark.xfail(strict=True, reason="AC-11 gap G2: timeout reply names an operator setting")
def test_gap_g2_a_timeout_is_shown_in_plain_words(monkeypatch):
    app, client, response, before = analyze(monkeypatch, failing_predict(raise_(httpx.ReadTimeout), []))
    assert "REMOTE_MODEL_URL" not in response.json()["detail"]


@pytest.mark.xfail(strict=True, reason="AC-11 gap G5: a non-JSON error body is not a transport refusal")
def test_gap_g5_a_non_json_error_body_becomes_a_transport_refusal():
    channel = ExplicitHttpChannel("http://synthetic.invalid", auth_headers=lambda authority: {},
                                  transport=httpx.MockTransport(lambda request: httpx.Response(
                                      502, content=b"<html>Bad Gateway</html>")))
    with pytest.raises(TransportError):
        channel.request("POST", "/v1/prism-bound/execute", {})
