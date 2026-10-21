"""Fake-only safety contracts: no host signals, subprocesses, GPU or listeners."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from scripts.qa.worker_supervisor import (
    ChildIdentity, Observation, Policy, SupervisorBlocked, WorkerSupervisor,
)


class FakeClock:
    now = 100.0

    def __call__(self):
        return self.now


class FakeChild:
    atomic_identity_signals = True

    def __init__(self, clock):
        self.clock = clock
        self.identity = ChildIdentity(77, 66, "fake_birth_00000001", "fake_scope_00000001", "a" * 64, "retfound-aptos5")
        self.live_identity = self.identity
        self.alive = True
        self.override = {}
        self.signals = []
        self.race_before_signal = False
        self.force_succeeds = True
        self.observation_fails = False

    def observe(self):
        if self.observation_fails:
            raise OSError("fixture private context must never escape")
        return replace(Observation(self.live_identity, self.alive, self.clock(), 0, "GPU-fixture-00000000", 100, 1024, 1024), **self.override)

    def signal_verified(self, expected, *, force):
        if self.race_before_signal:
            self.live_identity = replace(self.live_identity, birth_marker="recycled_birth_0002")
        if expected != self.live_identity:
            raise RuntimeError("identity changed at the signaling boundary")
        self.signals.append((expected, force))
        if force and self.force_succeeds:
            self.alive = False


@pytest.fixture
def setup():
    clock = FakeClock()
    child = FakeChild(clock)
    policy = Policy("retfound-aptos5", 66, "fake_scope_00000001", "a" * 64, "GPU-fixture-00000000", 2)
    return clock, child, policy


def start(setup, **changes):
    clock, child, policy = setup
    return WorkerSupervisor(replace(policy, **changes), child, clock=clock)


@pytest.mark.parametrize("changes", [
    {"pid": -77}, {"pid": 0}, {"pid": 1}, {"pid": 66}, {"pid": True},
    {"parent_pid": 999}, {"birth_marker": ""}, {"owner_scope": "foreign_scope_00001"},
    {"command_sha256": "b" * 64}, {"model_id": "prism-dr-5fold"},
])
def test_reject_unsafe_or_foreign_child_without_any_signal(setup, changes):
    setup[1].identity = replace(setup[1].identity, **changes)
    with pytest.raises(SupervisorBlocked, match="UNSAFE_OR_UNRECOGNIZED_CHILD"):
        start(setup)
    assert setup[1].signals == []


def test_no_raw_pid_adapter_capability(setup):
    setup[1].atomic_identity_signals = False
    with pytest.raises(SupervisorBlocked):
        start(setup)
    assert not setup[1].signals


@pytest.mark.parametrize("changes", [
    {"max_jobs": 43}, {"max_jobs": True}, {"max_seconds": 2701},
    {"request_seconds": 31}, {"drain_seconds": 31}, {"monitor_seconds": 6},
    {"max_seconds": float("inf")}, {"drain_seconds": float("nan")},
    {"max_vram_mib": 10241}, {"max_rss_bytes": 24 * 1024**3 + 1},
    {"max_project_bytes": 40 * 1024**3 + 1},
    {"gpu_uuid": ""}, {"model_id": "unknown"},
])
def test_policy_rejects_unbounded_or_unapproved_config(setup, changes):
    with pytest.raises(ValueError):
        start(setup, **changes)
    assert not setup[1].signals


def test_serial_admission_and_completed_job_cannot_retry(setup):
    supervisor = start(setup)
    supervisor.admit("job1")
    with pytest.raises(SupervisorBlocked, match="SERIAL_ADMISSION_CLOSED"):
        supervisor.admit("job2")
    supervisor.finish("job1", success=True)
    with pytest.raises(SupervisorBlocked, match="JOB_RETRY_REJECTED"):
        supervisor.admit("job1")
    supervisor.admit("job2")
    supervisor.finish("job2", success=True)
    with pytest.raises(SupervisorBlocked, match="JOB_CAP_REACHED"):
        supervisor.admit("job3")
    assert supervisor.jobs_started == 2
    assert not setup[1].signals


def test_concurrent_admission_accepts_only_one_without_starting_processes(setup):
    supervisor = start(setup)
    barrier = Barrier(2)

    def attempt(name):
        barrier.wait(timeout=2)
        try:
            supervisor.admit(name)
            return "ADMITTED"
        except SupervisorBlocked:
            return "BLOCKED"

    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(attempt, ("job1", "job2")))
    assert sorted(results) == ["ADMITTED", "BLOCKED"]
    assert supervisor.jobs_started == 1
    assert not setup[1].signals


def test_timeout_closes_admission_and_forces_once_after_bounded_drain(setup):
    clock, child, _ = setup
    supervisor = start(setup)
    supervisor.admit("job1")
    for _ in range(6):
        clock.now += 5
        supervisor.tick()
    assert supervisor.reason == "REQUEST_TIMEOUT"
    assert supervisor.state == "DRAINING"
    assert [force for _, force in child.signals] == [False]
    with pytest.raises(SupervisorBlocked):
        supervisor.admit("replacement")
    with pytest.raises(SupervisorBlocked):
        supervisor.finish("job1", success=True)
    clock.now += 24.999
    supervisor.tick()
    assert len(child.signals) == 1
    clock.now += .001
    assert supervisor.tick() == "STOPPED"
    supervisor.tick()
    supervisor.close()
    assert [force for _, force in child.signals] == [False, True]


def test_workload_deadline_rejects_new_job_at_exact_boundary(setup):
    clock, child, _ = setup
    supervisor = start(setup, max_seconds=5)
    clock.now += 5
    with pytest.raises(SupervisorBlocked):
        supervisor.admit("late")
    assert supervisor.reason == "WORKLOAD_DEADLINE"
    assert supervisor.jobs_started == 0
    assert len(child.signals) == 1


@pytest.mark.parametrize("override,reason", [
    ({"gpu_index": 1}, "GPU0_BINDING_MISMATCH"),
    ({"gpu_uuid": "GPU-foreign-00000000"}, "GPU0_BINDING_MISMATCH"),
    ({"vram_mib": 10241}, "VRAM_LIMIT"),
    ({"rss_bytes": 24 * 1024**3 + 1}, "RSS_LIMIT"),
    ({"project_bytes": 40 * 1024**3 + 1}, "PROJECT_DISK_LIMIT"),
    ({"observed_at": 94.9}, "TELEMETRY_STALE_OR_INVALID"),
    ({"observed_at": 101}, "TELEMETRY_STALE_OR_INVALID"),
    ({"observed_at": float("nan")}, "TELEMETRY_STALE_OR_INVALID"),
    ({"vram_mib": -1}, "RESOURCE_SAMPLE_INVALID"),
    ({"rss_bytes": True}, "RESOURCE_SAMPLE_INVALID"),
])
def test_resource_or_gpu_scope_violation_drains_only_owned_child(setup, override, reason):
    supervisor = start(setup)
    setup[1].override = override
    supervisor.tick()
    assert supervisor.state == "DRAINING"
    assert supervisor.reason == reason
    assert setup[1].signals == [(setup[1].identity, False)]


def test_identity_reuse_before_observation_refuses_all_signals(setup):
    supervisor = start(setup)
    setup[1].live_identity = replace(setup[1].identity, birth_marker="recycled_birth_0002")
    with pytest.raises(SupervisorBlocked, match="CHILD_IDENTITY_CHANGED_NO_SIGNAL"):
        supervisor.close()
    assert supervisor.state == "UNVERIFIED"
    assert not setup[1].signals


def test_identity_race_at_signal_is_rejected_by_adapter_no_raw_pid_fallback(setup):
    supervisor = start(setup)
    setup[1].race_before_signal = True
    with pytest.raises(SupervisorBlocked, match="VERIFIED_SIGNAL_REFUSED_OR_FAILED"):
        supervisor.close()
    assert supervisor.state == "UNVERIFIED"
    assert not setup[1].signals


def test_identity_reuse_at_force_boundary_never_chases_recycled_pid(setup):
    supervisor = start(setup)
    supervisor.close()
    setup[0].now += 30
    setup[1].race_before_signal = True
    with pytest.raises(SupervisorBlocked):
        supervisor.tick()
    assert [force for _, force in setup[1].signals] == [False]


def test_failed_force_remains_explicitly_unconfirmed_without_retry(setup):
    supervisor = start(setup)
    setup[1].force_succeeds = False
    supervisor.close()
    setup[0].now += 30
    assert supervisor.tick() == "UNCONFIRMED_STOP"
    supervisor.tick()
    with pytest.raises(SupervisorBlocked):
        supervisor.admit("new")
    assert [force for _, force in setup[1].signals] == [False, True]


def test_delayed_kernel_exit_is_confirmed_within_original_drain_deadline(setup):
    supervisor = start(setup)
    setup[1].force_succeeds = False
    supervisor.close()
    setup[0].now += 25
    assert supervisor.tick() == "FORCE_PENDING"
    setup[0].now += 1
    supervisor.tick()
    assert [force for _, force in setup[1].signals] == [False, True]
    setup[1].alive = False
    assert supervisor.tick() == "STOPPED"


def test_monitoring_gap_closes_admission(setup):
    supervisor = start(setup)
    setup[0].now += 5.001
    supervisor.tick()
    assert supervisor.reason == "MONITORING_GAP"


def test_nonmonotonic_clock_refuses_actions(setup):
    supervisor = start(setup)
    setup[0].now -= 1
    with pytest.raises(SupervisorBlocked, match="MONOTONIC_CLOCK_INVALID"):
        supervisor.admit("job")
    assert not setup[1].signals


def test_observation_error_redacts_details_and_never_guesses_pid(setup):
    supervisor = start(setup)
    setup[1].observation_fails = True
    with pytest.raises(SupervisorBlocked, match="^CHILD_OBSERVATION_UNAVAILABLE$"):
        supervisor.tick()
    assert not setup[1].signals


def test_invalid_observation_permanently_closes_admission(setup):
    supervisor = start(setup)
    setup[1].observe = lambda: None
    with pytest.raises(SupervisorBlocked, match="CHILD_OBSERVATION_INVALID"):
        supervisor.tick()
    assert supervisor.state == "UNVERIFIED"
    with pytest.raises(SupervisorBlocked):
        supervisor.admit("job")
    assert not setup[1].signals


def test_clock_exception_closes_admission_without_leaking_provider_details(setup):
    supervisor = start(setup)

    def unavailable():
        raise OSError("fixture provider private detail")

    supervisor._clock = unavailable
    with pytest.raises(SupervisorBlocked, match="^MONOTONIC_CLOCK_UNAVAILABLE$"):
        supervisor.tick()
    assert supervisor.state == "UNVERIFIED"
    assert not setup[1].signals


def test_worker_exit_during_request_is_terminal_without_signaling(setup):
    supervisor = start(setup)
    supervisor.admit("job")
    setup[1].alive = False
    assert supervisor.tick() == "STOPPED"
    with pytest.raises(SupervisorBlocked):
        supervisor.finish("job", success=True)
    assert not setup[1].signals


def test_failure_closes_lifetime_and_early_exit_needs_no_signal(setup):
    supervisor = start(setup)
    supervisor.admit("job")
    supervisor.finish("job", success=False)
    assert supervisor.reason == "JOB_FAILED_NO_RETRY"
    setup[1].alive = False
    assert supervisor.tick() == "STOPPED"
    assert [force for _, force in setup[1].signals] == [False]
