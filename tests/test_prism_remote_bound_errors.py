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
