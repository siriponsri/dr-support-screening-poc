"""Fake kernel handle, resource providers and reaping only; no host work."""

from dataclasses import replace
import errno
from types import SimpleNamespace

import pytest

from scripts.qa import linux_owned_child as module
from scripts.qa.worker_supervisor import (
    Policy,
    SupervisorBlocked,
    TerminalObservation,
    WorkerSupervisor,
)
from test_owned_exit_parse_race import handle


@pytest.mark.parametrize(
    "failure",
    [StopIteration(), PermissionError(errno.EACCES, "PRIVATE_PATH_MUST_NOT_LOG")],
)
def test_live_resource_failure_is_not_terminal_proof(monkeypatch, failure):
    owned, _ = handle(monkeypatch, terminal=False)
    owned.inspect = lambda: True

    def resources(pid):
        raise failure

    owned._resources = resources
    with pytest.raises(type(failure)):
        owned.observe()
    assert owned.observation_failure["stage"] == "RESOURCE_SAMPLE"
    assert "PRIVATE_PATH" not in str(owned.observation_failure)


@pytest.mark.parametrize("code", [errno.EACCES, errno.EPERM])
def test_denied_proc_identity_does_not_fall_back_to_a_later_pidfd_poll(
    monkeypatch, code
):
    owned, calls = handle(monkeypatch, terminal=True)

    def denied(pid):
        raise PermissionError(code, "PRIVATE_IDENTITY_DENIAL")

    monkeypatch.setattr(module, "proc_identity", denied)
    with pytest.raises(PermissionError):
        owned.inspect()
    assert calls == [0]
    assert owned.observation_failure["stage"] == "PROC_IDENTITY"


@pytest.mark.parametrize("code", [errno.EACCES, errno.EPERM])
def test_denied_resource_sample_is_failure_even_if_a_later_exit_would_be_proven(
    monkeypatch, code
):
    owned, _ = handle(monkeypatch, terminal=True)
    inspections = []

    def inspect():
        inspections.append(1)
        return len(inspections) == 1

    owned.inspect = inspect

    def denied(pid):
        raise PermissionError(code, "PRIVATE_DENIAL_MESSAGE")

    owned._resources = denied
    with pytest.raises(PermissionError):
        owned.observe()
    assert inspections == [1]  # Never switch observation route after denied sampling.
    assert owned.observation_failure == {
        "stage": "RESOURCE_SAMPLE",
        "exception_class": "PermissionError",
        "errno": code,
    }


@pytest.mark.parametrize("events", [[(999, 32)], [(999, 8)], [(999, 16)], [(1000, 1)]])
def test_invalid_closed_foreign_or_error_poll_events_are_never_exit(
    monkeypatch, events
):
    owned, _ = handle(monkeypatch, terminal=False)
    owned._poll = SimpleNamespace(poll=lambda timeout: events)
    with pytest.raises(RuntimeError, match="OWNED_PIDFD_EVENT_INVALID"):
        owned.observe_terminal()
    assert owned.observation_failure["stage"] == "PIDFD_POLL"


@pytest.mark.parametrize("code", [errno.EACCES, errno.EPERM, errno.EBADF])
def test_terminal_poll_denial_or_invalid_handle_remains_failure(monkeypatch, code):
    owned, _ = handle(monkeypatch, terminal=False)

    def failed(timeout):
        raise OSError(code, "PRIVATE_KERNEL_ERROR")

    owned._poll = SimpleNamespace(poll=failed)
    with pytest.raises(OSError):
        owned.observe_terminal()
    assert owned.observation_failure["stage"] == "PIDFD_POLL"
    assert owned.observation_failure["errno"] == code
    assert "PRIVATE_KERNEL_ERROR" not in str(owned.observation_failure)


def supervisor(monkeypatch):
    owned, _ = handle(monkeypatch, terminal=False)
    monkeypatch.setattr(
        module,
        "proc_identity",
        lambda pid: (owned.identity.parent_pid, owned.identity.birth_marker),
    )
    clock = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    owned._resources = lambda pid: dict(
        gpu_index=0,
        gpu_uuid="GPU-fixture-00000000",
        vram_mib=0,
        rss_bytes=1,
        project_bytes=1,
    )
    owned.signal_verified = lambda identity, force: None
    policy = Policy(
        "prism-dr-5fold",
        66,
        "fixture_scope_0001",
        "a" * 64,
        "GPU-fixture-00000000",
        2,
        max_seconds=90,
        request_seconds=8,
        drain_seconds=5,
        monitor_seconds=1,
    )
    control = WorkerSupervisor(policy, owned, clock=lambda: clock[0])
    control.admit("fake_job")
    clock[0] = 108
    assert control.tick() == "DRAINING"
    return owned, control, clock


def test_terminal_before_force_stops_without_another_signal(monkeypatch):
    owned, control, clock = supervisor(monkeypatch)
    owned.signal_verified = lambda *a, **kw: pytest.fail(
        "NO_EXTRA_SIGNAL_AFTER_KERNEL_TERMINAL"
    )
    owned._poll = SimpleNamespace(poll=lambda timeout: [(999, 1)])
    clock[0] = 110
    assert control.tick() == "STOPPED" and control.reason == "REQUEST_TIMEOUT"


def test_termination_port_identity_mismatch_stays_unverified(monkeypatch):
    owned, control, clock = supervisor(monkeypatch)
    owned.observe_terminal = lambda: TerminalObservation(
        replace(owned.identity, birth_marker="reused_birth_marker"), False, clock[0]
    )
    with pytest.raises(SupervisorBlocked, match="CHILD_IDENTITY_CHANGED_NO_SIGNAL"):
        control.tick()
    assert control.state == "UNVERIFIED"


def test_denied_terminal_poll_retains_allowlisted_detail(monkeypatch):
    owned, control, clock = supervisor(monkeypatch)

    def denied(timeout):
        raise PermissionError(errno.EACCES, "PRIVATE_PATH")

    owned._poll = SimpleNamespace(poll=denied)
    with pytest.raises(SupervisorBlocked, match="CHILD_OBSERVATION_UNAVAILABLE"):
        control.tick()
    assert control.state == "UNVERIFIED"
    assert control.observation_failure == {
        "stage": "PIDFD_POLL",
        "exception_class": "PermissionError",
        "errno": errno.EACCES,
    }
    assert control.stop_reason == "REQUEST_TIMEOUT"


def test_live_denial_never_switches_to_terminal_route_or_reopens(monkeypatch):
    owned, _ = handle(monkeypatch, terminal=False)
    monkeypatch.setattr(
        module,
        "proc_identity",
        lambda pid: (owned.identity.parent_pid, owned.identity.birth_marker),
    )
    clock = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    owned._resources = lambda pid: dict(
        gpu_index=0,
        gpu_uuid="GPU-fixture-00000000",
        vram_mib=0,
        rss_bytes=1,
        project_bytes=1,
    )
    policy = Policy(
        "prism-dr-5fold", 66, "fixture_scope_0001", "a" * 64, "GPU-fixture-00000000", 2
    )
    control = WorkerSupervisor(policy, owned, clock=lambda: clock[0])

    def denied(pid):
        raise PermissionError(errno.EPERM, "PRIVATE_RESOURCE_DENIAL")

    owned._resources = denied
    owned.observe_terminal = lambda: pytest.fail("NO_ALTERNATE_ROUTE_AFTER_DENIAL")
    with pytest.raises(SupervisorBlocked, match="CHILD_OBSERVATION_UNAVAILABLE"):
        control.tick()
    assert control.tick() == "UNVERIFIED"
    assert control.observation_failure["exception_class"] == "PermissionError"


@pytest.mark.parametrize("failure", [False, True])
def test_confirmed_reaping_and_failed_reaping_remain_distinct(monkeypatch, failure):
    owned, _ = handle(monkeypatch, terminal=True)
    owned._poll = SimpleNamespace(poll=lambda timeout: [(999, 1)])
    closes = []

    def reap(timeout):
        assert timeout == 1
        if failure:
            raise OSError(errno.ECHILD, "PRIVATE_REAP_ERROR")

    owned._process = SimpleNamespace(wait=reap, returncode=-9)
    owned._stderr_thread = SimpleNamespace(
        join=lambda timeout: None, is_alive=lambda: False
    )
    owned._stderr_bytes = 0
    owned._stderr_hash = module.hashlib.sha256(b"")
    monkeypatch.setattr(module.os, "close", closes.append)
    if failure:
        with pytest.raises(OSError):
            owned.close_confirmed()
        assert not owned._closed and closes == []
        assert owned.observation_failure["stage"] == "REAP"
    else:
        owned.close_confirmed()
        assert (
            owned._closed
            and closes == [999]
            and owned.completion()["child_returncode"] == -9
        )
        with pytest.raises(RuntimeError, match="OWNED_HANDLE_CLOSED"):
            owned.observe_terminal()


def test_windows_fake_events_do_not_need_native_linux_select_constants(monkeypatch):
    owned, _ = handle(monkeypatch, terminal=False)
    for name in ("POLLIN", "POLLERR", "POLLNVAL"):
        monkeypatch.delattr(module.select, name, raising=False)
    owned._poll = SimpleNamespace(poll=lambda timeout: [(999, 1)])
    assert owned.observe_terminal().alive is False
