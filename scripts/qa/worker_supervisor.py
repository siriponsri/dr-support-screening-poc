"""Offline-reviewable single-worker safety core; no process/GPU/network adapter.

A qualified host adapter must supply a handle obtained from its OWN spawn and
atomically enforce identity again when signaling (e.g. a pinned kernel handle).
An inspect-then-os.kill(PID) adapter is NOT safe. No PID attachment API exists.
Call tick from an independent bounded watchdog, not the inference thread. All
adapter methods must return within the monitoring interval. This core cannot
enforce scheduling or interrupt a blocked host adapter; live qualification is
required before deployment. No signal, process, clock wait or GPU operation is
implemented here. Limits are per worker; the caller retains the global42 cap.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from threading import RLock
import time
from typing import Callable, Protocol


MODELS = {"uspec-uwf-grading", "retfound-aptos5", "prism-dr-5fold"}
WORKER_ROLES = MODELS | {"qa-auth-probe"}
SHA = re.compile(r"[0-9a-f]{64}\Z")
JOB = re.compile(r"[A-Za-z0-9_-]{1,96}\Z")


class SupervisorBlocked(RuntimeError):
    """Only fixed, secret-safe reason codes are exposed."""


@dataclass(frozen=True)
class ChildIdentity:
    pid: int
    parent_pid: int
    birth_marker: str
    owner_scope: str
    command_sha256: str
    model_id: str


@dataclass(frozen=True)
class Observation:
    identity: ChildIdentity
    alive: bool
    observed_at: float
    gpu_index: int
    gpu_uuid: str
    vram_mib: int
    rss_bytes: int
    project_bytes: int
    gpu_observed_at: float | None = None


@dataclass(frozen=True)
class TerminalObservation:
    """Owned kernel liveness during stop; deliberately contains no resource claim."""
    identity: ChildIdentity
    alive: bool
    observed_at: float


class OwnedChild(Protocol):
    """Trusted spawn-only adapter; implementations require separate host tests.

    signal_verified must REFUSE a stale/reused PID even if a previous observation
    matched. A boolean capability alone is not host qualification evidence.
    It must affect only this child, never a PID group, GPU reset or other worker.
    """
    identity: ChildIdentity
    atomic_identity_signals: bool

    def observe(self) -> Observation: ...

    def signal_verified(self, expected: ChildIdentity, *, force: bool) -> None: ...


@dataclass(frozen=True)
class Policy:
    model_id: str
    parent_pid: int
    owner_scope: str
    command_sha256: str
    gpu_uuid: str
    max_jobs: int
    max_seconds: float = 2700
    request_seconds: float = 30
    drain_seconds: float = 30
    monitor_seconds: float = 5
    max_vram_mib: int = 10240
    max_rss_bytes: int = 24 * 1024**3
    max_project_bytes: int = 40 * 1024**3

    def __post_init__(self):
        if (self.model_id not in WORKER_ROLES or type(self.parent_pid) is not int or self.parent_pid <= 1
                or not isinstance(self.owner_scope, str) or not 16 <= len(self.owner_scope) <= 128
                or not isinstance(self.command_sha256, str) or not SHA.fullmatch(self.command_sha256)
                or not isinstance(self.gpu_uuid, str) or not re.fullmatch(r"GPU-[A-Za-z0-9-]{8,80}", self.gpu_uuid)):
            raise ValueError("INVALID_APPROVED_WORKER_IDENTITY")
        for value, ceiling in ((self.max_jobs, 42), (self.max_vram_mib, 10240),
                               (self.max_rss_bytes, 24 * 1024**3), (self.max_project_bytes, 40 * 1024**3)):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("INVALID_RESOURCE_OR_JOB_CAP")
        for value, ceiling in ((self.max_seconds, 2700), (self.request_seconds, 30),
                               (self.drain_seconds, 30), (self.monitor_seconds, 5)):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= ceiling:
                raise ValueError("INVALID_TIME_CAP")


class WorkerSupervisor:
    """One owned child, one admitted request, one terminal failure, no restart.

    No background loop is started. A host watchdog must call tick at most5s
    apart, including during inference/drain. force is attempted at most once
    after bounded drain. A surviving child is explicitly UNCONFIRMED_STOP.
    """

    def __init__(self, policy: Policy, child: OwnedChild, *, clock: Callable[[], float] = time.monotonic):
        self.policy, self._child, self._clock = policy, child, clock
        self._lock = RLock()
        self._last_now = None
        self.state, self.reason = "UNVERIFIED", None
        self.stop_reason = self.observation_failure = None
        self.jobs_started = 0
        self._seen: set[str] = set()
        self._job = None
        self._job_deadline = self._drain_deadline = None
        identity = child.identity
        if (type(identity.pid) is not int or identity.pid <= 1 or identity.pid == policy.parent_pid
                or identity.parent_pid != policy.parent_pid or identity.owner_scope != policy.owner_scope
                or identity.command_sha256 != policy.command_sha256 or identity.model_id != policy.model_id
                or not isinstance(identity.birth_marker, str) or not 16 <= len(identity.birth_marker) <= 256
                or child.atomic_identity_signals is not True):
            raise SupervisorBlocked("UNSAFE_OR_UNRECOGNIZED_CHILD")
        self._identity = identity
        self._started = self._last_poll = self._now()
        self._deadline = self._started + policy.max_seconds
        self.state = "IDLE"
        self.tick()

    def _fault(self, reason: str):
        self.state, self.reason = "UNVERIFIED", reason
        raise SupervisorBlocked(reason)

    def _now(self) -> float:
        try:
            value = self._clock()
        except Exception:
            self._fault("MONOTONIC_CLOCK_UNAVAILABLE")
        if (type(value) not in (int, float) or not math.isfinite(value)
                or self._last_now is not None and value < self._last_now):
            self._fault("MONOTONIC_CLOCK_INVALID")
        self._last_now = value
        return value

    def _retain_adapter_failure(self):
        # Allowlisted scalar detail only, never raw text/paths/payloads.
        detail = getattr(self._child, "observation_failure", None)
        if isinstance(detail, dict):
            stage, kind, code = detail.get("stage"), detail.get("exception_class"), detail.get("errno")
            self.observation_failure = {
                "stage": stage if type(stage) is str and stage in {
                    "PIDFD_POLL", "PROC_IDENTITY", "RESOURCE_SAMPLE", "RESOURCE_RECHECK", "REAP", "STDERR_DRAIN"
                } else "UNKNOWN",
                "exception_class": kind if type(kind) is str and kind in {
                    "PermissionError", "ProcessLookupError", "FileNotFoundError", "OSError", "RuntimeError",
                    "IndexError", "ValueError", "StopIteration"
                } else "OTHER",
                "errno": code if type(code) is int and 0 <= code <= 4095 else None,
            }

    def _observe(self, *, terminal=False):
        terminal_port = getattr(self._child, "observe_terminal", None)
        stopping = (terminal or self.state in {"DRAINING", "FORCE_PENDING"}) and callable(terminal_port)
        try:
            observation = terminal_port() if stopping else self._child.observe()
        except Exception:
            self._retain_adapter_failure()
            self._fault("CHILD_OBSERVATION_UNAVAILABLE")
        if not isinstance(observation, TerminalObservation if stopping else Observation):
            self._fault("CHILD_OBSERVATION_INVALID")
        if type(observation.alive) is not bool:
            self._fault("CHILD_LIVENESS_INVALID")
        if observation.identity != self._identity:
            self._fault("CHILD_IDENTITY_CHANGED_NO_SIGNAL")
        now = self._now()
        if stopping and (type(observation.observed_at) not in (int, float) or not math.isfinite(observation.observed_at)
                         or not 0 <= now - observation.observed_at <= self.policy.monitor_seconds):
            self._fault("TELEMETRY_STALE_OR_INVALID")
        return observation, now

    def _signal(self, *, force: bool):
        try:
            # The adapter must use an identity-pinned kernel handle here. Never
            # implement this as unchecked os.kill(observation.identity.pid).
            self._child.signal_verified(self._identity, force=force)
        except Exception:
            self._retain_adapter_failure()
            self._fault("VERIFIED_SIGNAL_REFUSED_OR_FAILED")

    def _drain(self, reason: str, now: float):
        self.state, self.reason = "DRAINING", reason
        self.stop_reason = self.stop_reason or reason
        self._drain_deadline = now + self.policy.drain_seconds
        self._force_at = self._drain_deadline - min(self.policy.monitor_seconds, self.policy.drain_seconds / 2)
        self._signal(force=False)

    def _resource_fault(self, observation: Observation, now: float):
        if (type(observation.observed_at) not in (int, float) or not math.isfinite(observation.observed_at)
                or not 0 <= now - observation.observed_at <= self.policy.monitor_seconds):
            return "TELEMETRY_STALE_OR_INVALID"
        gpu_time = getattr(observation, 'gpu_observed_at', None)
        if gpu_time is not None and (type(gpu_time) not in (int, float) or not math.isfinite(gpu_time)
                                     or not 0 <= now - gpu_time <= 2.5):
            return "GPU_TELEMETRY_STALE_OR_INVALID"
        if type(observation.gpu_index) is not int or observation.gpu_index != 0 or observation.gpu_uuid != self.policy.gpu_uuid:
            return "GPU0_BINDING_MISMATCH"
        if (type(observation.vram_mib) is not int or observation.vram_mib < 0
                or type(observation.rss_bytes) is not int or observation.rss_bytes < 0
                or type(observation.project_bytes) is not int or observation.project_bytes < 0):
            return "RESOURCE_SAMPLE_INVALID"
        if observation.vram_mib > self.policy.max_vram_mib:
            return "VRAM_LIMIT"
        if observation.rss_bytes > self.policy.max_rss_bytes:
            return "RSS_LIMIT"
        if observation.project_bytes > self.policy.max_project_bytes:
            return "PROJECT_DISK_LIMIT"
        return None

    def tick(self) -> str:
        with self._lock:
            if self.state in {"STOPPED", "UNVERIFIED", "UNCONFIRMED_STOP"}:
                return self.state
            now = self._now()
            due = None
            if self.state not in {"DRAINING", "FORCE_PENDING"}:
                due = ("WORKLOAD_DEADLINE" if now >= self._deadline else
                       "REQUEST_TIMEOUT" if self._job is not None and now >= self._job_deadline else
                       "MONITORING_GAP" if now - self._last_poll > self.policy.monitor_seconds else None)
            # Expired walls need only pinned-child liveness/identity. Never put
            # a telemetry query/cache failure in front of an already due stop.
            observation, now = self._observe(terminal=due is not None)
            if type(observation.alive) is not bool:
                self._fault("CHILD_LIVENESS_INVALID")
            if not observation.alive:
                self.state = "STOPPED"
                self.reason = self.reason or "WORKER_EXITED"
                return self.state
            if due is not None:
                self._last_poll = now
                self._drain(due, now)
                return self.state
            if self.state in {"DRAINING", "FORCE_PENDING"}:
                if self.state == "DRAINING" and now >= self._force_at:
                    # At most one forced stop; never chase a recycled PID.
                    self.state = "FORCE_PENDING"
                    self._signal(force=True)
                    after, now = self._observe()
                    if after.alive is False:
                        self.state = "STOPPED"
                if self.state == "FORCE_PENDING" and now >= self._drain_deadline:
                    self.state = "UNCONFIRMED_STOP"
                return self.state
            reason = ("WORKLOAD_DEADLINE" if now >= self._deadline else
                      "REQUEST_TIMEOUT" if self._job is not None and now >= self._job_deadline else
                      "MONITORING_GAP" if now - self._last_poll > self.policy.monitor_seconds else
                      self._resource_fault(observation, now))
            self._last_poll = now
            if reason:
                self._drain(reason, now)
            return self.state

    def admit(self, job_id: str):
        with self._lock:
            self.tick()
            if not isinstance(job_id, str) or not JOB.fullmatch(job_id):
                raise SupervisorBlocked("INVALID_JOB_ID")
            if self.state != "IDLE":
                raise SupervisorBlocked("SERIAL_ADMISSION_CLOSED")
            if job_id in self._seen:
                raise SupervisorBlocked("JOB_RETRY_REJECTED")
            if self.jobs_started >= self.policy.max_jobs:
                raise SupervisorBlocked("JOB_CAP_REACHED")
            self._seen.add(job_id)
            self.jobs_started += 1
            self._job = job_id
            self._job_deadline = min(self._deadline, self._last_now + self.policy.request_seconds)
            self.state = "BUSY"

    def finish(self, job_id: str, *, success: bool):
        with self._lock:
            self.tick()
            if self.state != "BUSY" or job_id != self._job:
                raise SupervisorBlocked("NO_MATCHING_LIVE_JOB")
            if type(success) is not bool:
                raise SupervisorBlocked("INVALID_COMPLETION")
            if not success:
                self._drain("JOB_FAILED_NO_RETRY", self._last_now)
                return
            self._job = self._job_deadline = None
            self.state = "IDLE"

    def close(self):
        with self._lock:
            self.tick()
            if self.state in {"IDLE", "BUSY"}:
                self._drain("OWNER_CLOSE", self._last_now)
