"""MS-03 phase A watchdog runner: pure helpers and orchestration with fake children only."""

import importlib
import json
from pathlib import Path
import sys

import pytest

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
               drain_seconds=10, monitor_seconds=2, max_vram_mib=item["max_vram_mib"],
               max_rss_bytes=item["max_rss_bytes"])
        assert item["max_vram_mib"] <= 2048 and item["max_rss_bytes"] <= 4 * 1024**3
        assert item["request_seconds"] <= 10 and item["hard_seconds"] <= 120
    assert watchdog.FRACTION_MIB == 1536 and watchdog.PHASE_SECONDS < 900


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
