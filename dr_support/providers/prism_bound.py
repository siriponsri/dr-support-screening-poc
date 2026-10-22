"""Offline candidate for source-attested, immutable local PRISM execution.

NOT registered in any factory/remote provider. The source-attested v2 protocol
is jointly tested offline; no model/runtime qualification or availability claimed.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import struct
from threading import Lock
import time

from PIL import Image

from dr_support.contracts import LABELS, LesionResult, PrismProcessingEvidence
from dr_support.services.source_policy import source_allowed_for_model
from .assets import verify_source, verify_weight
from .prism import PREPROCESSING, REVISION, PRISM

MASK_VERSION = "uwf_white_rim_fov_v1"
# Incompatible with v1 and the original unreviewed candidate protocol.
PROPOSED_PROTOCOL = "prism-wire-binding.source-attested.v2"
MAX_BYTES = 20_000_000
MAX_PIXELS = 20_000_000
PIN_FIELDS = {"model_id", "source_revision", "preprocessing", "config_sha256", "checkpoint_sha256"}


class BoundPlanError(ValueError):
    """Fixed reason codes only; no patient paths, bytes or secret values."""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def rgb_hash(image):
    return sha(struct.pack(">II", *image.size) + image.tobytes())


def decode(data, *, mode="RGB"):
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
        raise BoundPlanError("IMMUTABLE_BOUNDED_BYTES_REQUIRED")
    with Image.open(io.BytesIO(data)) as opened:
        if opened.format not in {"PNG", "JPEG"} or getattr(opened, "n_frames", 1) != 1:
            raise BoundPlanError("UNSUPPORTED_WIRE_ENCODING")
        if opened.width * opened.height > MAX_PIXELS:
            raise BoundPlanError("PIXEL_LIMIT")
        if mode == "L" and (opened.mode != "L" or opened.format != "PNG"):
            raise BoundPlanError("BINARY_L_PNG_REQUIRED")
        opened.load()
        return opened.convert(mode)


def png(image):
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def thresholds():
    values = json.loads(os.environ.get("PRISM_THRESHOLDS", "{}"))
    if not isinstance(values, dict) or set(values) - set(LABELS):
        raise BoundPlanError("UNSUPPORTED_THRESHOLDS")
    for value in values.values():
        if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1:
            raise BoundPlanError("UNSUPPORTED_THRESHOLDS")
    return tuple(sorted(values.items()))


def restore_fov(metadata, mask):
    # Lazy real baseline import; never called by module import or static identity.
    from dr_support.imaging.uwf_white_rim_fov import FovStatus, WhiteRimFov
    values = json.loads(metadata)
    values["status"] = FovStatus(values["status"])
    values["bounding_box"] = tuple(values["bounding_box"]) if values["bounding_box"] else None
    values["boundary"] = tuple(tuple(point) for point in values["boundary"])
    return WhiteRimFov(field_mask=mask, **values)


@dataclass(frozen=True)
class FrozenBaselinePreparation:
    wire: bytes
    mask_png: bytes | None
    fov_metadata: bytes | None
    status: str
    reason: str | None
    thresholds: tuple

    def materialize(self, image, original_rgb):
        if bytes(image.data) != self.wire or rgb_hash(original_rgb) != rgb_hash(decode(self.wire)):
            raise BoundPlanError("EXECUTION_WIRE_CHANGED")
        mask = decode(self.mask_png, mode="L") if self.mask_png else None
        fov = restore_fov(self.fov_metadata, mask) if self.fov_metadata else None
        # Binary-only mask: identical pixels to baseline numpy[mask == 0] = 0.
        masked = Image.composite(original_rgb, Image.new("RGB", original_rgb.size), mask) if mask else None
        return fov, masked


class BoundLocalPRISM(PRISM):
    prism_preview_protocol = PROPOSED_PROTOCOL

    def __init__(self, *, allow_cpu_fallback=None, batch_authorization=None):
        if batch_authorization is not None:
            from prism_batch_scope import is_batch_authorization
            if not is_batch_authorization(batch_authorization):
                raise BoundPlanError("TYPED_APPROVED_BATCH_AUTHORIZATION_REQUIRED")
        super().__init__(allow_cpu_fallback=allow_cpu_fallback)
        self._batch_authorization = batch_authorization
        self._bound_lock = Lock()
        self._candidates = OrderedDict()
        self._consumed = set()
        self._consumed_ids = set()
        self._loaded_identity = None
        self._active_preparation = None

    def _runtime_identity(self):
        """CPU file verification and package metadata only; no load/metadata/GPU."""
        from dr_support.services.identity_budget import check_identity_budget
        from .assets import sha256 as file_digest
        check_identity_budget()
        source = verify_source(os.environ["PRISM_SOURCE"], REVISION)
        check_identity_budget()
        weights = Path(os.environ["PRISM_WEIGHTS"])
        lock_path = Path(__file__).with_name("prism_assets.json")
        pins = json.loads(lock_path.read_text())["weights"]
        if len(pins) != 21:
            raise BoundPlanError("EXACT21_CHECKPOINTS_REQUIRED")
        for relative, digest in pins.items():
            check_identity_budget()
            verify_weight(weights / relative, digest)
            check_identity_budget()
        package = Path(__file__).resolve().parents[1]
        files = {"adapter": Path(__file__), "provider": Path(__file__).with_name("prism.py"),
                 "loader": Path(__file__).with_name("prism_safe_loader.py"), "lock": lock_path,
                 "FOV": package / "imaging/uwf_white_rim_fov.py",
                 "engine": source / "evaluation/src/image_level_evaluation.py",
                 "config": source / "evaluation/src/config.py", "yaml": source / "evaluation/configs/inference.yaml"}
        if self._batch_authorization is not None:
            import prism_batch_scope
            files["batch_authority"] = Path(prism_batch_scope.__file__)
        config = {"files": {name: file_digest(path) for name, path in files.items()},
                  "thresholds": thresholds(), "baseline": PREPROCESSING,
                  "versions": {name: importlib.metadata.version(name) for name in
                               ("numpy", "opencv-python", "Pillow", "torch", "torchvision", "ultralytics", "sahi", "ensemble-boxes")}}
        if self._batch_authorization is not None:
            # Policy is part of model/config identity, never disguised as an
            # uncertain anatomical mask from the baseline detector.
            config["external_mask_policy"] = self._batch_authorization.external_mask_policy
        check_identity_budget()
        return {"model_id": self.model_id, "source_revision": REVISION,
                "preprocessing": PREPROCESSING + "; bound_config=" + sha(canonical(config)),
                "config_sha256": sha(canonical(config)), "checkpoint_sha256": pins}

    def prism_preview_identity(self):
        pins = self._runtime_identity()
        # No self.metadata(): that method inspects the model/GPU runtime.
        descriptor = {"model_id": self.model_id, "task": "lesion-roi", "revision": REVISION,
                      "modalities": ["CFP", "UWF"], "ready": False,
                      "status": "OFFLINE_CANDIDATE_NOT_QUALIFIED", "release_status": "RESEARCH_ONLY"}
        return {"model_version": REVISION, "descriptor": descriptor, "model_pins": pins}

    @staticmethod
    def _detect_baseline(wire_rgb):
        from dr_support.imaging.uwf_white_rim_fov import detect_white_rim_fov
        return detect_white_rim_fov(wire_rgb)

    def _prepare_candidate(self, wire):
        if not isinstance(wire.data, bytes):
            raise BoundPlanError("IMMUTABLE_WIRE_BYTES_REQUIRED")
        image = decode(bytes(wire.data))
        if image.size != wire.size or wire.modality not in {"CFP", "UWF"}:
            raise BoundPlanError("WIRE_CONTEXT_MISMATCH")
        if self._batch_authorization is not None:
            self._batch_authorization.job_for_wire(wire.data, wire.modality)
            if wire.source_type != self._batch_authorization.origin_for_wire(wire.data, wire.modality):
                raise BoundPlanError("BATCH_RECORDED_ORIGIN_CHANGED")
        pins = self._runtime_identity()
        key = (sha(bytes(wire.data)), wire.modality, sha(canonical(pins)))
        now = time.monotonic()
        self._candidates = OrderedDict((k, v) for k, v in self._candidates.items() if v[0] > now)
        if key in self._candidates:
            return self._candidates[key][1]
        mask, metadata, reason, status = None, None, None, "NOT_APPLICABLE"
        if self._batch_authorization is not None:
            from prism_batch_scope import EXTERNAL_MASK_REASON
            # No anatomy detector is attempted in this explicit original-input
            # experiment. Native PRISM ROI still executes after the fatal fence.
            reason = EXTERNAL_MASK_REASON
        elif wire.modality == "UWF":
            fov = self._detect_baseline(image)
            status, reason = str(fov.status), fov.reason_code
            if fov.source_rgb_sha256 != rgb_hash(image) or (fov.image_width, fov.image_height) != image.size:
                raise BoundPlanError("BASELINE_FOV_SOURCE_MISMATCH")
            if status not in {"READY", "UNCERTAIN", "UNAVAILABLE"}:
                raise BoundPlanError("UNSUPPORTED_FOV_STATE")
            values = {name: getattr(fov, name) for name in (
                "status", "mask_version", "mask_sha256", "source_rgb_sha256", "boundary_confidence",
                "field_fraction", "excluded_fraction", "bounding_box", "boundary", "image_width", "image_height", "reason_code")}
            values["status"] = status
            if status == "READY":
                if fov.mask_version != MASK_VERSION or fov.field_mask is None:
                    raise BoundPlanError("BASELINE_MASK_REQUIRED")
                mask = png(fov.field_mask)
                decoded = decode(mask, mode="L")
                hist = decoded.histogram()
                if decoded.size != image.size or sum(hist[1:255]) or not hist[255]:
                    raise BoundPlanError("INVALID_BINARY_MASK")
                if fov.mask_sha256 != sha(MASK_VERSION.encode() + struct.pack(">II", *image.size) + decoded.tobytes()):
                    raise BoundPlanError("MASK_HASH_MISMATCH")
            elif fov.field_mask is not None:
                raise BoundPlanError("UNCERTAIN_MASK_FORBIDDEN")
            metadata = canonical(values)
        frozen = FrozenBaselinePreparation(bytes(wire.data), mask, metadata, status, reason, thresholds())
        while self._candidates and (len(self._candidates) >= 16 or
                sum(len(v[1].wire) + len(v[1].mask_png or b"") for v in self._candidates.values()) +
                len(frozen.wire) + len(mask or b"") > 128 * 1024**2):
            self._candidates.popitem(last=False)
        self._candidates[key] = (now + 300, frozen)
        return frozen

    def prepare_prism_preview_candidate(self, wire):
        with self._bound_lock:
            value = self._prepare_candidate(wire)
            return {"status": value.status, "reason_code": value.reason,
                    "mask_png": value.mask_png, "mask_version": MASK_VERSION if value.mask_png else None}

    def get_prism_preview_candidate(self, wire):
        """Read an existing preparation only; never run detection on validation."""
        with self._bound_lock:
            key = (sha(bytes(wire.data)), wire.modality, sha(canonical(self._runtime_identity())))
            entry = self._candidates.get(key)
            if entry is None or entry[0] <= time.monotonic():
                raise BoundPlanError("CANDIDATE_EXPIRED_OR_RESTARTED")
            value = entry[1]
            return {"status": value.status, "reason_code": value.reason,
                    "mask_png": value.mask_png, "mask_version": MASK_VERSION if value.mask_png else None}

    def _validate(self, request, wire, mask_png, binding, plan_hash, *, demo_authorization=None):
        from dr_support.services.case16_qualification import Case16Authorization, checked_authorization
        authorization = checked_authorization(demo_authorization)
        if self._batch_authorization is not None and authorization is not self._batch_authorization:
            raise BoundPlanError("BATCH_EXECUTION_AUTHORITY_CHANGED")
        if (authorization is not None and type(authorization) is not Case16Authorization
                and authorization is not self._batch_authorization):
            # checked_authorization already excluded every other type. Do not
            # add a batch-package import dependency to ordinary case16 users.
            raise BoundPlanError("BATCH_POLICY_NOT_CONFIGURED")
        if authorization is not None:
            # The qualification is exact-case authority, never a rewritten admission.
            authorization.binding(binding)
            authorization.wire(wire.data)
            if mask_png is not None:
                raise BoundPlanError("CASE16_NO_APPLIED_MASK")
        if not isinstance(wire.data, bytes) or (mask_png is not None and not isinstance(mask_png, bytes)):
            raise BoundPlanError("IMMUTABLE_EXECUTION_BYTES_REQUIRED")
        if sha(canonical(binding)) != plan_hash:
            raise BoundPlanError("PLAN_HASH_MISMATCH")
        if binding.get("binding_protocol") != PROPOSED_PROTOCOL:
            raise BoundPlanError("SOURCE_ATTESTED_V2_REQUIRED")
        source = binding.get("recorded_source_identity")
        # Proposed mandatory shared-contract extension. Freshly hashing changed
        # bytes must NEVER replace any recorded case/admission/image identity.
        required = {"case_source_sha256", "admission_source_sha256", "image_recorded_sha256",
                    "integrity_status", "source_origin", "case_revision", "admission_sha256"}
        if not isinstance(source, dict) or set(source) != required:
            raise BoundPlanError("RECORDED_SOURCE_ATTESTATION_REQUIRED")
        if (not isinstance(binding["source_sha256"], str) or len(binding["source_sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in binding["source_sha256"])):
            raise BoundPlanError("SOURCE_DIGEST_REQUIRED")
        if (source["integrity_status"] != "OK" or any(source[key] != binding["source_sha256"] for key in
                ("case_source_sha256", "admission_source_sha256", "image_recorded_sha256"))):
            raise BoundPlanError("RECORDED_SOURCE_CHANGED_OR_CONFLICTING")
        if (source["case_revision"] != binding["case_revision"] or source["admission_sha256"] != binding["admission_sha256"]
                or source["source_origin"] != binding["admission"]["source_origin"]):
            raise BoundPlanError("SOURCE_CONTEXT_CHANGED")
        if (request.model_id != self.model_id or binding["model_id"] != self.model_id or binding["model_version"] != REVISION
                or request.image_id != binding["image_id"] or wire.image_id != request.image_id
                or request.modality != binding["modality"] or wire.modality != request.modality):
            raise BoundPlanError("MODEL_IMAGE_MODALITY_MISMATCH")
        admission = binding["admission"]
        if (admission["source_origin"] != wire.source_type or
                (self._batch_authorization is None and not source_allowed_for_model(wire.source_type, model_api=True))
                or admission["retinal_modality"] != request.modality):
            raise BoundPlanError("SOURCE_OR_ADMISSION_BLOCKED")
        if ((authorization is None or not authorization.technical_only)
                and (admission["modality_admission"] != "FUNDUS_ACCEPTED"
                     or admission["quality_state"] != "GRADABLE")):
            raise BoundPlanError("SOURCE_OR_ADMISSION_BLOCKED")
        current = self._runtime_identity()
        if set(binding["model_pins"]) != PIN_FIELDS or current != binding["model_pins"]:
            raise BoundPlanError("MODEL_CONFIG_PINS_CHANGED")
        if (sha(bytes(wire.data)) != binding["wire_sha256"] or len(wire.data) != binding["wire_byte_count"]
                or wire.media_type != binding["wire_media_type"]):
            raise BoundPlanError("WIRE_BYTES_CHANGED")
        image = decode(bytes(wire.data))
        if (rgb_hash(image) != binding["wire_rgb_sha256"] or binding["source_rgb_sha256"] != rgb_hash(image)
                or binding["wire_dimensions"] != {"width": image.width, "height": image.height} or image.size != wire.size):
            raise BoundPlanError("WIRE_RGB_DIMENSIONS_CHANGED")
        transform = deepcopy(binding["transform"])
        digest = transform.pop("sha256")
        if sha(canonical(transform)) != digest:
            raise BoundPlanError("TRANSFORM_CHANGED")
        ow, oh, iw, ih = (transform[k] for k in ("original_width", "original_height", "input_width", "input_height"))
        if (any(type(v) is not int or v <= 0 for v in (ow, oh, iw, ih)) or (iw, ih) != image.size
                or transform["original_to_input"] != [iw / ow, 0, 0, ih / oh, 0, 0]
                or transform["coordinate_mapping"].get("scale_x") != ow / iw
                or transform["coordinate_mapping"].get("scale_y") != oh / ih):
            raise BoundPlanError("UNSUPPORTED_SPATIAL_TRANSFORM")
        if request.modality == "UWF" and (transform["transform_id"] != "analysis-uwf-unmasked-source-v1"
                or transform["representation_version"] != "uwf-source-analysis-v1"):
            raise BoundPlanError("UNSUPPORTED_UWF_PREPROCESSING")
        if (transform["version"] != "1" or (request.modality == "CFP" and
                (transform["transform_id"] not in {"analysis-source-v1", "analysis-tiff-png-rgb-v1", "analysis-dicom-png-rgb-v1"}
                 or transform["representation_version"] != "uwf-analysis-representation-v1"))):
            raise BoundPlanError("UNSUPPORTED_TRANSFORM_VERSION")
        expires = datetime.fromisoformat(binding["expires_at"])
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            raise BoundPlanError("PLAN_EXPIRED")
        key = (wire.sha256, wire.modality, sha(canonical(current)))
        entry = self._candidates.get(key)
        if entry is None or entry[0] <= time.monotonic():
            raise BoundPlanError("CANDIDATE_EXPIRED_OR_RESTARTED")
        frozen = entry[1]
        mask_sha = None if frozen.mask_png is None else sha(MASK_VERSION.encode() + struct.pack(">II", *image.size) + decode(frozen.mask_png, mode="L").tobytes())
        if (mask_png != frozen.mask_png or binding["mask_png_sha256"] != (sha(mask_png) if mask_png else None)
                or binding["mask_sha256"] != mask_sha or binding["mask_version"] != (MASK_VERSION if mask_png else None)
                or binding["external_fov_status"] != frozen.status or binding["external_fov_reason_code"] != frozen.reason
                or frozen.thresholds != thresholds()):
            raise BoundPlanError("FROZEN_MASK_OR_POLICY_CHANGED")
        return frozen, current

    def load(self):
        before = self._runtime_identity()
        super().load()
        if before != self._runtime_identity() or self.hashes != before["checkpoint_sha256"]:
            raise BoundPlanError("LOAD_IDENTITY_CHANGED")
        self._loaded_identity = before

    def infer(self, request, image):
        raise BoundPlanError("BOUND_PLAN_REQUIRED_NO_LEGACY_FALLBACK")

    def infer_remote_fenced_prism(self, request, wire, *, mask_png, binding, plan_sha256,
                                  before_forward, on_native_roi_entry, demo_authorization=None):
        # Review-only port; no factory/profile is registered by this patch.
        if not callable(before_forward) or not callable(on_native_roi_entry):
            raise BoundPlanError("FATAL_REMOTE_ENTRY_PORT_REQUIRED")
        return self.infer_bound_prism(request, wire, mask_png=mask_png, binding=binding,
            plan_sha256=plan_sha256, before_forward=before_forward, _remote_roi_entry=on_native_roi_entry,
            _demo_authorization=demo_authorization)

    def infer_bound_prism(self, request, wire, *, mask_png, binding, plan_sha256, before_forward=None,
                          _remote_roi_entry=None, _demo_authorization=None):
        if _demo_authorization is not None and not callable(_remote_roi_entry):
            raise BoundPlanError("FATAL_REMOTE_ENTRY_PORT_REQUIRED")
        if not self._bound_lock.acquire(blocking=False):
            raise BoundPlanError("SERIAL_EXECUTION_ONLY")
        model_work_started = False
        try:
            binding, request = deepcopy(binding), deepcopy(request)
            if not callable(before_forward):
                raise BoundPlanError("SERVER_SOURCE_REVALIDATION_REQUIRED")
            frozen, pins = self._validate(request, wire, mask_png, binding, plan_sha256,
                                          demo_authorization=_demo_authorization)
            plan_identity = (binding["scope"], binding["image_id"], binding["plan_id"])
            if (plan_sha256 in self._consumed or plan_identity in self._consumed_ids
                    or len(self._consumed) >= 4096):
                raise BoundPlanError("PLAN_REPLAY_OR_PROCESS_BUDGET")
            self._consumed.add(plan_sha256)  # Includes failed loads/forwards, never replay.
            self._consumed_ids.add(plan_identity)
            model_work_started = True
            if not self.loaded:
                self.load()
            if self._loaded_identity != pins:
                raise BoundPlanError("LOADED_MODELS_DO_NOT_MATCH_PREVIEW")
            # Revalidate after load/wait and immediately before the native ROI.
            self._validate(request, wire, mask_png, binding, plan_sha256,
                           demo_authorization=_demo_authorization)
            before_forward()
            self._active_preparation = frozen
            result = self._infer_loaded(request, wire, _frozen_preparation=frozen, _fatal_roi_entry=_remote_roi_entry)
            result = LesionResult.model_validate(result)
            processing = deepcopy(self.last_processing_evidence)
            # The native ROI stage runs for CFP as well as UWF; do not discard
            # its actual coordinates/fallback evidence for the CFP batch route.
            processing = PrismProcessingEvidence.model_validate(processing).model_dump(mode="json")
            if (processing["input_image_sha256"] != binding["wire_sha256"]
                    or processing["external_fov_status"] != frozen.status
                    or processing["external_fov_reason_code"] != frozen.reason
                    or len(processing["raw_boundary_classes"]) != len(result.lesions)):
                raise BoundPlanError("PROCESSING_INPUT_MISMATCH")
            if processing["native_roi_status"] == "FAILED":
                expected_mode = "FALLBACK" if request.modality == "UWF" else "LEGACY"
                if processing["processing_mode"] != expected_mode or processing["fov_used_for_model_input"]:
                    raise BoundPlanError("INVALID_NATIVE_ROI_FALLBACK")
                processing["analysis_field"] = None
            elif frozen.mask_png is not None:
                field = processing["analysis_field"] or {}
                if (processing["processing_mode"] != "PREPARED" or not processing["fov_used_for_model_input"]
                        or field.get("mask_sha256") != binding["mask_sha256"]
                        or field.get("mask_version") != MASK_VERSION
                        or field.get("source_rgb_sha256") != binding["wire_rgb_sha256"]):
                    raise BoundPlanError("APPLIED_MASK_RECEIPT_MISMATCH")
                applied = decode(base64.b64decode(field["field_mask_png_base64"], validate=True), mode="L")
                if applied.tobytes() != decode(frozen.mask_png, mode="L").tobytes():
                    raise BoundPlanError("APPLIED_MASK_PIXELS_MISMATCH")
                field["field_mask_png_base64"] = base64.b64encode(frozen.mask_png).decode()
            self.last_processing_evidence = deepcopy(processing)
            if (result.model_id != self.model_id or result.model_version != REVISION
                    or result.modality != request.modality or (result.width, result.height) != wire.size
                    or result.state != "AI_SUGGESTION" or result.provenance.source_type != wire.source_type
                    or result.provenance.image_sha256 != wire.sha256
                    or result.provenance.checkpoint_sha256 != pins["checkpoint_sha256"]
                    or result.provenance.source_revision != pins["source_revision"]
                    or result.provenance.preprocessing != pins["preprocessing"]):
                raise BoundPlanError("BOUND_RESULT_PROVENANCE_MISMATCH")
            return {"result": result.model_dump(mode="json"), "processing_evidence": processing,
                    "preview_receipt": {"plan_sha256": plan_sha256, "wire_sha256": wire.sha256,
                                        "mask_sha256": binding["mask_sha256"], "transform_sha256": binding["transform"]["sha256"]}}
        finally:
            self._active_preparation = None
            try:
                # Validation failures do not import Torch/inspect CUDA.
                if model_work_started:
                    self._release_cuda_memory(self.device)
            finally:
                self._bound_lock.release()

    def result(self, *args, **kwargs):
        value = super().result(*args, **kwargs)
        if self._active_preparation is None or self._loaded_identity is None:
            raise BoundPlanError("BOUND_RESULT_OUTSIDE_EXECUTION")
        # Bound protocol pins a stable pipeline/config. Actual ROI/mode remains
        # explicit typed processing evidence, not an unknown preflight identity.
        return value.model_copy(update={"provenance": value.provenance.model_copy(update={
            "preprocessing": self._loaded_identity["preprocessing"]})})
