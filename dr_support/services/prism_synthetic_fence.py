"""Offline single-writer SYNTHETIC authority; never registered in the app.

Owns immutable in-memory snapshots and a bounded, fsynced quarantine journal.
Every synthetic mutation uses this facade. It does not fence external files,
the real app/store, multiple processes, or arbitrary model workers. Authentication
of status is the trusted channel's responsibility, not a JSON hash assertion.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
from threading import RLock

from dr_support.services.prism_remote_transport import TransportError, canonical, require_sha256, sha

FIELDS = ("scope", "image_id", "case_revision", "source_sha256", "admission_sha256",
          "recorded_source_identity", "admission", "preparation_context", "model_pins")
WRITERS = frozenset({"case", "admission", "integrity", "revision", "preparation", "workspace", "provider", "source"})
STATUS_KEYS = ("epoch", "job_id", "ticket_id", "plan_sha256", "pins", "challenge_id")


class SyntheticFenceAuthority:
    """Fail-closed restart model, one writer, no timeout/epoch-based unlock.

    The directory must be a private test directory. Stale lock files are never
    removed automatically: a crash may need operator-confirmed single ownership.
    recover() uses the injected authenticated status reader for the OLD job; a
    new host epoch or missing old job cannot clear quarantine. No TTL exists.
    """
    def __init__(self, directory, *, authenticated_status_reader):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.closed = self.poisoned = False
        self.reader = authenticated_status_reader
        if not callable(self.reader):
            raise ValueError("TRUSTED_STATUS_READER_REQUIRED")
        self.lock_path = self.directory / "writer.lock"
        try:
            self.fd = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise TransportError("EXCLUSIVE_WRITER_NOT_ESTABLISHED", 503) from None
        self.lock_identity = os.fstat(self.fd)
        self.path = self.directory / "fence.json"
        self._snapshot = self._plan = self._wire = None
        self._generation = 0
        try:
            if self.path.exists():
                if self.path.stat().st_size > 65536:
                    raise ValueError("JOURNAL_LIMIT")
                value = json.loads(self.path.read_bytes())
                body = value["body"]
                if (set(value) != {"body", "sha256"} or sha(canonical(body)) != value["sha256"]
                        or set(body) != {"version", "state", "fence", "consumed"}
                        or body["version"] != 1 or body["state"] not in {"OPEN", "FENCED", "QUARANTINED"}
                        or not isinstance(body["consumed"], list) or len(body["consumed"]) > 128):
                    raise ValueError("INVALID_JOURNAL")
                for digest in body["consumed"]:
                    require_sha256(digest)
                if (body["state"] == "OPEN") != (body["fence"] is None):
                    raise ValueError("INVALID_FENCE_STATE")
                self._body = body
                if body["state"] != "OPEN":
                    # Recover BEFORE any mutation. No new snapshot can erase it.
                    self._body["state"] = "QUARANTINED"
                    self._persist()
            else:
                self._body = {"version": 1, "state": "OPEN", "fence": None, "consumed": []}
                self._persist()
        except BaseException:
            self.close()
            raise

    @property
    def body(self):
        """Inspection copy only; authoritative state has no public setter."""
        with self.lock:
            return deepcopy(self._body)

    def _persist(self):
        data = canonical({"body": self._body, "sha256": sha(canonical(self._body))})
        if len(data) > 65536:
            self.poisoned = True
            raise TransportError("JOURNAL_LIMIT", 503)
        # Interrupted writes leave the old journal (or fail closed on first
        # initialization); no grants can be issued before successful fsync.
        temporary = self.directory / "fence.pending"
        try:
            with temporary.open("wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            self.poisoned = True
            raise

    def _open(self):
        if self.closed or self.poisoned or self._body["state"] != "OPEN":
            raise TransportError("MUTATION_FENCED_OR_QUARANTINED")

    @staticmethod
    def _context(binding):
        context = {key: deepcopy(binding[key]) for key in FIELDS}
        recorded = context["recorded_source_identity"]
        require_sha256(context["source_sha256"])
        require_sha256(context["admission_sha256"])
        for key in ("case_source_sha256", "admission_source_sha256", "image_recorded_sha256"):
            require_sha256(recorded[key])
            if recorded[key] != context["source_sha256"]:
                raise TransportError("RECORDED_SOURCE_CONFLICT")
        if (context["admission"]["source_origin"] != "SYNTHETIC"
                or recorded["source_origin"] != "SYNTHETIC" or recorded["integrity_status"] != "OK"
                or recorded["case_revision"] != context["case_revision"]
                or recorded["admission_sha256"] != context["admission_sha256"]):
            raise TransportError("SYNTHETIC_RECORDED_AUTHORITY_REQUIRED")
        return context

    def stage(self, binding, *, original_bytes, wire_bytes):
        with self.lock:
            self._open()
            context = self._context(binding)
            if (not isinstance(original_bytes, bytes) or not isinstance(wire_bytes, bytes)
                    or not 0 < len(original_bytes) <= 20_000_000 or not 0 < len(wire_bytes) <= 20_000_000
                    or sha(original_bytes) != context["source_sha256"] or sha(wire_bytes) != binding["wire_sha256"]):
                raise TransportError("IMMUTABLE_RECORDED_SNAPSHOT_REQUIRED")
            self._snapshot = context
            self._wire = wire_bytes
            self._generation += 1
            self._plan = None

    def authorize_prepare(self, wire):
        with self.lock:
            self._open()
            if (self._snapshot is None or wire.source_type != "SYNTHETIC" or wire.data != self._wire
                    or wire.image_id != self._snapshot["image_id"]):
                raise TransportError("SYNTHETIC_SNAPSHOT_NOT_AUTHORIZED")

    def register_plan(self, binding):
        with self.lock:
            self._open()
            digest = sha(canonical(binding))
            if self._context(binding) != self._snapshot or binding["wire_sha256"] != sha(self._wire):
                raise TransportError("LOCAL_SOURCE_SCOPE_STALE")
            if digest in self._body["consumed"] or self._plan_key(binding) in self._body["consumed"]:
                raise TransportError("DURABLE_PLAN_REPLAY")
            self._plan = (digest, self._generation)

    @staticmethod
    def _plan_key(binding):
        return sha(canonical(["synthetic-plan-id", binding["scope"], binding["image_id"], binding["plan_id"]]))

    def mutate(self, writer):
        """All synthetic writers invalidate prepared plans; no bypass/setter."""
        with self.lock:
            self._open()
            if writer not in WRITERS:
                raise TransportError("UNRECOGNIZED_WRITER")
            self._generation += 1
            self._plan = None

    def acquire(self, binding, status, revalidate):
        with self.lock:
            self._open()
            digest = sha(canonical(binding))
            if (self._plan != (digest, self._generation) or self._context(binding) != self._snapshot
                    or status["state"] != "WAITING_SOURCE_FENCE" or status["forward_started"]
                    or status["terminal"] or status["plan_sha256"] != digest
                    or status["pins"] != binding["model_pins"] or not status["challenge_id"]):
                raise TransportError("LOCAL_SOURCE_SCOPE_STALE")
            plan_key = self._plan_key(binding)
            if digest in self._body["consumed"] or plan_key in self._body["consumed"] or len(self._body["consumed"]) > 126:
                raise TransportError("DURABLE_REPLAY_OR_SESSION_LIMIT")
            # Reentrant mutation inside revalidate also invalidates the plan.
            generation = self._generation
            revalidate()
            if generation != self._generation or self._plan != (digest, generation):
                raise TransportError("REVALIDATION_MUTATED_SOURCE")
            fence = {key: deepcopy(status[key]) for key in STATUS_KEYS}
            fence["fence_id"] = "synthetic_" + sha(canonical(fence))[:32]
            fence["source_context_sha256"] = sha(canonical(self._snapshot))
            self._body["consumed"].extend([digest, plan_key])
            self._body["state"], self._body["fence"] = "FENCED", fence
            self._persist()  # BEFORE returning permission to send any grant.
            return _Lease(self, fence["fence_id"])

    def _release_status(self, status):
        fence = self._body["fence"]
        if (not isinstance(status, dict) or fence is None
                or any(status.get(key) != fence[key] for key in STATUS_KEYS)
                or type(status.get("forward_started")) is not bool or type(status.get("terminal")) is not bool
                or status.get("state") not in {"FORWARD_STARTED", "COMPLETE", "FAILED", "ABORTED"}
                or status["terminal"] != (status["state"] in {"COMPLETE", "FAILED", "ABORTED"})
                or (status["state"] in {"FORWARD_STARTED", "COMPLETE"} and not status["forward_started"])
                or not (status.get("forward_started") is True
                        or (status.get("terminal") is True and status.get("state") in {"COMPLETE", "FAILED", "ABORTED"}))):
            raise TransportError("MATCHING_AUTHENTICATED_ENTRY_OR_TERMINAL_REQUIRED")
        self._body["state"], self._body["fence"] = "OPEN", None
        self._plan = None
        self._persist()

    def recover(self):
        with self.lock:
            if self.closed or self.poisoned:
                raise TransportError("AUTHORITY_CLOSED_OR_POISONED")
            if self._body["state"] == "OPEN":
                return
            # Trusted reader must authenticate old epoch/job status. No caller
            # supplied JSON, local timeout, cancel ACK, or new epoch is proof.
            self._release_status(self.reader(deepcopy(self._body["fence"])))

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            current = self.lock_path.stat()
            if (current.st_dev, current.st_ino) != (self.lock_identity.st_dev, self.lock_identity.st_ino):
                os.close(self.fd)
                raise TransportError("WRITER_LOCK_IDENTITY_CHANGED")
            os.close(self.fd)
            self.lock_path.unlink()  # ONLY this instance's exclusive lock.


class _Lease:
    def __init__(self, authority, fence_id):
        self.authority, self.fence_id = authority, fence_id

    def release(self, proof):
        with self.authority.lock:
            a = self.authority
            if a.closed or a.poisoned or not a._body["fence"] or a._body["fence"]["fence_id"] != self.fence_id:
                raise TransportError("STALE_FENCE_LEASE")
            if not isinstance(proof, dict) or proof.get("kind") != "AUTHENTICATED_STATUS":
                # Even NO_GRANT_SENT stays closed in this conservative facade.
                raise TransportError("MATCHING_AUTHENTICATED_ENTRY_OR_TERMINAL_REQUIRED")
            a._release_status(proof.get("status"))

    def quarantine(self, reason):
        with self.authority.lock:
            a = self.authority
            if a.closed or a.poisoned or not a._body["fence"] or a._body["fence"]["fence_id"] != self.fence_id:
                raise TransportError("STALE_FENCE_LEASE")
            a._body["state"] = "QUARANTINED"
            a._persist()
