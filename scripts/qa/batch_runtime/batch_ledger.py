"""Fsynced append-only attempt ledger for the approved finite demo batch.

No inference transport, process launch, credentials or database access here.
An attempt is consumed before a call, including an ambiguous/failed call.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import math
from collections import Counter
from copy import deepcopy
from threading import RLock
from uuid import uuid4

BASE_USED, CAP = 49, 529
M1_BASE_USED, M1_CAP = 525, 549
M1_DECISION = "HOSPITAL_M1_ACCOUNTING_20261023"
M1_SERVER = "HOSPITAL_M1_QA_SERVER_20261023"
M1_LOCAL = "HOSPITAL_M1_QA_LOCAL_20261023"
M1_WINDOWS = {M1_SERVER: "QA_SERVER", M1_LOCAL: "QA_LOCAL"}
M1_ALLOCATIONS = {"server_acceptance": 9, "local_acceptance": 6, "post_fix_verification": 9}
M1_UPSTREAM_LEDGER_SHA = "ebc4f23ac5b9d89f136ada7a36b08350ddacf186e338a50c0ea5ba6f5ba14d98"
M1_GPU0 = "GPU-044a8b11-4729-458b-a07b-297e45439419"
# Owner-approved 2026-10-23: the retained finite-demo COMPLETE receipt predates
# the listener_closed/cleanup_components fields. Its producer (demo_session.py
# sha256 e0721fe11fc436c3a1b409df4c8010c50e6e49d5f858e04de27b51da71582091)
# published it only after supervisor close, child drain/close_confirmed and both
# monitor closes returned, and set cleanup_confirmed from the closed listener.
# Only these exact bytes are accepted in that legacy shape.
M1_LEGACY_DEMO_COMPLETE_SHA = "9847e4da6c7d5c4fd0703c0141ccaad7c40feda90dab85b0d5ae94fc5e9d5a06"
M1_ANCHORS = {"batch_ledger", "original_budget", "second_budget", "demo_requests",
              "demo_activation", "demo_complete", "demo_ready"}
TERMINAL = {"PASS_READBACK", "FAILED_NO_RETRY", "FAILED_PERSISTENCE", "SENT_OR_UNCERTAIN", "BLOCKED_PREMODEL"}
TRANSITIONS = {
    None: {"ATTEMPT_INTENT", "BLOCKED_PREMODEL"},
    "ATTEMPT_INTENT": {"RESPONSE_RETAINED", "FAILED_NO_RETRY", "SENT_OR_UNCERTAIN"},
    "RESPONSE_RETAINED": {"PASS_READBACK", "FAILED_PERSISTENCE"},
}
REASONS = {None, "SOURCE_CHANGED", "MODEL_IDENTITY_CHANGED", "AUTH_FAILED", "DEADLINE", "RESOURCE_LIMIT", "DISCONNECTED", "INVALID_RESPONSE", "POSTGRES_READBACK_MISMATCH", "CLINICAL_STATE_CHANGED", "OWNED_CLEANUP_UNCONFIRMED", "APP_REJECTED", "RESPONSE_IO_FAILED", "OPERATOR_STOP"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def require(value, code):
    if not value:
        raise RuntimeError(code)


def _is_sha(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _direct(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.exists():
            require(not item.is_symlink() and not getattr(item.stat(), "st_file_attributes", 0) & 1024,
                    "M1_REPARSE_PATH_REJECTED")
    return path


def _regular(path):
    path = _direct(path)
    require(path.is_file() and path.stat().st_size <= 10 * 1024**2, "M1_REGULAR_BOUNDED_FILE_REQUIRED")
    return path.read_bytes()


def _new_file(path, raw):
    with Path(path).open("xb") as output:
        require(output.write(raw) == len(raw), "M1_PARTIAL_WRITE_QUARANTINED")
        output.flush()
        os.fsync(output.fileno())


def _prior_batch(raw):
    """Replay actual pinned rows; a declaration of525 never establishes usage."""
    require(raw and raw.endswith(b"\n"), "M1_UPSTREAM_LEDGER_TORN")
    states, intents, previous, manifest = {}, 0, "0" * 64, None
    for seq, line in enumerate(raw.splitlines(), 1):
        row = json.loads(line)
        require(set(row) == {"seq", "manifest", "job_id", "state", "reason", "artifact_sha256", "previous", "hash"}
                and row["seq"] == seq and _is_sha(row["job_id"]) and _is_sha(row["manifest"]),
                "M1_UPSTREAM_LEDGER_SCHEMA")
        manifest = manifest or row["manifest"]
        require(row["manifest"] == manifest and row["previous"] == previous
                and row["hash"] == digest(canonical({k: v for k, v in row.items() if k != "hash"}))
                and row["reason"] in REASONS
                and row["state"] in TRANSITIONS.get(states.get(row["job_id"]), set()),
                "M1_UPSTREAM_LEDGER_CHAIN_OR_TRANSITION")
        require(row["artifact_sha256"] is None or _is_sha(row["artifact_sha256"]), "M1_UPSTREAM_ARTIFACT_INVALID")
        if row["state"] in {"RESPONSE_RETAINED", "PASS_READBACK"}:
            require(_is_sha(row["artifact_sha256"]), "M1_UPSTREAM_ARTIFACT_REQUIRED")
        previous = row["hash"]
        states[row["job_id"]] = row["state"]
        intents += row["state"] == "ATTEMPT_INTENT"
    require(intents == 476 and len(states) == 480
            and Counter(states.values()) == {"PASS_READBACK": 467, "FAILED_NO_RETRY": 9, "BLOCKED_PREMODEL": 4},
            "M1_EXACT_CLOSED_480_BATCH_REQUIRED")
    return manifest, states


def _closed_budget(raw, manifest, charge):
    saved = json.loads(raw)
    body = saved["body"]
    require(saved["sha256"] == digest(canonical(body)) and body["manifest"] == manifest
            and body["active"] is None and body["quarantined"] is False
            and all(type(body[key]) in (int, float) and math.isfinite(body[key]) and body[key] > 0
                    for key in ("started_monotonic", "started_utc", "charged_gpu_seconds"))
            and math.isclose(body["charged_gpu_seconds"], charge, rel_tol=0, abs_tol=0.000001),
            "M1_UPSTREAM_BUDGET_NOT_CLOSED_OR_CHANGED")


def _verify_m1(directory, proposal_path, approval_path, proposal_sha256, approval_sha256,
               upstream_paths, installation_sha256):
    require(_is_sha(proposal_sha256) and _is_sha(approval_sha256) and _is_sha(installation_sha256),
            "M1_EXTERNAL_AUTHORIZATION_PINS_REQUIRED")
    proposal_raw, approval_raw = _regular(proposal_path), _regular(approval_path)
    require(digest(proposal_raw) == proposal_sha256 and digest(approval_raw) == approval_sha256,
            "M1_EXACT_EXTERNAL_OWNER_APPROVAL_REQUIRED")
    proposal, approval = json.loads(proposal_raw), json.loads(approval_raw)
    require(set(proposal) == {"schema", "decision_id", "base_used", "cap", "new_admissions_max",
                             "allocations", "windows", "accounting_directory", "installation_sha256",
                             "upstream", "operations"}
            and proposal["schema"] == "hospital-m1-continuation.v1"
            and proposal["decision_id"] == M1_DECISION
            and type(proposal["base_used"]) is int and proposal["base_used"] == M1_BASE_USED
            and type(proposal["cap"]) is int and proposal["cap"] == M1_CAP
            and type(proposal["new_admissions_max"]) is int and proposal["new_admissions_max"] == 24
            and proposal["allocations"] == M1_ALLOCATIONS
            and proposal["installation_sha256"] == installation_sha256
            and set(approval) == {"schema", "decision_id", "proposal_sha256", "status"}
            and approval == {"schema": "hospital-m1-owner-approval.v1", "decision_id": M1_DECISION,
                             "proposal_sha256": proposal_sha256,
                             "status": "EXPLICIT_OWNER_APPROVED_NOT_ACTIVATED"},
            "M1_AUTHORIZATION_SCOPE_INVALID")
    directory = _direct(directory)
    require(Path(proposal["accounting_directory"]).is_absolute()
            and _direct(proposal["accounting_directory"]) == directory,
            "M1_SINGLE_AUTHORIZED_ACCOUNTING_DIRECTORY_REQUIRED")
    expected_windows = {key: {"profile": profile, "gpu_index": 0, "gpu_seconds_cap": 10800,
                              "wall_seconds_cap": 14400, "refund_unused": False, "renew": False}
                        for key, profile in M1_WINDOWS.items()}
    require(proposal["windows"] == expected_windows
            and all(type(value) is int for value in proposal["allocations"].values())
            and all(type(window[key]) is int for window in proposal["windows"].values()
                    for key in ("gpu_index", "gpu_seconds_cap", "wall_seconds_cap")),
            "M1_EXACT_TWO_NAMED_WINDOWS_REQUIRED")
    require(set(upstream_paths) == set(proposal["upstream"]) == M1_ANCHORS
            and all(_is_sha(value) for value in proposal["upstream"].values()), "M1_CLOSURE_ANCHORS_REQUIRED")
    paths = {key: _direct(path) for key, path in upstream_paths.items()}
    require(directory not in {path.parent for path in paths.values()}, "M1_OLD_ACCOUNTING_DIRECTORY_MUST_NOT_BE_REUSED")
    upstream = {key: _regular(path) for key, path in paths.items()}
    require(all(digest(raw) == proposal["upstream"][key] for key, raw in upstream.items())
            and digest(upstream["batch_ledger"]) == M1_UPSTREAM_LEDGER_SHA,
            "M1_PINNED_UPSTREAM_BYTES_CHANGED")
    manifest, old_jobs = _prior_batch(upstream["batch_ledger"])
    _closed_budget(upstream["original_budget"], manifest, 4772.230)
    _closed_budget(upstream["second_budget"], manifest, 9800.644)
    demo = upstream["demo_requests"]
    require(demo.endswith(b"\n") and len(demo.splitlines()) == 1, "M1_OLD_DEMO_MUST_HAVE_ZERO_INTENTS")
    row = json.loads(demo)
    require(row == {"state": "ANCHOR", "prior_ledger_sha256": M1_UPSTREAM_LEDGER_SHA,
                    "base_used": 525, "cap": 529, "sequence": 1, "previous": "0" * 64,
                    "hash": digest(canonical({k: v for k, v in row.items() if k != "hash"}))},
            "M1_ZERO_DEMO_JOURNAL_CHAIN_INVALID")
    marker, complete, ready = (json.loads(upstream[key]) for key in
                               ("demo_activation", "demo_complete", "demo_ready"))
    legacy_complete = digest(upstream["demo_complete"]) == M1_LEGACY_DEMO_COMPLETE_SHA
    require(marker["prior_used"] == 525 and marker["cap"] == 529
            and marker["prior_ledger_sha256"] == M1_UPSTREAM_LEDGER_SHA
            and type(marker.get("run")) is str and marker["run"]
            and complete.get("cleanup_confirmed") is True
            and complete.get("conservative_gpu_reserved_seconds") == 2430
            and not complete.get("logging_blocked") and not complete.get("error_class")
            and (legacy_complete or (
                complete.get("listener_closed") is True
                and set(complete.get("cleanup_components", {}))
                    == {"supervisor_close", "child_terminal_reap", "gpu_monitor", "disk_monitor"}
                and all(value.get("confirmed") is True for value in complete["cleanup_components"].values())))
            and ready.get("status") == "LOADED_NOT_YET_INFERENCE_VALIDATED"
            and ready.get("gpu_uuid") == M1_GPU0 and ready.get("prior_used") == 525
            and ready.get("cap") == 529 and len(ready.get("models", [])) == 3
            and {item["model_id"] for item in ready["models"]}
                == {"uspec-uwf-grading", "retfound-aptos5", "prism-dr-5fold"}
            and all(type(item.get("forward_attempts_during_load")) is int
                    and item["forward_attempts_during_load"] == 0 for item in ready["models"]),
            "M1_FINITE_DEMO_CLOSURE_OR_RESERVATION_INVALID")
    jobs = proposal["operations"]
    require(type(jobs) is list and len(jobs) == 24 and len({job["job_id"] for job in jobs}) == 24
            and len({job["operation_id"] for job in jobs}) == 24
            and Counter(job["purpose"] for job in jobs) == M1_ALLOCATIONS,
            "M1_EXACT_24_OPERATIONS_REQUIRED")
    fields = {"job_id", "operation_id", "purpose", "window_id", "source_sha256", "model_id",
              "modality", "model_pins_sha256", "parameters_sha256", "preprocessing_id"}
    for job in jobs:
        require(set(job) == fields and _is_sha(job["job_id"]) and job["job_id"] not in old_jobs
                and job["job_id"] == digest(canonical({k: v for k, v in job.items() if k != "job_id"}))
                and all(_is_sha(job[key]) for key in ("source_sha256", "model_pins_sha256", "parameters_sha256"))
                and all(type(job[key]) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", job[key])
                        for key in ("operation_id", "preprocessing_id"))
                and job["window_id"] in M1_WINDOWS and job["purpose"] in M1_ALLOCATIONS
                and (job["purpose"] != "server_acceptance" or job["window_id"] == M1_SERVER)
                and (job["purpose"] != "local_acceptance" or job["window_id"] == M1_LOCAL)
                and (job["model_id"], job["modality"]) in {
                    ("uspec-uwf-grading", "UWF"), ("retfound-aptos5", "CFP"),
                    ("prism-dr-5fold", "UWF"), ("prism-dr-5fold", "CFP")},
                "M1_OPERATION_SCOPE_OR_IDENTITY_INVALID")
    return {"proposal": proposal, "proposal_raw": proposal_raw, "approval_raw": approval_raw,
            "proposal_sha256": proposal_sha256, "approval_sha256": approval_sha256,
            "upstream": upstream, "paths": paths, "proposal_path": _direct(proposal_path),
            "approval_path": _direct(approval_path), "manifest": digest(canonical(jobs))}


class BatchLedger:
    """One owner only. Stale lock/quarantine is never cleared automatically."""

    def __init__(self, directory, *, jobs, manifest_sha256, _continuation=None):
        require(re.fullmatch(r"[a-f0-9]{64}", manifest_sha256) is not None, "MANIFEST_DIGEST_REQUIRED")
        if _continuation is not None:
            context = _continuation
            _continuation = _verify_m1(directory, context["proposal_path"], context["approval_path"],
                context["proposal_sha256"], context["approval_sha256"], context["paths"],
                context["proposal"]["installation_sha256"])
            require(jobs == _continuation["proposal"]["operations"]
                    and manifest_sha256 == _continuation["manifest"], "M1_VERIFIED_OPERATIONS_REQUIRED")
        self.directory = Path(directory)
        self.jobs = {job["job_id"]: deepcopy(job) for job in jobs}
        require(len(self.jobs) == len(jobs) and 0 < len(jobs) <= 480, "UNIQUE_BOUNDED_JOBS_REQUIRED")
        self.manifest_sha256 = manifest_sha256
        self.continuation = _continuation
        self.base_used, self.cap = (M1_BASE_USED, M1_CAP) if _continuation is not None else (BASE_USED, CAP)
        self._admitting = False
        self._window_budget = None
        self.lock = RLock()
        self.states, self.rows, self.attempts = {}, [], 0
        self.owned_lock = None
        self.poisoned = False
        self.journal_sha = None
        self.allowed_job_ids = None
        self.directory.mkdir(parents=True, exist_ok=True)
        require(not self.directory.is_symlink(), "LEDGER_SYMLINK_REJECTED")
        self._reload()

    @classmethod
    def for_continuation(cls, directory, *, proposal_path, approval_path, proposal_sha256,
                         approval_sha256, upstream_paths, installation_sha256):
        """Open only an externally pinned, independently verified M1 continuation.

        This is accounting only: no window, worker or inference is activated.
        The caller must obtain the expected hashes from the explicit owner
        approval channel, never from an adjacent self-declared hash file.
        """
        verified = _verify_m1(directory, proposal_path, approval_path, proposal_sha256,
                              approval_sha256, upstream_paths, installation_sha256)
        return cls(directory, jobs=verified["proposal"]["operations"],
                   manifest_sha256=verified["manifest"], _continuation=verified)

    def _check_continuation(self):
        context = self.continuation
        require(context is not None and self.base_used == M1_BASE_USED and self.cap == M1_CAP
                and digest(canonical(list(self.jobs.values()))) == self.manifest_sha256 == context["manifest"]
                and context["proposal"] == json.loads(context["proposal_raw"])
                and _direct(self.directory) == _direct(context["proposal"]["accounting_directory"]),
                "M1_CONTINUATION_CONTEXT_CHANGED")
        require(_regular(context["proposal_path"]) == context["proposal_raw"]
                and _regular(context["approval_path"]) == context["approval_raw"]
                and all(_regular(path) == context["upstream"][key] for key, path in context["paths"].items()),
                "M1_APPROVAL_OR_UPSTREAM_CHANGED")

    def _origin(self):
        value = {"manifest": self.manifest_sha256, "budget_required": self.continuation is not None}
        if self.continuation is not None:
            value["continuation"] = {"schema": "hospital-m1-accounting-origin.v1",
                "proposal_sha256": self.continuation["proposal_sha256"],
                "approval_sha256": self.continuation["approval_sha256"],
                "base_used": M1_BASE_USED, "cap": M1_CAP,
                "upstream": self.continuation["proposal"]["upstream"],
                "prior_gpu_seconds_preserved": 17002.874}
        return value

    def _head(self, journal_sha, seq, tail):
        return {"manifest": self.manifest_sha256, "proposal_sha256": self.continuation["proposal_sha256"],
                "journal_sha256": journal_sha, "seq": seq, "tail": tail}

    def _write_head(self, value):
        pending = self.directory / "JOURNAL_HEAD.pending"
        _new_file(pending, canonical(value))
        os.replace(pending, self.directory / "JOURNAL_HEAD.json")

    def _check_head(self):
        if self.continuation is not None and (self.directory / "ACCOUNTING.json").exists():
            require(json.loads(_regular(self.directory / "JOURNAL_HEAD.json"))
                    == self._head(self.journal_sha, len(self.rows), self.rows[-1]["hash"] if self.rows else "0" * 64),
                    "M1_JOURNAL_HIGH_WATER_MISMATCH_NO_REPLAY")

    def _reload(self):
        self.states, self.rows, self.attempts = {}, [], 0
        path = self.directory / "LEDGER.jsonl"
        marker = self.directory / "ACCOUNTING.json"
        require(not marker.exists() or path.is_file(), "MISSING_PRIOR_JOURNAL_QUARANTINED")
        raw = b""
        if path.exists():
            require(not path.is_symlink() and path.stat().st_size <= 10*1024**2, "LEDGER_INVALID")
            raw = path.read_bytes()
            require(not raw or raw.endswith(b"\n"), "TORN_LEDGER_QUARANTINE_NO_REPLAY")
            for line in raw.splitlines():
                self._accept(json.loads(line), replay=True)
        self.journal_sha = digest(raw)
        self._check_head()

    def assert_owner(self):
        require(not self.poisoned and self.owned_lock is not None, "EXCLUSIVE_UNPOISONED_LEDGER_OWNER_REQUIRED")
        lock = self.directory / "SESSION.lock"
        require(not lock.is_symlink() and lock.read_bytes() == self.owned_lock, "LEDGER_OWNER_CHANGED_OR_RELEASED")
        path = self.directory / "LEDGER.jsonl"
        require(path.is_file() and not path.is_symlink() and digest(path.read_bytes()) == self.journal_sha, "LEDGER_WRITE_STATE_UNCERTAIN")
        if self.continuation is not None:
            self._check_continuation()
            require(not (self.directory / "HANDOVER.lock").exists(), "M1_SOURCE_PERMANENTLY_FENCED")
            self._check_head()
            self.accounting()

    def accounting(self):
        path = self.directory / "ACCOUNTING.json"
        require(path.is_file() and not path.is_symlink(), "ACCOUNTING_ORIGIN_REQUIRED")
        value = json.loads(path.read_bytes())
        if self.continuation is not None:
            require(value == self._origin(), "M1_ACCOUNTING_ORIGIN_CHANGED")
            require(_regular(self.directory / "PROPOSAL.json") == self.continuation["proposal_raw"]
                    and _regular(self.directory / "APPROVAL.json") == self.continuation["approval_raw"]
                    and all(_regular(self.directory / "upstream" / (key + ".original")) == raw
                            for key, raw in self.continuation["upstream"].items()),
                    "M1_PRESERVED_CLOSURE_CHANGED")
            return value
        require(set(value) == {"manifest", "budget_required"} and value["manifest"] == self.manifest_sha256
                and type(value["budget_required"]) is bool, "ACCOUNTING_ORIGIN_CHANGED")
        return value

    def require_budget_file(self):
        """Publish requirement BEFORE budget creation; a crash fails closed."""
        with self.lock:
            self.assert_owner()
            value = self.accounting()
            require(not value["budget_required"], "MISSING_PRIOR_BUDGET_NO_RESET")
            value["budget_required"] = True
            pending = self.directory / "ACCOUNTING.pending"
            require(not pending.exists(), "ACCOUNTING_WRITE_UNCERTAIN")
            try:
                with pending.open("xb") as out:
                    out.write(canonical(value))
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(pending, self.directory / "ACCOUNTING.json")
            except BaseException:
                self.poisoned = True
                raise

    def _accept(self, row, *, replay=False):
        require(isinstance(row, dict) and set(row) == {"seq", "manifest", "job_id", "state", "reason", "artifact_sha256", "previous", "hash"}, "LEDGER_SCHEMA_INVALID")
        require(row["seq"] == len(self.rows)+1 and row["manifest"] == self.manifest_sha256, "LEDGER_IDENTITY_CHANGED")
        require(row["job_id"] in self.jobs and row["reason"] in REASONS, "LEDGER_JOB_OR_REASON_INVALID")
        previous = self.rows[-1]["hash"] if self.rows else "0"*64
        require(row["previous"] == previous and row["hash"] == digest(canonical({key: value for key, value in row.items() if key != "hash"})), "LEDGER_CHAIN_INVALID")
        require(row["state"] in TRANSITIONS.get(self.states.get(row["job_id"]), set()), "NO_RETRY_OR_DUPLICATE_JOB")
        artifact = row["artifact_sha256"]
        require(artifact is None or type(artifact) is str and re.fullmatch(r"[a-f0-9]{64}", artifact), "ARTIFACT_DIGEST_INVALID")
        if row["state"] in {"RESPONSE_RETAINED", "PASS_READBACK"}:
            require(artifact is not None, "RESPONSE_OR_READBACK_DIGEST_REQUIRED")
        next_attempts = self.attempts + (row["state"] == "ATTEMPT_INTENT")
        require(self.base_used + next_attempts <= self.cap, "APPROVED_BATCH_QUOTA_EXHAUSTED")
        if self.continuation is not None:
            require(row["state"] != "ATTEMPT_INTENT" or _is_sha(artifact), "M1_REQUEST_DIGEST_REQUIRED")
        if not replay:
            self.assert_owner()
            if self.continuation is not None:
                budget = self._window_budget
                require(budget is not None and self.jobs[row["job_id"]]["window_id"] == budget.session_id,
                        "M1_OPERATION_OUTSIDE_ACTIVE_WINDOW")
                require(row["state"] != "ATTEMPT_INTENT" or self._admitting, "M1_ADMISSION_GATE_REQUIRED")
                if self.states.get(row["job_id"]) is None:
                    budget.check()
            require(self.allowed_job_ids is None or row["job_id"] in self.allowed_job_ids,
                    "JOB_OUTSIDE_APPROVED_SESSION_SCOPE")
            raw = canonical(row)+b"\n"
            path = self.directory / "LEDGER.jsonl"
            require(not path.is_symlink(), "LEDGER_SYMLINK_REJECTED")
            current = path.stat().st_size if path.exists() else 0
            require(current + len(raw) <= 10*1024**2, "LEDGER_LIMIT")
            try:
                with path.open("ab") as output:
                    require(output.write(raw) == len(raw), "PARTIAL_LEDGER_WRITE")
                    output.flush()
                    os.fsync(output.fileno())
                self.journal_sha = digest(path.read_bytes())
                if self.continuation is not None:
                    self._write_head(self._head(self.journal_sha, row["seq"], row["hash"]))
            except BaseException:
                self.poisoned = True
                raise
        self.rows.append(row)
        self.states[row["job_id"]] = row["state"]
        self.attempts = next_attempts

    def acquire(self):
        require(self.owned_lock is None, "LEDGER_ALREADY_OWNED")
        if self.continuation is not None:
            self._check_continuation()
            require(not (self.directory / "HANDOVER.lock").exists(), "M1_SOURCE_PERMANENTLY_FENCED")
            require(not (self.directory / "M1_WINDOW_ACTIVATION.lock").exists(),
                    "M1_PARTIAL_WINDOW_ACTIVATION_PRESERVED")
        require(not (self.directory / "OWNER_RECOVERY.lock").exists(),
                "INCOMPLETE_OWNER_RECOVERY_PRESERVED")
        require(not (self.directory / "SESSION_ACTIVATION.lock").exists(),
                "INCOMPLETE_SESSION_ACTIVATION_PRESERVED")
        path = self.directory / "SESSION.lock"
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            raw = canonical({"manifest": self.manifest_sha256, "owner_pid": os.getpid(), "epoch": uuid4().hex})
            require(os.write(fd, raw) == len(raw), "PARTIAL_LEDGER_LOCK_WRITE_QUARANTINED")
            os.fsync(fd)
            self.owned_lock = raw
        finally:
            os.close(fd)
        try:
            marker = self.directory / "ACCOUNTING.json"
            if not marker.exists():
                # A pre-existing unmarked accounting file is uncertain, never
                # adopted as a new session or used to reset consumed work.
                require(not (self.directory / "LEDGER.jsonl").exists()
                        and not (self.directory / "BUDGET.json").exists(), "UNMARKED_ACCOUNTING_NO_RESET")
                if self.continuation is not None:
                    require(not any((self.directory / name).exists() for name in
                                    ("PROPOSAL.json", "APPROVAL.json", "upstream", "JOURNAL_HEAD.json", "windows")),
                            "M1_PARTIAL_ORIGIN_NO_RESET")
                    _new_file(self.directory / "PROPOSAL.json", self.continuation["proposal_raw"])
                    _new_file(self.directory / "APPROVAL.json", self.continuation["approval_raw"])
                    (self.directory / "upstream").mkdir()
                    for key, raw in self.continuation["upstream"].items():
                        _new_file(self.directory / "upstream" / (key + ".original"), raw)
                    _new_file(self.directory / "JOURNAL_HEAD.json", canonical(self._head(digest(b""), 0, "0" * 64)))
                for name, data in (("LEDGER.jsonl", b""), ("ACCOUNTING.json", canonical(self._origin()))):
                    with (self.directory / name).open("xb") as output:
                        output.write(data)
                        output.flush()
                        os.fsync(output.fileno())
            self.accounting()
            self._reload()  # authoritative replay AFTER acquiring ownership
        except BaseException:
            self.poisoned = True
            raise

    def close(self, *, cleanup_confirmed):
        # Failure retains lock/quarantine. Never conclude from file/PID absence.
        require(cleanup_confirmed is True and self.owned_lock is not None, "CLEANUP_UNCONFIRMED_LOCK_PRESERVED")
        require(not self.poisoned, "UNCERTAIN_ACCOUNTING_LOCK_PRESERVED")
        if self.continuation is not None:
            self.assert_owner()
            require(not self.uncertain(), "M1_UNCERTAIN_INTENT_OWNER_PRESERVED")
            self._require_closed_window()
        path = self.directory / "SESSION.lock"
        require(not path.is_symlink() and path.read_bytes() == self.owned_lock, "LEDGER_OWNER_CHANGED")
        path.unlink()
        self.owned_lock = None

    def append(self, job_id, state, *, reason=None, artifact_sha256=None):
        with self.lock:
            row = {"seq": len(self.rows)+1, "manifest": self.manifest_sha256, "job_id": job_id, "state": state, "reason": reason, "artifact_sha256": artifact_sha256, "previous": self.rows[-1]["hash"] if self.rows else "0"*64}
            row["hash"] = digest(canonical(row))
            self._accept(row)
            return row["hash"]

    def admit(self, job_id, *, request_sha256, budget):
        """Durable single-use intent BEFORE a caller may dispatch execute/predict.

        The runtime still must consume the returned admission ID once at its
        qualified native entry fence. This module never performs a dispatch.
        """
        with self.lock:
            self.assert_owner()
            require(self.continuation is not None and _is_sha(request_sha256), "M1_REQUEST_DIGEST_REQUIRED")
            require(budget is self._window_budget and budget.ledger is self, "M1_EXACT_WINDOW_BUDGET_REQUIRED")
            now = budget.check()
            require(budget.body["active"] is not None and not self.uncertain(),
                    "M1_FUNDED_IDLE_ADMISSION_REQUIRED")
            require(now < budget.body["active"]["deadline"], "M1_GPU_ENTRY_DEADLINE_EXHAUSTED")
            require(job_id in self.jobs and self.jobs[job_id]["window_id"] == budget.session_id,
                    "M1_OPERATION_OUTSIDE_ACTIVE_WINDOW")
            try:
                self._admitting = True
                admission = self.append(job_id, "ATTEMPT_INTENT", artifact_sha256=request_sha256)
            finally:
                self._admitting = False
            return {"admission_id": admission, "job_id": job_id, "window_id": budget.session_id,
                    "request_sha256": request_sha256, "global_used": self.base_used + self.attempts}

    def _require_closed_window(self):
        from batch_budget import continuation_window_context
        if (self.directory / "windows" / M1_SERVER).exists():
            _, _, body = continuation_window_context(self, M1_SERVER)
            require(body["active"] is None and body["quarantined"] is False and body["window_closed"] is True,
                    "M1_WINDOW_MUST_BE_CLOSED")
        require(not (self.directory / "windows" / M1_LOCAL).exists(), "M1_LOCAL_ADOPTION_NOT_QUALIFIED")

    def fence_handover(self, *, destination_installation_sha256):
        """Permanently fence this source; Local adoption is NOT implemented.

        Keeps the old owner lock and all data. No copied bundle is authority to
        activate Local, and no software-only offline clone protection is claimed.
        """
        with self.lock:
            self.assert_owner()
            require(self.continuation is not None and _is_sha(destination_installation_sha256),
                    "M1_APPROVED_DESTINATION_IDENTITY_REQUIRED")
            require((self.directory / "windows" / M1_SERVER).is_dir() and not self.uncertain(),
                    "M1_CLOSED_SOURCE_WITH_NO_UNCERTAIN_INTENTS_REQUIRED")
            self._require_closed_window()
            server = self.directory / "windows" / M1_SERVER
            value = {"schema": "hospital-m1-source-handover.v1", "status": "SOURCE_FENCED_LOCAL_ADOPTION_NOT_QUALIFIED",
                "manifest": self.manifest_sha256, "proposal_sha256": self.continuation["proposal_sha256"],
                "approval_sha256": self.continuation["approval_sha256"],
                "destination_installation_sha256": destination_installation_sha256,
                "journal_sha256": self.journal_sha, "seq": len(self.rows),
                "server_budget_sha256": digest(_regular(server / "BUDGET.json")),
                "server_activation_sha256": digest(_regular(server / "COMPLETE.json")),
                "journal_head_sha256": digest(_regular(self.directory / "JOURNAL_HEAD.json")),
                "upstream": deepcopy(self.continuation["proposal"]["upstream"]),
                "tail": self.rows[-1]["hash"] if self.rows else "0" * 64,
                "global_used": self.base_used + self.attempts,
                "owner_lock_sha256": digest(self.owned_lock),
                "remaining_job_ids": [row["job_id"] for row in self.pending()],
                "local_activation_available": False}
            try:
                _new_file(self.directory / "HANDOVER.lock", canonical(value))
                _new_file(self.directory / "HANDOVER_EXPORT.json", canonical(value))
            except BaseException:
                self.poisoned = True
                raise
            return deepcopy(value)

    def restrict_to_jobs(self, job_ids):
        """Narrow this owned handle without removing any historical rows."""
        self.assert_owner()
        ids = frozenset(job_ids)
        require(len(ids) == len(job_ids) == 175 and ids <= self.jobs.keys()
                and all(row["job_id"] in ids for row in self.pending()),
                "EXACT_APPROVED_REMAINING_SCOPE_REQUIRED")
        require(self.allowed_job_ids is None or self.allowed_job_ids == ids,
                "SESSION_JOB_SCOPE_CANNOT_CHANGE")
        self.allowed_job_ids = ids

    def pending(self):
        # An intent/response without final outcome is uncertain, never pending.
        require(not self.poisoned, "UNCERTAIN_ACCOUNTING_NO_ADMISSION")
        return [deepcopy(job) for key, job in self.jobs.items() if key not in self.states]

    def uncertain(self):
        return [key for key, state in self.states.items() if state in {"ATTEMPT_INTENT", "RESPONSE_RETAINED", "SENT_OR_UNCERTAIN"}]

    def summary(self):
        return {"attempts_in_batch": self.attempts, "global_used": self.base_used+self.attempts,
                "cap": self.cap, "not_sent": len(self.pending()), "uncertain_jobs": len(self.uncertain()), "automatic_retries": 0}
