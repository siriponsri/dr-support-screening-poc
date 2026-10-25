"""Host refusal codes reach the app log; synthetic MockTransport only."""
import httpx
import pytest

from dr_support.providers.prism_remote_bound import ExplicitHttpChannel
from dr_support.services.prism_remote_transport import TransportError


def channel(body, status=409):
    return ExplicitHttpChannel("http://synthetic.invalid", auth_headers=lambda authority: {},
                               transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)))


@pytest.mark.parametrize("body, code", [
    ({"error": "PLAN_EXPIRED"}, "PLAN_EXPIRED"),
    ({"detail": "Request not admitted; no inference dispatched", "code": "PRISM_FROZEN_PLAN_INVALID"},
     "PRISM_FROZEN_PLAN_INVALID"),
    ({"detail": "Outside the M1 session scope"}, "REMOTE_REJECTED"),
    ({"code": 7}, "REMOTE_REJECTED"),
])
def test_host_refusal_code_is_kept(body, code):
    with pytest.raises(TransportError) as raised:
        channel(body).request("POST", "/v1/prism-bound/execute", {})
    assert raised.value.code == code and raised.value.status == 409


def recording_channel(seen, handler=None):
    def respond(request):
        seen.append((request.url.path, request.extensions["timeout"]))
        return handler(request) if handler else httpx.Response(200, json={})
    return ExplicitHttpChannel("http://synthetic.invalid", auth_headers=lambda authority: {},
                               transport=httpx.MockTransport(respond))


def test_only_prepare_gets_the_longer_read_timeout():
    seen = []
    channel = recording_channel(seen)
    channel.request("POST", "/v1/prism-bound/prepare", {})
    channel.request("POST", "/v1/prism-bound/execute", {})
    channel.request("GET", "/v1/prism-bound/capabilities")
    for path in ("/v1/prism-bound/jobs/synthetic_job_1", "/v1/prism-bound/jobs/synthetic_job_1/grant",
                 "/v1/prism-bound/jobs/synthetic_job_1/cancel"):
        channel.request("POST" if path.endswith(("grant", "cancel")) else "GET", path, {})
    timeouts = {path: value for path, value in seen}
    assert timeouts.pop("/v1/prism-bound/prepare") == {"connect": 2, "read": 10, "write": 10, "pool": 10}
    assert len(timeouts) == 5 and all(value["read"] == 2 for value in timeouts.values())


def test_a_prepare_timeout_becomes_a_plain_retryable_refusal():
    from types import SimpleNamespace
    from dr_support.providers.prism_remote_bound import RemoteBoundTransportCandidate

    def timeout(request):
        raise httpx.ReadTimeout("synthetic", request=request)
    authority = SimpleNamespace(authorize_prepare=lambda wire: None)
    candidate = RemoteBoundTransportCandidate(recording_channel([], timeout), source_authority=authority)
    candidate.capabilities = {"epoch": "synthetic-epoch", "pins": {}}
    wire = SimpleNamespace(data=b"synthetic", sha256="a" * 64, media_type="image/png", modality="CFP")
    with pytest.raises(TransportError) as raised:
        candidate.prepare_prism_preview_candidate(wire)
    assert raised.value.code == "PREPARE_UNAVAILABLE" and raised.value.status == 503
    assert candidate.tickets == {}


def test_an_execute_timeout_is_not_turned_into_a_prepare_refusal():
    def timeout(request):
        raise httpx.ReadTimeout("synthetic", request=request)
    with pytest.raises(httpx.ReadTimeout):
        recording_channel([], timeout).request("POST", "/v1/prism-bound/execute", {})
