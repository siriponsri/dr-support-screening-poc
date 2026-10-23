"""Offline source-attested transport core. No model imports/listener/credentials.

An executor port and authenticated principal mapper are mandatory. There is no
production port:9488ab8 lacks both source mutation fencing and a fatal native-ROI
entry hook. The isolated registration profile stays disabled until those exist.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import io
import json
import re
import struct
from threading import Condition, Lock, RLock, Thread
import time

from PIL import Image

PROTOCOL = "prism-wire-binding.source-attested.v2"
TRANSPORT = "prism-remote-entry-fence.candidate.v1"
BASE = "/v1/prism-bound"
MASK_VERSION = "uwf_white_rim_fov_v1"
FINAL = {"COMPLETE", "FAILED", "ABORTED"}


class TransportError(RuntimeError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require_sha256(value, code="INVALID_SHA256"):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise TransportError(code, 422)
    return value


def pixels(data, *, mask=False):
    if not isinstance(data, bytes) or not 0 < len(data) <= 20_000_000:
        raise TransportError("IMMUTABLE_BOUNDED_BYTES_REQUIRED", 422)
    with Image.open(io.BytesIO(data)) as image:
        if (image.format not in ({"PNG"} if mask else {"PNG", "JPEG"})
                or getattr(image, "n_frames", 1) != 1 or image.width * image.height > 20_000_000
                or (mask and image.mode != "L")):
            raise TransportError("UNSUPPORTED_IMAGE", 422)
        image.load()
        result = image.copy() if mask else image.convert("RGB")
    if mask:
        histogram = result.histogram()
        if sum(histogram[1:255]) or not histogram[255]:
            raise TransportError("BINARY_NONEMPTY_MASK_REQUIRED", 422)
    return result


def decode64(value):
    if not isinstance(value, str) or len(value) > 20_000_000:
        raise TransportError("BODY_LIMIT", 413)
    try:
        return base64.b64decode(value, validate=True)
    except ValueError:
        raise TransportError("INVALID_BASE64", 422) from None


@dataclass(frozen=True)
class Principal:
    """Created by trusted authentication, never deserialized from request JSON."""
    subject: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class Ticket:
    owner: str
    wire: bytes
    mask: bytes | None
    modality: str
    media: str
    pins: bytes
    candidate: bytes
    deadline: float


@dataclass
class Job:
    owner: str
    ticket_id: str
    binding: bytes
    plan_sha256: str
    deadline: float
    job_id: str = ""
    state: str = "LOADING"
    cancelled: bool = False
    challenge: str | None = None
    fence_id: str | None = None
    forward_started: bool = False
    result: dict | None = None
    error: str | None = None
    condition: Condition = field(default_factory=Condition)
    thread: Thread | None = None


class BoundTransportHost:
    """Single active job, immutable CPU tickets, no retry or production startup.

    executor.load_until must honor a real owned-worker deadline in deployment.
    executor.execute must invoke gate AFTER all loading/queueing and entry at
    actual native ROI entry OUTSIDE recoverable ROI fallback. A bool flag alone
    is not qualification; no implementation of this real executor is registered.
    """
    def __init__(self, executor, *, authenticate, issue_id, epoch, clock=time.monotonic,
                 ticket_seconds=300, job_seconds=30, allowed_origins=frozenset({"SYNTHETIC"})):
        if not getattr(executor, "entry_fence_port", False):
            raise TransportError("FATAL_ROI_ENTRY_PORT_REQUIRED", 503)
        if not (0 < ticket_seconds <= 300 and 0 < job_seconds <= 120):
            raise ValueError("INVALID_DEADLINE")
        self.executor, self.authenticate, self.issue_id = executor, authenticate, issue_id
        from .case16_qualification import checked_authorization
        self.demo_authorization = checked_authorization(getattr(executor, "demo_authorization", None))
        self.epoch, self.clock = epoch, clock
        self.ticket_seconds, self.job_seconds = ticket_seconds, job_seconds
        self.allowed_origins = allowed_origins
        self.tickets, self.jobs = {}, {}
        self.consumed_tickets, self.consumed_plans, self.consumed_ids = set(), set(), set()
        self.lock = RLock()
        self.id_lock = Lock()
        self.issued_ids = set()
        self._workspace_executor = None

    def enable_workspace_executor(self, executor):
        """Trusted bootstrap only; never inferred from request JSON/headers."""
        from .prism_workspace_executor import LoadedWorkspacePrismExecutor
        with self.lock:
            if (type(executor) is not LoadedWorkspacePrismExecutor or executor is not self.executor
                    or self.demo_authorization is not None or self._workspace_executor is not None
                    or self.tickets or self.jobs or self.consumed_tickets or self.consumed_plans
                    or self.consumed_ids or self.issued_ids):
                raise TransportError("FRESH_EXACT_WORKSPACE_EXECUTOR_REQUIRED", 503)
            self._workspace_executor = executor

    def _workspace_enabled(self):
        if self._workspace_executor is None:
            return False
        from .prism_workspace_executor import LoadedWorkspacePrismExecutor
        if (type(self.executor) is not LoadedWorkspacePrismExecutor
                or self.executor is not self._workspace_executor or self.demo_authorization is not None):
            raise TransportError("WORKSPACE_EXECUTOR_SCOPE_CHANGED", 503)
        return True

    def _id(self):
        with self.id_lock:
            value = self.issue_id()
            if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", value)
                    or value in self.issued_ids or len(self.issued_ids) >= 4096):
                raise TransportError("UNIQUE_BOUNDED_ID_FACTORY_REQUIRED", 503)
            self.issued_ids.add(value)
            return value

    def _pins(self):
        self._workspace_enabled()
        value = self.executor.identity()
        if set(value) != {"model_id", "source_revision", "preprocessing", "config_sha256", "checkpoint_sha256"}:
            raise TransportError("IDENTITY_SCHEMA", 503)
        require_sha256(value["config_sha256"], "INVALID_CONFIG_SHA256")
        checkpoints = value["checkpoint_sha256"]
        if not isinstance(checkpoints, dict) or not checkpoints or any(not isinstance(k, str) or not k for k in checkpoints):
            raise TransportError("INVALID_CHECKPOINT_MAP", 422)
        for digest in checkpoints.values():
            require_sha256(digest, "INVALID_CHECKPOINT_SHA256")
        return canonical(value)

    def _job(self, principal, job_id):
        job = self.jobs.get(job_id)
        if job is None or job.owner != principal.subject:
            raise TransportError("UNKNOWN_JOB", 404)
        return job

    def _validate(self, ticket, binding, plan_hash):
        require_sha256(plan_hash, "INVALID_PLAN_SHA256")
        for key in ("source_sha256", "source_rgb_sha256", "wire_rgb_sha256", "wire_sha256", "admission_sha256"):
            require_sha256(binding.get(key), "INVALID_SOURCE_OR_ADMISSION_SHA256")
        if sha(canonical(binding)) != plan_hash or binding.get("binding_protocol") != PROTOCOL:
            raise TransportError("PLAN_PROTOCOL_OR_HASH")
        if len(canonical(binding)) > 256 * 1024:
            raise TransportError("PLAN_SIZE_LIMIT", 413)
        expires = datetime.fromisoformat(binding["expires_at"])
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            raise TransportError("PLAN_EXPIRED")
        if canonical(binding.get("model_pins")) != ticket.pins or self._pins() != ticket.pins:
            raise TransportError("MODEL_CONFIG_CHANGED")
        pins = json.loads(ticket.pins)
        if (binding.get("model_id") != "prism-dr-5fold" or pins["model_id"] != binding["model_id"]
                or binding.get("model_version") != pins["source_revision"]):
            raise TransportError("MODEL_VERSION_CHANGED")
        source = binding.get("recorded_source_identity")
        required = {"case_source_sha256", "admission_source_sha256", "image_recorded_sha256", "integrity_status",
                    "source_origin", "case_revision", "admission_sha256"}
        if not isinstance(source, dict) or set(source) != required:
            raise TransportError("RECORDED_AUTHORITY_REQUIRED")
        for key in ("case_source_sha256", "admission_source_sha256", "image_recorded_sha256", "admission_sha256"):
            require_sha256(source[key], "INVALID_RECORDED_SHA256")
        if (type(source["case_revision"]) is not int or type(binding["case_revision"]) is not int
                or binding["case_revision"] < 0):
            raise TransportError("INVALID_RECORDED_REVISION")
        if (source["integrity_status"] != "OK" or any(source[k] != binding.get("source_sha256") for k in
                ("case_source_sha256", "admission_source_sha256", "image_recorded_sha256"))):
            raise TransportError("SOURCE_CHANGED_OR_CONFLICTING")
        admission = binding.get("admission", {})
        if (source["case_revision"] != binding.get("case_revision") or source["admission_sha256"] != binding.get("admission_sha256")
                or source["source_origin"] != admission.get("source_origin")
                or source["source_origin"] not in self.allowed_origins
                or admission.get("retinal_modality") != ticket.modality):
            raise TransportError("SOURCE_CONTEXT_OR_ADMISSION")
        if self.demo_authorization is None:
            if admission.get("modality_admission") != "FUNDUS_ACCEPTED" or admission.get("quality_state") != "GRADABLE":
                raise TransportError("SOURCE_CONTEXT_OR_ADMISSION")
        else:
            # Typed, pinned, no-mask, bounded qualification only. Never infer a
            # research exception from a client-provided mode flag or new hash.
            self.demo_authorization.binding(binding)
        image = pixels(ticket.wire)
        rgb_digest = sha(struct.pack(">II", *image.size) + image.tobytes())
        candidate = json.loads(ticket.candidate)
        if (binding.get("wire_sha256") != sha(ticket.wire) or binding.get("wire_byte_count") != len(ticket.wire)
                or binding.get("wire_rgb_sha256") != rgb_digest or binding.get("source_rgb_sha256") != rgb_digest
                or binding.get("wire_dimensions") != {"width": image.width, "height": image.height}
                or binding.get("wire_media_type") != ticket.media or binding.get("modality") != ticket.modality):
            raise TransportError("WIRE_BINDING_CHANGED")
        for name in ("mask_sha256", "mask_png_sha256", "mask_version", "external_fov_status", "external_fov_reason_code"):
            if name in {"mask_sha256", "mask_png_sha256"} and binding.get(name) is not None:
                require_sha256(binding[name], "INVALID_MASK_SHA256")
            if binding.get(name) != candidate[name]:
                raise TransportError("MASK_BINDING_CHANGED")
        transform = deepcopy(binding.get("transform", {}));digest = transform.pop("sha256", None)
        require_sha256(digest, "INVALID_TRANSFORM_SHA256")
        if not digest or sha(canonical(transform)) != digest:
            raise TransportError("TRANSFORM_BINDING_CHANGED")
        ow, oh, iw, ih = (transform.get(k) for k in ("original_width", "original_height", "input_width", "input_height"))
        if (any(type(v) is not int or v <= 0 for v in (ow, oh, iw, ih)) or (iw, ih) != image.size
                or transform.get("version") != "1" or transform.get("original_to_input") != [iw / ow, 0, 0, ih / oh, 0, 0]
                or transform.get("coordinate_mapping", {}).get("scale_x") != ow / iw
                or transform.get("coordinate_mapping", {}).get("scale_y") != oh / ih):
            raise TransportError("UNSUPPORTED_TRANSFORM")
        if ticket.modality == "UWF" and (transform.get("transform_id") != "analysis-uwf-unmasked-source-v1"
                or transform.get("representation_version") != "uwf-source-analysis-v1"):
            raise TransportError("UNSUPPORTED_UWF_TRANSFORM")
        if self.clock() >= ticket.deadline:
            raise TransportError("TICKET_EXPIRED")

    def _prepare(self, principal, value):
        with self.lock:
            if any(job.state not in FINAL for job in self.jobs.values()):
                raise TransportError("CONCURRENT_PREPARATION")
            return self._prepare_locked(principal, value)

    def _prepare_locked(self, principal, value):
        if set(value) != {"wire_b64", "wire_sha256", "wire_media_type", "modality"}:
            raise TransportError("PREPARE_SCHEMA", 422)
        wire = decode64(value["wire_b64"]);image = pixels(wire)
        with Image.open(io.BytesIO(wire)) as encoded:
            if {"PNG": "image/png", "JPEG": "image/jpeg"}.get(encoded.format) != value["wire_media_type"]:
                raise TransportError("MEDIA_TYPE_MISMATCH", 422)
        # CFP is opt-in for the exact batch or additive workspace executor.
        # Existing synthetic/case16 fixed-session paths stay UWF-only.
        from .case16_qualification import Case16Authorization
        batch_authorized = self.demo_authorization is not None and type(self.demo_authorization) is not Case16Authorization
        workspace_enabled = self._workspace_enabled()
        if (value["wire_sha256"] != sha(wire)
                or value["modality"] not in ({"CFP", "UWF"} if batch_authorized or workspace_enabled else {"UWF"})):
            raise TransportError("WIRE_CONTEXT", 422)
        if batch_authorized:
            self.demo_authorization.job_for_wire(wire, value["modality"])
        pins = self._pins()
        candidate = self.executor.prepare(wire, value["modality"])
        if self._pins() != pins:
            raise TransportError("CONFIG_CHANGED_DURING_CPU_PREPARE")
        mask = candidate.get("mask_png")
        mask_digest = None
        if mask is not None:
            decoded = pixels(mask, mask=True)
            if (decoded.size != image.size or candidate["status"] != "READY"
                    or candidate["mask_version"] != MASK_VERSION or value["modality"] != "UWF"):
                raise TransportError("MASK_CONTEXT")
            mask_digest = sha(MASK_VERSION.encode() + struct.pack(">II", *decoded.size) + decoded.tobytes())
        elif candidate["status"] not in (
                {"NOT_APPLICABLE"} if batch_authorized or workspace_enabled and value["modality"] == "CFP"
                else {"UNCERTAIN", "UNAVAILABLE"}):
            raise TransportError("READY_MASK_MISSING")
        if batch_authorized:
            self.demo_authorization.candidate(candidate)
        frozen = {"external_fov_status": candidate["status"], "external_fov_reason_code": candidate.get("reason_code"),
                  "mask_sha256": mask_digest, "mask_png_sha256": sha(mask) if mask else None,
                  "mask_version": MASK_VERSION if mask else None}
        with self.lock:
            self.tickets = {k: v for k, v in self.tickets.items() if v.deadline > self.clock()}
            if (len(self.tickets) >= 16 or sum(len(t.wire) + len(t.mask or b"") for t in self.tickets.values())
                    + len(wire) + len(mask or b"") > 128 * 1024**2):
                raise TransportError("TICKET_CACHE_LIMIT", 503)
            ticket_id = self._id()
            self.tickets[ticket_id] = Ticket(principal.subject, wire, mask, value["modality"], value["wire_media_type"],
                                             pins, canonical(frozen), self.clock() + self.ticket_seconds)
        return {"ticket_id": ticket_id, "epoch": self.epoch, "pins": json.loads(pins), **frozen,
                "mask_b64": base64.b64encode(mask).decode() if mask else None}

    def _start(self, principal, value):
        if set(value) != {"ticket_id", "binding", "plan_sha256"}:
            raise TransportError("EXECUTE_SCHEMA", 422)
        with self.lock:
            ticket_id = value["ticket_id"];ticket = self.tickets.get(ticket_id)
            if ticket is None or ticket.owner != principal.subject:
                raise TransportError("UNKNOWN_TICKET", 404)
            if any(j.state not in FINAL for j in self.jobs.values()):
                raise TransportError("CONCURRENT_ADMISSION")
            if len(self.jobs) >= 16:
                raise TransportError("SESSION_JOB_CAP", 503)
            binding = deepcopy(value["binding"]);digest = value["plan_sha256"]
            self._validate(ticket, binding, digest)
            plan_id = (binding["scope"], binding["image_id"], binding["plan_id"])
            if ticket_id in self.consumed_tickets or digest in self.consumed_plans or plan_id in self.consumed_ids:
                raise TransportError("REPLAY")
            self.consumed_tickets.add(ticket_id);self.consumed_plans.add(digest);self.consumed_ids.add(plan_id)
            job_id = self._id();job = Job(principal.subject, ticket_id, canonical(binding), digest,
                                         self.clock() + self.job_seconds, job_id=job_id)
            self.jobs[job_id] = job
            job.thread = Thread(target=self._run, args=(job, ticket), daemon=False)
            job.thread.start()
        return {"job_id": job_id, "epoch": self.epoch}

    def _run(self, job, ticket):
        from .identity_budget import identity_budget
        try:
            with identity_budget(job.deadline, cancelled=lambda: job.cancelled, clock=self.clock):
                return self._run_bounded(job, ticket)
        except BaseException as error:
            with job.condition:
                job.error = error.code if isinstance(error, TransportError) else "EXECUTOR_FAILED_NO_RETRY"
                job.state = "ABORTED" if job.cancelled else "FAILED"
                job.condition.notify_all()

    def _run_bounded(self, job, ticket):
        binding = json.loads(job.binding)
        def check(*, verify_identity=True):
            if job.cancelled or self.clock() >= job.deadline:
                raise TransportError("CANCELLED_OR_DEADLINE")
            if verify_identity:
                self._validate(ticket, binding, job.plan_sha256)
        def gate():
            # Must be called by the executor AFTER its final load/queue wait.
            with job.condition:
                check();job.challenge = self._id();job.state = "WAITING_SOURCE_FENCE"
                job.condition.notify_all()
                while job.fence_id is None:
                    check(verify_identity=False);job.condition.wait(min(.05, max(.001, job.deadline - self.clock())))
                check();job.state = "GRANTED_NOT_STARTED"
        def entry():
            # Mandatory fatal hook OUTSIDE the recoverable native-ROI try block.
            with job.condition:
                check()
                if job.state != "GRANTED_NOT_STARTED" or not job.fence_id:
                    raise TransportError("NO_SOURCE_FENCE_AT_ENTRY")
                job.forward_started = True;job.state = "FORWARD_STARTED"
                job.condition.notify_all()
        try:
            self.executor.load_until(job.deadline, lambda: job.cancelled)
            check()
            if canonical(self.executor.loaded_identity()) != ticket.pins:
                raise TransportError("LOADED_MODEL_CONFIG_CHANGED")
            returned = self.executor.execute(ticket.wire, ticket.mask, binding, job.plan_sha256,
                                             before_forward=gate, on_roi_entry=entry)
            if not job.forward_started:
                raise TransportError("EXECUTOR_SKIPPED_FATAL_ENTRY_HOOK")
            with job.condition:
                check(verify_identity=False)
                job.result = returned;job.state = "COMPLETE";job.condition.notify_all()
        except BaseException as error:
            with job.condition:
                job.error = error.code if isinstance(error, TransportError) else "EXECUTOR_FAILED_NO_RETRY"
                job.state = "ABORTED" if job.cancelled else "FAILED";job.condition.notify_all()

    def _status(self, job):
        with job.condition:
            return {"job_id": job.job_id, "state": job.state, "forward_started": job.forward_started, "terminal": job.state in FINAL,
                    "challenge_id": job.challenge, "plan_sha256": job.plan_sha256, "ticket_id": job.ticket_id,
                    "pins": json.loads(job.binding)["model_pins"], "epoch": self.epoch,
                    "result": deepcopy(job.result) if job.state == "COMPLETE" else None, "error": job.error}

    def handle(self, method, path, headers, body):
        """HTTP-independent handler, exercised through in-memory fake endpoints."""
        try:
            principal = self.authenticate(headers)
            if not isinstance(principal, Principal) or "review-client" not in principal.scopes:
                raise TransportError("UNAUTHORIZED", 401)
            if method == "GET" and path == BASE + "/capabilities":
                return 200, {"transport": TRANSPORT, "binding_protocol": PROTOCOL, "epoch": self.epoch,
                             "pins": json.loads(self._pins()), "runtime_registered": False}
            if headers.get("x-prism-epoch") != self.epoch:
                raise TransportError("SESSION_RESTARTED_OR_EXPIRED")
            if len(body) > 20_100_000:
                raise TransportError("BODY_LIMIT", 413)
            value = json.loads(body) if body else {}
            if method == "POST" and path == BASE + "/prepare":
                if "prepare-source" not in principal.scopes:
                    raise TransportError("TRUSTED_PREPARATION_AUTHORITY_REQUIRED", 403)
                return 200, self._prepare(principal, value)
            if method == "POST" and path == BASE + "/execute":
                return 202, self._start(principal, value)
            match = re.fullmatch(re.escape(BASE) + r"/jobs/([A-Za-z0-9_-]{8,80})(?:/(grant|cancel))?", path)
            if not match:
                raise TransportError("UNKNOWN_ROUTE", 404)
            job = self._job(principal, match[1]);action = match[2]
            if method == "GET" and action is None:
                return 200, self._status(job)
            if method == "POST" and action == "cancel":
                if value:
                    raise TransportError("CANCEL_SCHEMA", 422)
                with job.condition:
                    job.cancelled = True;job.condition.notify_all()
                return 202, {"cancel_requested": True, "terminal_confirmed": False}
            if method == "POST" and action == "grant":
                if "forward-authority" not in principal.scopes:
                    raise TransportError("TRUSTED_SOURCE_AUTHORITY_REQUIRED", 403)
                if set(value) != {"challenge_id", "plan_sha256", "fence_id"}:
                    raise TransportError("GRANT_SCHEMA", 422)
                with job.condition:
                    if (job.state != "WAITING_SOURCE_FENCE" or job.cancelled or self.clock() >= job.deadline
                            or value.get("challenge_id") != job.challenge or value.get("plan_sha256") != job.plan_sha256
                            or not isinstance(value.get("fence_id"), str) or not 8 <= len(value["fence_id"]) <= 80):
                        raise TransportError("GRANT_STALE_REPLAY_OR_WRONG_SCOPE")
                    job.fence_id = value["fence_id"];job.state = "GRANT_RECEIVED";job.condition.notify_all()
                return 200, {"grant_received": True, "forward_started": False}
            raise TransportError("UNKNOWN_ROUTE", 404)
        except TransportError as error:
            return error.status, {"error": error.code}
        except (KeyError, TypeError, ValueError, OSError):
            return 422, {"error": "INVALID_FROZEN_REQUEST"}
        except Exception:
            return 503, {"error": "HOST_OPERATION_FAILED_NO_RETRY"}

    def join_for_test(self, timeout=3):
        """No process kill. Test fixtures must release their own fake loaders."""
        for job in self.jobs.values():
            job.thread.join(timeout)
            if job.thread.is_alive():
                raise RuntimeError("FAKE_JOB_STILL_RUNNING")
