"""Post-force invalid liveness never becomes a waiting/success result."""

import pytest
from scripts.qa.worker_supervisor import SupervisorBlocked, TerminalObservation
from test_owned_terminal_wait import supervisor


@pytest.mark.parametrize("invalid", [None, 1])
def test_invalid_post_force_liveness_is_explicit_failure(monkeypatch, invalid):
    child, control, clock = supervisor(monkeypatch)
    clock[0] = 112
    states = iter([True, invalid])
    child.observe_terminal = lambda: TerminalObservation(
        child.identity, next(states), clock[0]
    )
    with pytest.raises(SupervisorBlocked, match="CHILD_LIVENESS_INVALID"):
        control.tick()
    assert control.state == "UNVERIFIED" and control.stop_reason == "REQUEST_TIMEOUT"
