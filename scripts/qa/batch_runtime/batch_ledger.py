"""Fsynced append-only attempt ledger for the approved finite demo batch.

No inference transport, process launch, credentials or database access here.
An attempt is consumed before a call, including an ambiguous/failed call.
"""

import hashlib
import json
import os
from pathlib import Path
import re
from copy import deepcopy
from threading import RLock
from uuid import uuid4

BASE_USED, CAP = 49, 529
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


class BatchLedger:
    """One owner only. Stale lock/quarantine is never cleared automatically."""

    def __init__(self, directory, *, jobs, manifest_sha256):
        require(re.fullmatch(r"[a-f0-9]{64}", manifest_sha256) is not None, "MANIFEST_DIGEST_REQUIRED")
        self.directory = Path(directory)
        self.jobs = {job["job_id"]: deepcopy(job) for job in jobs}
        require(len(self.jobs) == len(jobs) and 0 < len(jobs) <= 480, "UNIQUE_BOUNDED_JOBS_REQUIRED")
        self.manifest_sha256 = manifest_sha256
        self.lock = RLock()
        self.states, self.rows, self.attempts = {}, [], 0
        self.owned_lock = None
        self.poisoned = False
        self.journal_sha = None
        self.allowed_job_ids = None
        self.directory.mkdir(parents=True, exist_ok=True)
        require(not self.directory.is_symlink(), "LEDGER_SYMLINK_REJECTED")
        self._reload()

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

    def assert_owner(self):
        require(not self.poisoned and self.owned_lock is not None, "EXCLUSIVE_UNPOISONED_LEDGER_OWNER_REQUIRED")
        lock = self.directory / "SESSION.lock"
        require(not lock.is_symlink() and lock.read_bytes() == self.owned_lock, "LEDGER_OWNER_CHANGED_OR_RELEASED")
        path = self.directory / "LEDGER.jsonl"
        require(path.is_file() and not path.is_symlink() and digest(path.read_bytes()) == self.journal_sha, "LEDGER_WRITE_STATE_UNCERTAIN")

    def accounting(self):
        path = self.directory / "ACCOUNTING.json"
        require(path.is_file() and not path.is_symlink(), "ACCOUNTING_ORIGIN_REQUIRED")
        value = json.loads(path.read_bytes())
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
        require(BASE_USED + next_attempts <= CAP, "APPROVED_BATCH_QUOTA_EXHAUSTED")
        if not replay:
            self.assert_owner()
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
            except BaseException:
                self.poisoned = True
                raise
        self.rows.append(row)
        self.states[row["job_id"]] = row["state"]
        self.attempts = next_attempts

    def acquire(self):
        require(self.owned_lock is None, "LEDGER_ALREADY_OWNED")
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
                for name, data in (("LEDGER.jsonl", b""), ("ACCOUNTING.json", canonical({"manifest": self.manifest_sha256, "budget_required": False}))):
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
        return {"attempts_in_batch": self.attempts, "global_used": BASE_USED+self.attempts, "cap": CAP, "not_sent": len(self.pending()), "uncertain_jobs": len(self.uncertain()), "automatic_retries": 0}
