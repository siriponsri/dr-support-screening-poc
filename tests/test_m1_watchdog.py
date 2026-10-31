"""MS-03 phase A watchdog runner: pure helpers and orchestration with fake children only."""

import importlib
import json
from pathlib import Path
import sys

import pytest

from test_m1_accounting_continuation import rig, upstream_seed  # noqa: F401
from test_m1_prism_window import chain  # noqa: F401
from test_m1_service_session import activate, budget_for, opened, service  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/model-server"))
watchdog = importlib.import_module("m1_watchdog")
from scripts.qa.worker_supervisor import Policy  # noqa: E402


def spec(name):
    return next(item for item in watchdog.CASES if item["case"] == name)


def test_every_case_fits_the_supervisor_policy_limits():
    for item in watchdog.CASES:
        Policy(watchdog.ROLE, 1234, "hospital_m1_qa_server_watchdog-" + item["case"], "a" * 64, watchdog.GPU,
               max_jobs=1, max_seconds=item["max_seconds"], request_seconds=item["request_seconds"],
               drain_seconds=15, monitor_seconds=5, max_vram_mib=item["max_vram_mib"],
               max_rss_bytes=item["max_rss_bytes"])
        assert item["max_vram_mib"] <= 2048 and item["max_rss_bytes"] <= 4 * 1024**3
        assert item["request_seconds"] <= 10 and item["hard_seconds"] <= 120
    assert watchdog.FRACTION_MIB <= 1536 and watchdog.PHASE_SECONDS < 900


def test_child_command_is_prlimit_then_nice_with_address_space_only_without_cuda():
    rss = watchdog.child_argv(spec("rss-limit"), Path("/run"))
    gpu = watchdog.child_argv(spec("vram-limit"), Path("/run"))
    assert rss[0] == watchdog.PRLIMIT and "--core=0" in rss and rss[rss.index("--") + 1] == watchdog.NICE
    assert any(arg.startswith("--as=") for arg in rss) and not any(arg.startswith("--as=") for arg in gpu)
    assert gpu[-4:] == ["--child", "vram-limit", "--run", str(Path("/run"))]
    assert watchdog.child_environment(spec("rss-limit"))["CUDA_VISIBLE_DEVICES"] == ""
    assert watchdog.child_environment(spec("oom-contained"))["CUDA_VISIBLE_DEVICES"] == watchdog.GPU


def passing(name, **changes):
    item = spec(name)
    observed = {key: item["expect"][key] for key in ("state", "reason", "returncode")}
    observed.update(cleanup_confirmed=True, peaks={"vram_mib": 1800}, admitted=True, child={"oom_raised": True})
    observed.update(changes)
    return item, observed


@pytest.mark.parametrize("name", [item["case"] for item in watchdog.CASES])
def test_expected_safe_stops_pass(name):
    item, observed = passing(name)
    assert watchdog.evaluate(item, observed) == []


@pytest.mark.parametrize("name, changes, problem", [
    ("oom-contained", {"child": {"oom_raised": False}}, "oom_raised"),
    ("oom-contained", {"peaks": {"vram_mib": 2300}}, "vram_peak"),
    ("vram-limit", {"reason": "WORKER_EXITED"}, "reason"),
    ("vram-limit", {"state": "UNCONFIRMED_STOP"}, "state"),
    ("rss-limit", {"returncode": -watchdog.SIGKILL}, "returncode"),
    ("request-timeout", {"admitted": False}, "admitted"),
    ("hard-alarm", {"cleanup_confirmed": False}, "cleanup_confirmed"),
])
def test_unexpected_outcomes_fail(name, changes, problem):
    item, observed = passing(name, **changes)
    assert problem in watchdog.evaluate(item, observed)


class FakeChild:
    identity = "child-identity"

    def __init__(self, returncode):
        self.alive, self.returncode, self.signals, self.closed = True, returncode, [], False

    def inspect(self):
        return self.alive

    def signal_verified(self, identity, *, force):
        self.signals.append(force)
        self.alive = False

    def close_confirmed(self):
        assert not self.alive
        self.closed = True

    def completion(self):
        assert self.closed
        return {"child_returncode": self.returncode}


class FakeSupervisor:
    def __init__(self, child, *, stop_after, reason):
        self.child, self.state, self.reason, self.ticks = child, "IDLE", None, 0
        self.stop_after, self.stop_reason, self.admitted = stop_after, reason, []

    def tick(self):
        self.ticks += 1
        if self.ticks >= self.stop_after and self.state != "STOPPED":
            self.child.alive = False
            self.state, self.reason = "STOPPED", self.stop_reason
        return self.state

    def admit(self, job_id):
        self.admitted.append(job_id)
        self.state = "BUSY"

    def close(self):
        pass


class FakeResources:
    peaks = {"vram_mib": 1200, "rss_bytes": 1, "project_bytes": 1}


def test_run_case_admits_the_slow_request_once_ready_and_passes(tmp_path):
    item = spec("request-timeout")
    child = FakeChild(-watchdog.SIGTERM)
    (tmp_path / "request-timeout.child.json").write_text(json.dumps({"ready": True}))
    holder = {}

    def supervise(_, owned):
        holder["supervisor"] = FakeSupervisor(owned, stop_after=4, reason="REQUEST_TIMEOUT")
        return holder["supervisor"]
    observed = watchdog.run_case(item, spawn=lambda _: (child, FakeResources()), supervise=supervise,
                                 run=tmp_path, sleep=lambda _: None)
    assert observed["passed"], observed["problems"]
    assert holder["supervisor"].admitted == ["watchdog-request-timeout"] and child.closed


def test_run_case_reports_a_child_that_outlives_the_case_and_still_reaps_it(tmp_path):
    item = spec("vram-limit")
    child = FakeChild(-watchdog.SIGKILL)
    clock = iter(range(0, 10000, 5))
    observed = watchdog.run_case(item, spawn=lambda _: (child, FakeResources()),
                                 supervise=lambda _, owned: FakeSupervisor(owned, stop_after=10**9, reason=None),
                                 run=tmp_path, clock=lambda: next(clock), sleep=lambda _: None)
    assert not observed["passed"] and "state" in observed["problems"]
    assert child.closed and observed["cleanup_confirmed"] is True and child.signals == [False]


def test_a_spawn_refusal_is_a_failed_case_with_nothing_left_running(tmp_path):
    def spawn(_):
        raise RuntimeError("OWNED_SPAWN_FAILED")
    observed = watchdog.run_case(spec("oom-contained"), spawn=spawn, supervise=None, run=tmp_path,
                                 sleep=lambda _: None)
    assert observed["error_class"] == "RuntimeError" and observed["cleanup_confirmed"] is True
    assert not observed["passed"]


def test_team_snapshot_comparison_ignores_memory_but_not_processes():
    before = {"ok": True, "gpu1_compute_pids": [10], "ollama_pids": [20], "gpu1_memory_mib": 5000}
    assert watchdog.team_unchanged(before, {**before, "gpu1_memory_mib": 6000})
    assert not watchdog.team_unchanged(before, {**before, "ollama_pids": [21]})
    assert not watchdog.team_unchanged(before, {**before, "gpu1_compute_pids": []})
    assert not watchdog.team_unchanged(before, {"ok": False})


def test_new_team_processes_are_normal_activity():
    before = {"ok": True, "gpu1_compute_pids": [10], "ollama_pids": [20, 21]}
    assert watchdog.team_unchanged(before, {**before, "gpu1_compute_pids": [10, 11], "ollama_pids": [20, 21, 22]})


@pytest.mark.parametrize("raw", ["{not json", "[1, 2]"])
def test_an_unreadable_child_receipt_keeps_the_cleanup_result(tmp_path, raw):
    (tmp_path / "oom-contained.child.json").write_text(raw)
    observed = watchdog.run_case(spec("oom-contained"), spawn=lambda _: (FakeChild(0), FakeResources()),
                                 supervise=lambda _, owned: FakeSupervisor(owned, stop_after=2, reason="WORKER_EXITED"),
                                 run=tmp_path, sleep=lambda _: None)
    assert observed["cleanup_confirmed"] is True and observed["child"] == {"receipt": "UNREADABLE"}
    assert "oom_raised" in observed["problems"]


class Monitor:
    def __init__(self, fails=False):
        self.fails = fails

    def close(self):
        if self.fails:
            raise RuntimeError("MONITOR")


def result(**changes):
    team = {"ok": True, "gpu1_compute_pids": [], "ollama_pids": [5]}
    value = {"cases": [{"case": "x", "passed": True, "cleanup_confirmed": True}], "gpu0_vram_after_mib": 1,
             "team_before": team, "team_after": team}
    value.update(changes)
    return value


def watchdog_window(service):  # noqa: F811
    from batch_ledger import M1_SERVICE_WATCHDOG
    ledger = opened(service)
    activate(service, ledger, M1_SERVICE_WATCHDOG)
    budget = budget_for(service, ledger, M1_SERVICE_WATCHDOG)
    budget.reserve_worker("watchdog-lifetime")
    return ledger, budget


def test_confirmed_cleanup_closes_the_watchdog_window_and_the_ledger(service):  # noqa: F811
    ledger, budget = watchdog_window(service)
    done = watchdog.finish_phase(result(), budget=budget, lease="watchdog-lifetime", ledger=ledger,
                                 monitors={"gpu_monitor": Monitor(), "disk_monitor": Monitor()})
    assert done["status"] == "PASS" and done["window_stop"] == done["ledger_close"] == "CONFIRMED"
    assert budget.body["window_closed"] is True and ledger.owned_lock is None


def test_unconfirmed_cleanup_quarantines_the_window_and_keeps_the_ledger(service):  # noqa: F811
    ledger, budget = watchdog_window(service)
    done = watchdog.finish_phase(result(), budget=budget, lease="watchdog-lifetime", ledger=ledger,
                                 monitors={"gpu_monitor": Monitor(fails=True), "disk_monitor": Monitor()})
    assert done["status"] == "FAIL" and done["cleanup_confirmed"] is False
    assert done["window_stop"].startswith("RETAINED_") and done["ledger_close"].startswith("RETAINED_")
    assert budget.body["quarantined"] is True and budget.body["charged_gpu_seconds"] == 900
    assert ledger.owned_lock is not None


def test_an_early_error_with_no_cases_is_a_failure(service):  # noqa: F811
    ledger, budget = watchdog_window(service)
    done = watchdog.finish_phase(result(cases=[], error_class="RuntimeError"), budget=budget,
                                 lease="watchdog-lifetime", ledger=ledger,
                                 monitors={"gpu_monitor": Monitor(), "disk_monitor": Monitor()})
    assert done["status"] == "FAIL" and done["window_stop"] == "CONFIRMED"


def test_not_run_cases_fail_the_phase_but_need_no_cleanup():
    done = watchdog.finish_phase(result(cases=[{"case": "x", "passed": False, "problems": ["NOT_RUN"]}]),
                                 budget=None, lease=None, ledger=None, monitors={"gpu_monitor": Monitor()})
    assert done["cleanup_confirmed"] is True and done["status"] == "FAIL"
    assert done["window_stop"] == "NO_LEASE_RESERVED" and done["ledger_close"] == "NOT_OPENED"


def test_failure_detail_keeps_only_allowlisted_scalars():
    detail = watchdog.failure_detail({"stage": "PROC_RSS_PARSE", "exception_class": "StopIteration", "errno": 2,
                                      "reason": "GPU_SAMPLE_STALE", "message": "/home/user/private/path",
                                      "token": "secret-value"})
    assert detail == {"stage": "PROC_RSS_PARSE", "exception_class": "StopIteration", "errno": 2,
                      "reason": "GPU_SAMPLE_STALE"}
    assert watchdog.failure_detail({"stage": "has space /tmp/x", "errno": 99999, "exception_class": 7}) is None
    assert watchdog.failure_detail("PIDFD_POLL") is None and watchdog.failure_detail(None) is None


def test_error_code_is_a_fixed_code_or_nothing():
    assert watchdog.error_code(RuntimeError("CHILD_OBSERVATION_UNAVAILABLE")) == "CHILD_OBSERVATION_UNAVAILABLE"
    assert watchdog.error_code(RuntimeError("free text with /path and token=x")) is None
    assert watchdog.error_code(ValueError("CHILD_OBSERVATION_UNAVAILABLE")) is None


class FaultingSupervisor(FakeSupervisor):
    """Reproduces the phase A oom-contained outcome: the adapter fails while the child exits."""

    def tick(self):
        self.observation_failure = {"stage": "RESOURCE_SAMPLE", "exception_class": "StopIteration", "errno": None,
                                    "path": "/proc/123/status"}
        self.state, self.reason = "UNVERIFIED", "CHILD_OBSERVATION_UNAVAILABLE"
        self.child.alive = False
        raise RuntimeError("CHILD_OBSERVATION_UNAVAILABLE")


class FailingResources(FakeResources):
    last_failure = {"stage": "PROC_RSS_PARSE", "exception_class": "StopIteration", "detail": "VmRSS missing"}


def test_run_case_records_the_cause_without_changing_the_verdict(tmp_path):
    item = spec("oom-contained")
    (tmp_path / "oom-contained.child.json").write_text(json.dumps({"oom_raised": True, "allocated_mib": 1024}))
    child = FakeChild(0)
    child.observation_failure = {"stage": "PROC_IDENTITY", "exception_class": "FileNotFoundError", "errno": 2}
    observed = watchdog.run_case(item, spawn=lambda _: (child, FailingResources()),
                                 supervise=lambda _, owned: FaultingSupervisor(owned, stop_after=1, reason=None),
                                 run=tmp_path, sleep=lambda _: None)
    assert observed["error_class"] == "RuntimeError" and observed["error_code"] == "CHILD_OBSERVATION_UNAVAILABLE"
    assert observed["supervisor_failure"] == {"stage": "RESOURCE_SAMPLE", "exception_class": "StopIteration"}
    assert observed["adapter_failure"] == {"stage": "PROC_IDENTITY", "exception_class": "FileNotFoundError", "errno": 2}
    assert observed["resource_failure"] == {"stage": "PROC_RSS_PARSE", "exception_class": "StopIteration"}
    # The verdict and cleanup are exactly what phase A recorded: the stop rule did not change.
    assert observed["problems"] == ["state", "reason"] and observed["cleanup_confirmed"] is True
    assert "/proc" not in json.dumps(observed) and "VmRSS" not in json.dumps(observed)


def test_monitor_failure_detail_is_recorded_and_the_status_rule_is_unchanged():
    class DetailedMonitor(Monitor):
        failure_detail = {"stage": "GPU_SAMPLE", "exception_class": "RuntimeError", "reason": "GPU_SAMPLE_STALE",
                          "raw": "nvidia-smi output"}
    done = watchdog.finish_phase(result(), budget=None, lease=None, ledger=None,
                                 monitors={"gpu_monitor": DetailedMonitor(), "disk_monitor": Monitor()})
    assert done["monitor_failures"] == {"gpu_monitor": {"stage": "GPU_SAMPLE", "exception_class": "RuntimeError",
                                                        "reason": "GPU_SAMPLE_STALE"}}
    assert done["status"] == "FAIL"  # No lease/ledger closed here, exactly as before this change.


def test_limits_quota_and_stop_rules_are_unchanged():
    assert (watchdog.FRACTION_MIB, watchdog.PHASE_SECONDS, watchdog.IDLE_VRAM_MIB) == (1024, 780, 64)
    assert watchdog.MIN_AVAILABLE_RAM == 12 * 1024**3
    assert [(item["case"], item["max_vram_mib"], item["max_rss_bytes"], item["request_seconds"], item["max_seconds"],
             item["hard_seconds"], item["expect"]["reason"]) for item in watchdog.CASES] == [
        ("oom-contained", 2048, 4 * 1024**3, 10, 90, 120, "WORKER_EXITED"),
        ("vram-limit", 768, 4 * 1024**3, 10, 90, 120, "VRAM_LIMIT"),
        ("rss-limit", 2048, 4 * 1024**3, 10, 90, 120, "RSS_LIMIT"),
        ("request-timeout", 2048, 4 * 1024**3, 10, 90, 120, "REQUEST_TIMEOUT"),
        ("hard-alarm", 2048, 4 * 1024**3, 10, 90, 15, "WORKER_EXITED")]
    source = (ROOT / "scripts/model-server/m1_watchdog.py").read_text(encoding="utf-8")
    assert "drain_seconds=15" in source and "monitor_seconds=5" in source and "max_jobs=1" in source


class Exploding:
    @property
    def observation_failure(self):
        raise KeyError("boom")

    failure_detail = observation_failure
    last_failure = observation_failure


def test_cause_capture_never_blocks_cleanup_or_accounting(tmp_path):
    child = FakeChild(0)

    class ExplodingResources(FakeResources):
        last_failure = Exploding.observation_failure
    observed = watchdog.run_case(spec("hard-alarm"), spawn=lambda _: (child, ExplodingResources()),
                                 supervise=lambda _, owned: FakeSupervisor(owned, stop_after=1, reason="WORKER_EXITED"),
                                 run=tmp_path, sleep=lambda _: None)
    assert child.closed and observed["cleanup_confirmed"] is True and "resource_failure" not in observed
    done = watchdog.finish_phase(result(), budget=None, lease=None, ledger=None, monitors={"gpu_monitor": Exploding()})
    assert "monitor_failures" not in done and done["window_stop"] == "NO_LEASE_RESERVED"


def test_lower_case_or_subclassed_detail_is_dropped():
    class Sneaky(dict):
        pass
    assert watchdog.failure_detail(Sneaky(stage="PIDFD_POLL")) is None
    assert watchdog.failure_detail({"stage": "deadbeefcafe0123", "reason": "token_abc"}) is None
