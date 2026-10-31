"""AC-11 offline fault injection on the review app's remote grading path.

MockTransport only: no network, model server, GPU or hospital data. Each case
starts from established clinician work (a confirmed grade and human annotation
geometry), probes successfully, then breaks the predict call (or the probe) and
checks the safety rules: the clinician's work and history are unchanged, no
result is saved, exactly one predict call is made (no automatic retry), the
reply is plain language with no token, setting name or raw exception text, and
"not sent" is said only when no connection was made.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from dr_support.providers.prism_remote_bound import ExplicitHttpChannel, RemoteReplyUnreadable
from test_remote import FIXTURE_IMAGE, _wire_remote_app

TOKEN = "synthetic-remote-secret"
MODELS = [{"model_id": "retfound-aptos5", "task": "global", "modalities": ["CFP"], "status": "LOADED",
           "release_status": "RESEARCH_ONLY"}]
CLINICAL_FIELDS = ("revision", "global", "inference_history", "reviewed_grade", "grade_status", "grade_review_source",
                   "human_annotations", "clinician_review", "lesion", "annotation_hash", "events")
ANNOTATIONS = [{"type": "rectangle", "label": "HEMORRHAGE", "geometry": {"x": 10, "y": 20, "width": 30, "height": 25}},
               {"type": "point", "label": "MICROANEURYSM", "geometry": {"x": 40, "y": 60}}]


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


def established(monkeypatch, handler):
    """A case with a confirmed clinician grade and human annotation geometry before any fault."""
    app = _wire_remote_app(monkeypatch, handler, token=TOKEN)
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    client = TestClient(app)
    case = client.get(f"/v1/cases/{FIXTURE_IMAGE.image_id}").json()
    saved = client.put(f"/v1/cases/{FIXTURE_IMAGE.image_id}/annotations", json={
        "revision": case["revision"], "reviewer": "Synthetic clinician", "annotations": ANNOTATIONS})
    assert saved.status_code == 200, saved.text
    graded = client.post(f"/v1/cases/{FIXTURE_IMAGE.image_id}/review", json={
        "revision": saved.json()["revision"], "action": "CORRECT_GRADE", "reviewer": "Synthetic clinician", "grade": 2})
    assert graded.status_code == 200, graded.text
    before = clinical_state(app)
    assert before["reviewed_grade"] == 2 and len(before["human_annotations"]) == 2  # Real work to preserve.
    return app, client, before


def analyze(client):
    return client.post("/v1/infer/global", json={"image_id": FIXTURE_IMAGE.image_id, "model_id": "retfound-aptos5"})


def raise_(error):
    def failure(request):
        raise error("synthetic fault /tmp/secret-path", request=request)
    return failure


UNKNOWN = "The result is unknown"
FAULTS = {
    "connection refused": (raise_(httpx.ConnectError), 503, "was not sent"),
    "connect timeout": (raise_(httpx.ConnectTimeout), 503, "was not sent"),
    "connection dropped": (raise_(httpx.ReadError), 502, UNKNOWN),
    "remote protocol error": (raise_(httpx.RemoteProtocolError), 502, UNKNOWN),
    "read timeout": (raise_(httpx.ReadTimeout), 504, UNKNOWN),
    "server error 500": (lambda request: httpx.Response(500, json={"detail": "synthetic"}), 502, "refused or could not complete"),
    "token rejected 401": (lambda request: httpx.Response(401, json={"detail": "unauthorized"}), 502, "refused or could not complete"),
    "forbidden 403": (lambda request: httpx.Response(403, json={"detail": "forbidden"}), 502, "refused or could not complete"),
    "malformed json": (lambda request: httpx.Response(200, content=b"{not json"), 502, "could not be verified"),
    "html error page": (lambda request: httpx.Response(502, content=b"<html>Bad Gateway</html>"), 502, "refused or could not complete"),
    "wrong contract": (lambda request: httpx.Response(200, json={"unexpected": True}), 502, "could not be verified"),
}


@pytest.mark.parametrize("name", list(FAULTS))
def test_a_broken_predict_preserves_clinician_work_and_never_retries(monkeypatch, name):
    failure, status, wording = FAULTS[name]
    calls = []
    app, client, before = established(monkeypatch, failing_predict(failure, calls))
    response = analyze(client)
    detail = response.json()["detail"]
    assert response.status_code == status and wording in detail
    assert calls == ["/v1/predict/dr"]  # Exactly one predict call: no automatic retry.
    assert clinical_state(app) == before  # Grade, geometry, reviewer, history and revision unchanged.
    for leak in (TOKEN, "REMOTE_MODEL_URL", "secret-path", "synthetic fault", "transport", "Errno", "httpx"):
        assert leak not in detail
    if wording == UNKNOWN:
        assert "not sent" not in detail and "Do not resend" in detail  # Possibly sent: never "nothing ran".


def test_an_unreachable_server_is_refused_before_any_predict_and_recovers(monkeypatch):
    state, calls = {"down": False}, []

    def handle(request):
        if state["down"]:
            raise httpx.ConnectError("synthetic fault", request=request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "PASS", "assets_verified": True})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=MODELS)
        calls.append(request.url.path)
        raise httpx.ReadError("synthetic fault", request=request)
    app, client, before = established(monkeypatch, handle)
    state["down"] = True
    response = analyze(client)
    assert response.status_code == 503 and "manual review remains available" in response.json()["detail"]
    assert calls == [] and clinical_state(app) == before
    state["down"] = False  # The link comes back: the next request is probed again, nothing is stuck.
    again = analyze(client)
    assert again.status_code == 502 and calls == ["/v1/predict/dr"] and clinical_state(app) == before


def test_a_rejected_token_at_the_probe_is_refused_before_any_predict(monkeypatch):
    calls, state = [], {"reject": False}

    def handle(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "PASS", "assets_verified": True})
        if request.url.path == "/v1/models":
            return httpx.Response(401, json={"detail": "unauthorized"}) if state["reject"] else httpx.Response(200, json=MODELS)
        calls.append(request.url.path)
        return httpx.Response(500)
    app, client, before = established(monkeypatch, handle)
    state["reject"] = True
    response = analyze(client)
    assert response.status_code == 503 and calls == [] and clinical_state(app) == before
    assert TOKEN not in response.text


@pytest.mark.parametrize("body, status", [(b"<html>Bad Gateway</html>", 502), (b"[1, 2]", 200), (b"", 401)])
def test_a_non_json_prism_reply_is_a_transport_refusal_not_a_parse_crash(body, status):
    channel = ExplicitHttpChannel("http://synthetic.invalid", auth_headers=lambda authority: {},
                                  transport=httpx.MockTransport(lambda request: httpx.Response(status, content=body)))
    with pytest.raises(RemoteReplyUnreadable) as raised:
        channel.request("POST", "/v1/prism-bound/execute", {})
    assert raised.value.code == "REMOTE_REPLY_NOT_JSON" and raised.value.status >= 400
