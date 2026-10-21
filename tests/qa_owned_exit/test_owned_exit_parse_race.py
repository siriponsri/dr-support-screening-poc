"""Deterministic /proc exit races and fake pidfd only; no host processes."""

from types import SimpleNamespace

import pytest

from scripts.qa import linux_owned_child as module
from scripts.qa.worker_supervisor import ChildIdentity
from scripts.qa.worker_supervisor import Policy, SupervisorBlocked, WorkerSupervisor


def handle(monkeypatch, *, terminal):
    owned = object.__new__(module.LinuxOwnedChild)
    owned.identity = ChildIdentity(
        123, 66, "fixture_birth_0001", "fixture_scope_0001", "a" * 64, "prism-dr-5fold"
    )
    owned._closed = False
    owned._pidfd = 999
    calls = []

    def poll(timeout):
        assert timeout == 0  # No added waits or deadline/monitoring relaxation.
        calls.append(timeout)
        return [(999, 1)] if terminal and len(calls) > 1 else []

    owned._poll = SimpleNamespace(poll=poll)
    owned._resources = lambda pid: pytest.fail(
        "EXITING_OR_UNKNOWN_CHILD_MUST_NOT_BE_SAMPLED"
    )
    monkeypatch.setattr(
        module.os, "kill", lambda *a: pytest.fail("RAW_PID_SIGNAL_FORBIDDEN")
    )
    monkeypatch.setattr(
        module.signal,
        "pidfd_send_signal",
        lambda *a: pytest.fail("NO_SIGNAL_IN_OBSERVATION"),
        raising=False,
    )
    return owned, calls


@pytest.mark.parametrize(
    "stat", ["", "123 (terminated task) Z", "123 (terminated task) Z bad-parent"]
)
@pytest.mark.parametrize("terminal", [True, False])
def test_empty_or_partial_proc_read_requires_independent_terminal_pidfd(
    monkeypatch, stat, terminal
):
    owned, calls = handle(monkeypatch, terminal=terminal)

    class FakePath:
        def __init__(self, path):
            self.path = path

        def read_text(self):
            return "fixture-boot-id" if self.path.endswith("boot_id") else stat

    monkeypatch.setattr(module, "Path", FakePath)
    if terminal:
        observation = owned.observe()
        assert observation.alive is False and observation.identity == owned.identity
        assert observation.rss_bytes == observation.vram_mib == 0
        assert calls == [0, 0]
    else:
        with pytest.raises((IndexError, ValueError)):
            owned.observe()
        assert calls in ([0], [0, 0])


def test_closed_handle_remains_an_error_without_kernel_poll(monkeypatch):
    owned, calls = handle(monkeypatch, terminal=True)
    owned._closed = True
    with pytest.raises(RuntimeError, match="OWNED_HANDLE_CLOSED"):
        owned.observe()
    assert calls == []


def test_pidfd_poll_failure_is_never_replaced_by_proc_inference(monkeypatch):
    owned, _ = handle(monkeypatch, terminal=True)

    def unavailable(timeout):
        raise OSError("FAKE_KERNEL_OBSERVATION_UNAVAILABLE")

    owned._poll = SimpleNamespace(poll=unavailable)
    monkeypatch.setattr(
        module, "proc_identity", lambda pid: pytest.fail("DO_NOT_INFER_EXIT_FROM_PROC")
    )
    with pytest.raises(OSError):
        owned.observe()


@pytest.mark.parametrize("terminal_proven", [True, False])
def test_timeout_force_partial_proc_read_preserves_kernel_proof_boundary(
    monkeypatch, terminal_proven
):
    """Reproduce q02's phase with fake pidfd/clock, not its unrecorded OS cause."""
    owned, _ = handle(monkeypatch, terminal=False)
    now = [100.0]
    killed = [False]
    post_force_polls = []
    signals = []
    birth = "fixture_boot_001:12345"
    owned.identity = ChildIdentity(
        123, 66, birth, "fixture_scope_0001", "a" * 64, "prism-dr-5fold"
    )

    def poll(timeout):
        assert timeout == 0
        if killed[0]:
            post_force_polls.append(timeout)
            if terminal_proven and len(post_force_polls) > 1:
                return [(999, 1)]
        return []

    owned._poll = SimpleNamespace(poll=poll)

    class FakePath:
        def __init__(self, path):
            self.path = path

        def read_text(self):
            if self.path.endswith("boot_id"):
                return "fixture_boot_001"
            if killed[0]:
                return ""
            return "123 (owned child) " + " ".join(["S", "66"] + ["0"] * 17 + ["12345"])

    monkeypatch.setattr(module, "Path", FakePath)
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    sample_calls = []

    def resources(pid):
        sample_calls.append(pid)
        if killed[0]:
            raise StopIteration("SYNTHETIC_MISSING_EXIT_RSS")
        return dict(
            gpu_index=0,
            gpu_uuid="GPU-fixture-00000000",
            vram_mib=0,
            rss_bytes=1024,
            project_bytes=1024,
        )

    owned._resources = resources

    def signal(fd, number, *args):
        assert fd == 999
        signals.append(number)
        if number == 9:
            killed[0] = True

    owned._pidfd = 999
    monkeypatch.setattr(module.signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(module.signal, "pidfd_send_signal", signal, raising=False)
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
    supervisor = WorkerSupervisor(policy, owned, clock=lambda: now[0])
    supervisor.admit("fake_job_2")
    now[0] = 108
    assert supervisor.tick() == "DRAINING" and supervisor.reason == "REQUEST_TIMEOUT"
    before_stop_samples = len(sample_calls)
    now[0] = 112
    assert supervisor.tick() == "FORCE_PENDING"
    with pytest.raises(SupervisorBlocked, match="SERIAL_ADMISSION_CLOSED"):
        supervisor.admit("not_authorized_during_stop")
    now[0] = 112.25
    if terminal_proven:
        assert supervisor.tick() == "STOPPED"
        assert supervisor.reason == "REQUEST_TIMEOUT"
    else:
        assert supervisor.tick() == "FORCE_PENDING"
        now[0] = 113
        assert supervisor.tick() == "UNCONFIRMED_STOP"
    assert signals == [module.signal.SIGTERM, 9]
    assert len(sample_calls) == before_stop_samples  # No live-RSS claims once stopping.
