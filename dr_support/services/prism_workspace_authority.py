"""Unregistered workspace authority; trusted ports do not qualify a deployment."""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import secrets
from threading import RLock
from types import SimpleNamespace

from .admission import is_inference_eligible
from .filesystem_privacy import has_reparse_component, private_hospital_root
from .prism_preview import PrismPreviewService, preparation_context
from .prism_remote_transport import TransportError, canonical, require_sha256, sha
from .source_identity import source_identity_reason
from .source_mutation_gate import SourceMutationGate
from .source_policy import source_allowed_for_model

STATUS_KEYS = ("epoch", "job_id", "ticket_id", "plan_sha256", "pins", "challenge_id")
CONTEXT_KEYS = {"workspace_id", "image_id", "case", "workspace", "admission", "source_sha256",
                "preparation_context", "model_pins", "runtime_context", "objects"}
PIN_KEYS = {"model_id", "source_revision", "preprocessing", "config_sha256", "checkpoint_sha256"}
LIMIT = 65536


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", value) is not None


def _same_objects(left, right):
    return len(left) == len(right) and all(a is b for a, b in zip(left, right, strict=True))


def _pins(value):
    if (not isinstance(value, dict) or set(value) != PIN_KEYS or value["model_id"] != "prism-dr-5fold"
            or not _identifier(value["source_revision"]) or not isinstance(value["preprocessing"], str)
            or not 0 < len(value["preprocessing"]) <= 1000
            or not isinstance(value["checkpoint_sha256"], dict) or not value["checkpoint_sha256"]):
        raise TransportError("REVIEWED_NONSECRET_MODEL_PINS_REQUIRED")
    require_sha256(value["config_sha256"])
    for name, digest in value["checkpoint_sha256"].items():
        if not _identifier(name):
            raise TransportError("REVIEWED_NONSECRET_MODEL_PINS_REQUIRED")
        require_sha256(digest)


class WorkspaceAuthority:
    """Single owned directory, explicit DB fence, no registration or inference."""

    def __init__(self, directory, *, context_reader, database_fence, authenticated_status_reader):
        self.gate = SourceMutationGate()
        self.lock = RLock()
        self.closed = self.poisoned = False
        self._locked = False
        self._fd = self._permit = self._db_permit = None
        self._stage = self._plan = None
        if (not callable(context_reader) or not callable(authenticated_status_reader)
                or any(not callable(getattr(database_fence, key, None)) for key in ("read", "acquire", "recover"))):
            raise TransportError("INTERNAL_TRUSTED_AUTHORITY_PORTS_REQUIRED", 503)
        self.context_reader, self.database, self.reader = context_reader, database_fence, authenticated_status_reader
        self.directory = Path(directory)
        if not self.directory.is_absolute() or ".." in self.directory.parts:
            raise TransportError("PRIVATE_ABSOLUTE_AUTHORITY_DIRECTORY_REQUIRED", 503)
        try:
            if has_reparse_component(self.directory.parent):
                raise TransportError("REDIRECTED_AUTHORITY_DIRECTORY_REJECTED", 503)
            try:
                self.directory.lstat()
            except FileNotFoundError:
                pass
            else:
                if has_reparse_component(self.directory):
                    raise TransportError("REDIRECTED_AUTHORITY_DIRECTORY_REJECTED", 503)
        except OSError:
            raise TransportError("EXISTING_UNREDIRECTED_AUTHORITY_PARENT_REQUIRED", 503) from None
        self.directory.mkdir(mode=0o700, exist_ok=True)
        self.owner_path = self.directory / "workspace-authority.owner"
        self.path, self.pending = self.directory / "workspace-authority.json", self.directory / "workspace-authority.pending"
        try:
            if has_reparse_component(self.directory) or not private_hospital_root(self.directory):
                raise TransportError("PRIVATE_AUTHORITY_DIRECTORY_REQUIRED", 503)
            flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            try:
                self._fd = os.open(self.owner_path, flags | os.O_CREAT | os.O_EXCL, 0o600)
                fresh = True
            except FileExistsError:
                if has_reparse_component(self.owner_path):
                    raise TransportError("REDIRECTED_AUTHORITY_OWNER_REJECTED", 503)
                self._fd = os.open(self.owner_path, flags)
                fresh = False
            self._owner_stat = os.fstat(self._fd)
            self._os_lock(True)
            self._locked = True
            self._check_owner()
            if fresh:
                self.owner_id = secrets.token_hex(32)
                os.write(self._fd, self.owner_id.encode("ascii"))
                os.fsync(self._fd)
            else:
                os.lseek(self._fd, 0, os.SEEK_SET)
                self.owner_id = os.read(self._fd, 65).decode("ascii")
                require_sha256(self.owner_id)
            self._check_owner()
            if self.pending.exists() or (not fresh and not self.path.exists()):
                raise TransportError("PARTIAL_OR_MISSING_AUTHORITY_JOURNAL_RETAINED", 503)
            if self.path.exists():
                self._body = self._load()
            else:
                self._body = {"version": 1, "owner_id": self.owner_id, "state": "OPEN", "fence": None, "consumed": []}
                self._persist()
            durable = self.database.read()
            local = self._body["fence"]
            if durable is not None:
                self._validate_fence(durable)
                if local is not None and local != durable:
                    raise TransportError("LOCAL_DATABASE_FENCE_SCOPE_MISMATCH", 503)
                self._body["fence"] = deepcopy(durable)
                self._consume(durable["plan_sha256"], durable["local_plan_key"])
            if self._body["fence"] is not None:
                self._permit = self.gate.begin_entry(expected_generation=0)
                self._permit.quarantine()
                self._body["state"] = "QUARANTINED"
                self._persist()
        except BaseException:
            self.close()
            raise

    def _os_lock(self, acquire):
        os.lseek(self._fd, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._fd, msvcrt.LK_NBLCK if acquire else msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB if acquire else fcntl.LOCK_UN)
        except OSError:
            raise TransportError("EXCLUSIVE_OS_AUTHORITY_LOCK_REQUIRED", 503) from None

    def _check_owner(self):
        if self.closed or self._fd is None:
            raise TransportError("AUTHORITY_CLOSED", 503)
        try:
            current = self.owner_path.lstat()
            valid = (not has_reparse_component(self.owner_path) and private_hospital_root(self.directory)
                     and (current.st_dev, current.st_ino) == (self._owner_stat.st_dev, self._owner_stat.st_ino))
        except OSError:
            valid = False
        if not valid:
            self.poisoned = True
            raise TransportError("AUTHORITY_OWNER_OR_PRIVACY_CHANGED", 503)

    @staticmethod
    def _validate_fence(value):
        if (not isinstance(value, dict) or set(value) != {*STATUS_KEYS, "fence_id", "source_context_sha256", "local_plan_key"}
                or any(not _identifier(value[key]) for key in ("epoch", "job_id", "ticket_id", "challenge_id", "fence_id"))):
            raise TransportError("INVALID_DURABLE_AUTHORITY_SCOPE", 503)
        for key in ("plan_sha256", "source_context_sha256", "local_plan_key"):
            require_sha256(value[key])
        _pins(value["pins"])

    def _load(self):
        try:
            if has_reparse_component(self.path) or self.path.stat().st_size > LIMIT:
                raise ValueError()
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError()
                    result[key] = value
                return result
            envelope = json.loads(self.path.read_bytes(), object_pairs_hook=unique)
            body = envelope["body"]
            if (set(envelope) != {"body", "sha256"} or sha(canonical(body)) != envelope["sha256"]
                    or set(body) != {"version", "owner_id", "state", "fence", "consumed"}
                    or type(body["version"]) is not int or body["version"] != 1 or body["owner_id"] != self.owner_id
                    or body["state"] not in {"OPEN", "ACQUIRING", "FENCED", "QUARANTINED"}
                    or (body["state"] == "OPEN") != (body["fence"] is None)
                    or not isinstance(body["consumed"], list) or len(body["consumed"]) > 128
                    or len(set(body["consumed"])) != len(body["consumed"])):
                raise ValueError()
            for item in body["consumed"]:
                require_sha256(item)
            if body["fence"] is not None:
                self._validate_fence(body["fence"])
                if any(body["fence"][key] not in body["consumed"] for key in ("plan_sha256", "local_plan_key")):
                    raise ValueError()
            return body
        except (ValueError, KeyError, TypeError):
            raise TransportError("CORRUPT_AUTHORITY_JOURNAL_RETAINED", 503) from None

    def _persist(self):
        self._check_owner()
        data = canonical({"body": self._body, "sha256": sha(canonical(self._body))})
        if len(data) > LIMIT:
            self.poisoned = True
            raise TransportError("AUTHORITY_JOURNAL_LIMIT", 503)
        try:
            # Never truncate an earlier failed pending write.
            with self.pending.open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(self.pending, self.path)
            if os.name != "nt":
                descriptor = os.open(self.directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        except BaseException:
            self.poisoned = True
            raise TransportError("AUTHORITY_JOURNAL_WRITE_FAILED_RETAINED", 503) from None

    def _ready(self):
        self._check_owner()
        value = self.gate.snapshot()
        if self.poisoned or self._body["state"] != "OPEN" or value.state != "OPEN" or value.writers:
            raise TransportError("AUTHORITY_FENCED_BUSY_OR_POISONED", 503)
        return value.generation

    def _read(self, image_id):
        try:
            raw = self.context_reader(image_id)
            if not isinstance(raw, dict) or set(raw) != CONTEXT_KEYS:
                raise ValueError()
            objects = raw["objects"]
            if not isinstance(objects, tuple) or len(objects) != 4 or any(value is None for value in objects):
                raise ValueError()
            value = {key: deepcopy(raw[key]) for key in CONTEXT_KEYS - {"objects"}}
            encoded = canonical(value)
            if (len(encoded) > 8 * 1024 * 1024
                    or not isinstance(value["runtime_context"], dict) or not value["runtime_context"]):
                raise ValueError()
            case, admission = value["case"], value["admission"]
            digest = require_sha256(value["source_sha256"])
            metadata = admission.get("source_metadata") or {}
            if (not _identifier(value["workspace_id"]) or value["image_id"] != image_id
                    or value["workspace"].get("workspace_id") != value["workspace_id"]
                    or case.get("image_id") != image_id or type(case.get("revision")) is not int or case["revision"] < 0
                    or case.get("admission") != admission or value["preparation_context"] != preparation_context(case)
                    or not source_allowed_for_model(admission.get("source_origin")) or not is_inference_eligible(admission)
                    or admission.get("retinal_modality") not in {"CFP", "UWF"}
                    or source_identity_reason(case, SimpleNamespace(sha256=digest), admission)
                    or not isinstance(metadata, dict)
                    or metadata.get("integrity_status") not in {None, "OK", "DUPLICATE_CONTENT"}
                    or any(item is not None and item != digest for item in
                           (case.get("source_sha256"), case.get("image_sha256"), metadata.get("source_sha256")))):
                raise ValueError()
            hashes = (case.get("source_sha256") or case.get("image_sha256"), admission.get("source_sha256"),
                      case.get("image_sha256") or metadata.get("source_sha256"))
            if any(item != digest for item in hashes) or not any(item in {"OK", "DUPLICATE_CONTENT"} for item in
                    (admission.get("integrity_status"), (admission.get("integrity") or {}).get("status"), metadata.get("integrity_status"))):
                raise ValueError()
            _pins(value["model_pins"])
            identity = objects[1].prism_preview_identity()
            if (identity["model_pins"] != value["model_pins"]
                    or identity["model_version"] != value["model_pins"]["source_revision"]
                    or (admission["source_origin"] == "HOSPITAL_AUTHORIZED" and "HOSPITAL_AUTHORIZED" not in
                        identity["descriptor"].get("authorized_source_origins", []))):
                raise ValueError()
            recorded = dict(case_source_sha256=hashes[0], admission_source_sha256=hashes[1], image_recorded_sha256=hashes[2],
                            integrity_status="OK", source_origin=admission["source_origin"], case_revision=case["revision"],
                            admission_sha256=sha(canonical(admission)))
            return value, encoded, objects, recorded
        except Exception:
            raise TransportError("FULL_RECORDED_WORKSPACE_CONTEXT_REQUIRED", 503) from None

    def _current_stage(self):
        if self._stage is None:
            raise TransportError("STAGED_WORKSPACE_CONTEXT_REQUIRED")
        value, encoded, objects, _ = self._read(self._stage["image_id"])
        if encoded != self._stage["context"] or not _same_objects(objects, self._stage["objects"]):
            raise TransportError("FULL_WORKSPACE_CONTEXT_OR_OBJECT_CHANGED")
        return value

    def authorize_prepare(self, wire, recorded_context=None, original_bytes=None):
        with self.lock:
            generation = self._ready()
            if not isinstance(wire.data, bytes) or not 0 < len(wire.data) <= 20_000_000:
                raise TransportError("IMMUTABLE_BOUNDED_WIRE_REQUIRED")
            if recorded_context is not None:
                if not isinstance(recorded_context, dict):
                    raise TransportError("RECORDED_PREPARE_CONTEXT_REQUIRED")
                value, encoded, objects, recorded = self._read(wire.image_id)
                expected = dict(scope=recorded_context.get("scope"), image_id=wire.image_id, case_revision=value["case"]["revision"],
                                source_sha256=value["source_sha256"], wire_sha256=sha(wire.data),
                                admission_sha256=recorded["admission_sha256"], recorded_source_identity=recorded,
                                admission={key: value["admission"].get(key) for key in
                                           ("source_origin", "retinal_modality", "modality_admission", "quality_state")},
                                preparation_context=value["preparation_context"], model_pins=value["model_pins"])
                if (not _identifier(expected["scope"]) or recorded_context != expected
                        or not isinstance(original_bytes, bytes) or not 0 < len(original_bytes) <= 20_000_000
                        or sha(original_bytes) != value["source_sha256"]):
                    raise TransportError("IMMUTABLE_RECORDED_PREPARE_CONTEXT_REQUIRED")
                self._stage = dict(image_id=wire.image_id, context=encoded, objects=objects, recorded=expected,
                                   wire=wire.data, generation=generation)
                self._plan = None
            elif original_bytes is not None:
                raise TransportError("RECORDED_PREPARE_CONTEXT_REQUIRED")
            value = self._current_stage()
            if (wire.data != self._stage["wire"] or wire.image_id != self._stage["image_id"]
                    or wire.sha256 != sha(wire.data)
                    or wire.source_type != value["admission"]["source_origin"] or wire.source_origin != wire.source_type
                    or wire.modality != value["admission"]["retinal_modality"]
                    or self._ready() != generation or generation != self._stage["generation"]):
                raise TransportError("STAGED_WIRE_OR_WRITER_GENERATION_CHANGED")

    def register_preview_plan(self, snapshot, binding, plan_hash):
        with self.lock:
            generation = self._ready()
            value = self._current_stage()
            frozen, _ = PrismPreviewService._freeze(snapshot)
            try:
                expiry = datetime.fromisoformat(binding.get("expires_at", ""))
            except (TypeError, ValueError):
                expiry = None
            if (set(binding) != {*frozen, "plan_id", "generation", "expires_at"}
                    or type(binding.get("generation")) is not int or binding["generation"] < 0
                    or not isinstance(binding.get("expires_at"), str) or len(binding["expires_at"]) > 100
                    or expiry is None or expiry.tzinfo is None):
                raise TransportError("EXACT_FROZEN_WORKSPACE_PLAN_METADATA_REQUIRED")
            if (sha(canonical(binding)) != plan_hash or not _identifier(binding.get("plan_id"))
                    or {key: item for key, item in binding.items() if key not in {"plan_id", "generation", "expires_at"}} != frozen
                    or snapshot.wire != self._stage["wire"] or sha(snapshot.source) != value["source_sha256"]
                    or snapshot.runtime.store is not self._stage["objects"][0]
                    or snapshot.runtime.provider is not self._stage["objects"][1]
                    or any(binding.get(key) != item for key, item in self._stage["recorded"].items())
                    or self._ready() != generation or generation != self._stage["generation"]):
                raise TransportError("WORKSPACE_PLAN_HANDLE_OR_CONTEXT_CHANGED")
            key = sha(canonical(["workspace-plan-id", value["workspace_id"], value["image_id"], binding["plan_id"]]))
            if plan_hash in self._body["consumed"] or key in self._body["consumed"]:
                raise TransportError("DURABLE_WORKSPACE_PLAN_REPLAY")
            self._plan = (plan_hash, key, generation)

    def _consume(self, digest, key):
        additions = [item for item in (digest, key) if item not in self._body["consumed"]]
        if len(self._body["consumed"]) + len(additions) > 128:
            raise TransportError("BOUNDED_AUTHORITY_SESSION_EXHAUSTED", 503)
        self._body["consumed"].extend(additions)

    def _status(self, fence, *, waiting=False):
        status = self.reader(deepcopy(fence))
        if (not isinstance(status, dict) or any(status.get(key) != fence[key] for key in STATUS_KEYS)
                or type(status.get("forward_started")) is not bool or type(status.get("terminal")) is not bool):
            raise TransportError("MATCHING_AUTHENTICATED_OLD_JOB_REQUIRED")
        if waiting:
            valid = status.get("state") == "WAITING_SOURCE_FENCE" and not status["forward_started"] and not status["terminal"]
        else:
            valid = (status.get("state") in {"FORWARD_STARTED", "COMPLETE", "FAILED", "ABORTED"}
                     and status["terminal"] == (status["state"] in {"COMPLETE", "FAILED", "ABORTED"})
                     and (status["state"] not in {"FORWARD_STARTED", "COMPLETE"} or status["forward_started"])
                     and (status["forward_started"] or status["terminal"]))
        if not valid:
            raise TransportError("MATCHING_AUTHENTICATED_ENTRY_OR_TERMINAL_REQUIRED")
        return status

    def acquire(self, binding, status, revalidate):
        with self.lock:
            generation = self._ready()
            digest = sha(canonical(binding))
            if (self._plan is None or self._plan[0] != digest or self._plan[2] != generation or not callable(revalidate)
                    or status.get("state") != "WAITING_SOURCE_FENCE" or status.get("forward_started") is not False
                    or status.get("terminal") is not False or status.get("plan_sha256") != digest
                    or status.get("pins") != binding["model_pins"]):
                raise TransportError("REGISTERED_WORKSPACE_PLAN_OR_CHALLENGE_CHANGED")
            fence = {key: deepcopy(status[key]) for key in STATUS_KEYS}
            fence.update(fence_id="workspace_" + secrets.token_hex(16), local_plan_key=self._plan[1],
                         source_context_sha256=sha(self._stage["context"]))
            self._validate_fence(fence)
            self._status(fence, waiting=True)
            self._permit = self.gate.begin_entry(expected_generation=generation)
            self._body["fence"], self._body["state"] = fence, "ACQUIRING"
            attempted = False
            try:
                self._consume(digest, self._plan[1])
                self._persist()
                value = self._current_stage()
                revalidate()
                self._current_stage()
                if self.gate.snapshot().generation != generation:
                    raise TransportError("REVALIDATION_WRITER_GENERATION_CHANGED")
                attempted = True
                self._db_permit = self.database.acquire(workspace_id=value["workspace_id"], image_id=value["image_id"],
                    case=deepcopy(value["case"]), workspace=deepcopy(value["workspace"]), binding=deepcopy(fence))
                if (getattr(self._db_permit, "fence_id", None) != fence["fence_id"]
                        or any(not callable(getattr(self._db_permit, key, None)) for key in ("release", "quarantine"))):
                    raise TransportError("COMMITTED_DATABASE_ENTRY_PERMIT_REQUIRED", 503)
                self._body["state"] = "FENCED"
                self._persist()
                return _WorkspaceLease(self, fence["fence_id"])
            except BaseException:
                if attempted or self.poisoned:
                    self._quarantine()
                else:
                    self._body["state"], self._body["fence"] = "OPEN", None
                    try:
                        self._persist()
                    except BaseException:
                        self._body["fence"] = fence
                        self._quarantine()
                    else:
                        self._permit._release_after_verified_authority()
                        self._permit = None
                raise
            finally:
                self._plan = None

    def _quarantine(self):
        if self._permit is None:
            self._permit = self.gate.begin_entry(expected_generation=self.gate.snapshot().generation)
        self._permit.quarantine()
        if self._body["fence"] is None:
            # Unknown idle DB outcome has no old-job identity to invent. Keep
            # the current process closed; a restart must inspect DB afresh.
            self.poisoned = True
            return
        self._body["state"] = "QUARANTINED"
        try:
            self._persist()
        except BaseException:
            self.poisoned = True

    def _released(self):
        # DB port success is AFTER its authenticated release transaction commit.
        # Open normal writer/save paths even if subsequent local evidence fails.
        self._permit._release_after_verified_authority()
        self._permit = self._db_permit = self._plan = self._stage = None
        self._body["state"], self._body["fence"] = "OPEN", None
        try:
            self._persist()
        except BaseException:
            self.poisoned = True

    def recover(self):
        with self.lock:
            self._check_owner()
            local = self._body["fence"]
            try:
                durable = self.database.read()
            except BaseException:
                self._quarantine()
                raise TransportError("DATABASE_FENCE_OUTCOME_UNKNOWN", 503) from None
            if durable is not None and local != durable:
                self._quarantine()
                raise TransportError("LOCAL_DATABASE_FENCE_SCOPE_MISMATCH", 503)
            if local is None:
                if self.poisoned:
                    raise TransportError("AUTHORITY_POISONED", 503)
                return
            try:
                self._status(local)
                if durable is not None:
                    self.database.recover()
                self._released()
            except BaseException:
                self._quarantine()
                raise

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            if self._fd is not None:
                try:
                    if self._locked:
                        self._os_lock(False)
                        self._locked = False
                finally:
                    os.close(self._fd)
                    self._fd = None


class _WorkspaceLease:
    def __init__(self, authority, fence_id):
        self.authority, self.fence_id = authority, fence_id

    def _current(self):
        authority = self.authority
        authority._check_owner()
        if authority._body["fence"] is None or authority._body["fence"]["fence_id"] != self.fence_id:
            raise TransportError("STALE_WORKSPACE_LEASE")
        return authority

    def release(self, proof):
        with self.authority.lock:
            authority = self._current()
            try:
                if not isinstance(proof, dict) or proof.get("kind") != "AUTHENTICATED_STATUS":
                    raise TransportError("MATCHING_AUTHENTICATED_ENTRY_OR_TERMINAL_REQUIRED")
                status = authority._status(authority._body["fence"])
                authority._db_permit.release({"kind": "AUTHENTICATED_STATUS", "status": status})
                authority._released()
            except BaseException:
                authority._quarantine()
                raise

    def quarantine(self, reason):
        with self.authority.lock:
            authority = self._current()
            authority._quarantine()
