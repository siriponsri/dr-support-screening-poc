"""Ephemeral, one-use PRISM wire receipts. No model/FOV imports or DB creation.

A provider must explicitly implement the frozen-plan protocol. Existing local
and remote providers do not; unsupported providers fail closed, never fall back.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import re
import secrets
import struct
from threading import RLock
import time
from typing import Callable, Literal

from fastapi import HTTPException
from fastapi.responses import Response
from PIL import Image
from pydantic import Field

from ..contracts import Contract

PROTOCOL = "prism-wire-binding.v1"
MODEL_ID = "prism-dr-5fold"
MASK_VERSION = "uwf_white_rim_fov_v1"
MAX_PIXELS = 50_000_000
MAX_BYTES = 32 * 1024 * 1024


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def rgb(data: bytes) -> Image.Image:
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413, "Preview representation exceeds the verified size limit.")
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > MAX_PIXELS:
            raise HTTPException(413, "Preview dimensions exceed the verified size limit.")
        image.load()
        return image.convert("RGB")


def rgb_hash(image: Image.Image) -> str:
    return sha(struct.pack(">II", *image.size) + image.tobytes())


def png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    Image.frombytes(image.mode, image.size, image.tobytes()).save(output, format="PNG")
    return output.getvalue()


def preparation_context(case: dict) -> str:
    prep = case.get("analysis_preparation") or {}
    derivative = prep.get("derivative") or case.get("analysis_derivative") or {}
    return json.dumps([
        prep.get("status"), prep.get("source_sha256"), prep.get("candidate_mask_sha256"),
        prep.get("candidate_mask_representation_version"), derivative.get("derivative_sha256"),
        derivative.get("valid_retina_mask_sha256"), derivative.get("transform_id"),
        derivative.get("transform_version"), derivative.get("representation_version"),
    ], separators=(",", ":"))


@dataclass(frozen=True)
class PreviewSnapshot:
    """Created by trusted server code under its store lock, never from a request."""
    scope: str
    image_id: str
    revision: int
    source: bytes
    wire: bytes
    wire_media_type: str
    modality: str
    model_version: str
    model_pins: dict
    transform: dict
    preparation_context: str
    admission: dict
    external_fov_status: str
    external_fov_reason_code: str | None
    mask: bytes | None  # Encoded L-mode PNG, binary, source-provider coordinates.
    mask_version: str | None
    # Handles are pinned to the original store/provider until receipt expiry.
    runtime: object


class PreviewPrepareRequest(Contract):
    revision: int = Field(ge=0, strict=True)
    model_id: Literal["prism-dr-5fold"] = MODEL_ID


class PreviewSubmitRequest(Contract):
    revision: int = Field(ge=0, strict=True)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    wire_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mask_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    transform_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_version: str = Field(min_length=1, max_length=200)


@dataclass
class _Plan:
    snapshot: PreviewSnapshot
    identity: str
    binding: dict
    display: dict
    assets: dict[str, bytes]
    deadline: float
    generation: int
    consumed: bool = False


class PrismPreviewService:
    """Bounded process-local cache. Restart/eviction invalidates receipts safely.

    All snapshot/execute calls run under one supplied transaction lock. The
    workstation must use one worker; there is no distributed receipt guarantee.
    """
    def __init__(self, snapshot: Callable[[str], PreviewSnapshot], execute: Callable,
                 *, lock=None, clock=time.monotonic, ttl=300, max_plans=16,
                 max_cache_bytes=128 * 1024 * 1024):
        self.snapshot = snapshot
        self.execute = execute
        self.lock = lock or RLock()
        self.clock = clock
        self.ttl = ttl
        self.max_plans = max_plans
        self.max_cache_bytes = max_cache_bytes
        self.plans: dict[str, _Plan] = {}
        self.generations: dict[tuple[str, str], int] = {}

    @staticmethod
    def _freeze(snapshot: PreviewSnapshot) -> tuple[dict, dict[str, bytes]]:
        source, wire = rgb(snapshot.source), rgb(snapshot.wire)
        with Image.open(io.BytesIO(snapshot.wire)) as encoded:
            if {"PNG": "image/png", "JPEG": "image/jpeg"}.get(encoded.format) != snapshot.wire_media_type:
                raise HTTPException(409, "Wire media type does not match the frozen encoded bytes.")
        pin_fields = {"model_id", "source_revision", "preprocessing", "config_sha256", "checkpoint_sha256"}
        if set(snapshot.model_pins) != pin_fields:
            raise HTTPException(503, "PRISM pin fields must use the reviewed non-secret schema.")
        pins = deepcopy(snapshot.model_pins)
        checkpoints = pins.get("checkpoint_sha256")
        if (not snapshot.model_version or pins.get("model_id") != MODEL_ID
                or not pins.get("source_revision") or not pins.get("preprocessing")
                or not pins.get("config_sha256") or not checkpoints
                or not isinstance(checkpoints, dict)
                or any(not re.fullmatch(r"[a-f0-9]{64}", str(value)) for value in checkpoints.values())
                or not re.fullmatch(r"[a-f0-9]{64}", str(pins.get("config_sha256")))):
            raise HTTPException(503, "Frozen PRISM model/config/checkpoint pins are unavailable.")
        transform = deepcopy(snapshot.transform)
        mapping = transform.get("original_to_input")
        if (source.size != (transform.get("original_width"), transform.get("original_height"))
                or wire.size != (transform.get("input_width"), transform.get("input_height"))
                or not transform.get("version") or not transform.get("transform_id")
                or not transform.get("representation_version") or not isinstance(mapping, list)
                or len(mapping) != 6):
            raise HTTPException(409, "Wire transform is incomplete.")
        # This checkpoint supports the locked identity/scale representation,
        # never a guessed crop or downstream native-ROI transform.
        expected = [wire.width / source.width, 0, 0, wire.height / source.height, 0, 0]
        inverse = transform.get("coordinate_mapping") or {}
        if (mapping != expected or inverse.get("scale_x") != source.width / wire.width
                or inverse.get("scale_y") != source.height / wire.height):
            raise HTTPException(409, "Wire transform is not the verified source-to-analysis mapping.")
        transform["sha256"] = sha(canonical(transform))
        status = snapshot.external_fov_status
        mask_hash = None
        overlay = None
        retained, excluded = 1.0, 0.0
        if snapshot.mask is not None:
            if snapshot.modality != "UWF" or status != "READY" or snapshot.mask_version != MASK_VERSION:
                raise HTTPException(409, "An unqualified FOV candidate cannot be adopted.")
            if source.size != wire.size:
                raise HTTPException(409, "FOV overlay requires the baseline identity coordinate map.")
            if len(snapshot.mask) > MAX_BYTES:
                raise HTTPException(413, "Candidate mask exceeds the verified size limit.")
            with Image.open(io.BytesIO(snapshot.mask)) as candidate:
                if candidate.mode != "L" or candidate.size != wire.size:
                    raise HTTPException(409, "Candidate mask coordinates do not match the wire image.")
                candidate.load()
                histogram = candidate.histogram()
                if sum(histogram[1:255]) or histogram[255] == 0:
                    raise HTTPException(409, "Candidate mask must retain/exclude binary pixels explicitly.")
                mask_data = candidate.tobytes()
                mask_hash = sha(MASK_VERSION.encode("ascii") + struct.pack(">II", *candidate.size) + mask_data)
                retained = histogram[255] / (wire.width * wire.height)
                excluded = 1 - retained
                colors = Image.new("RGBA", candidate.size, (230, 60, 60, 120))
                colors.paste((36, 180, 95, 120), (0, 0, candidate.width, candidate.height), candidate)
                overlay = png(colors)
        elif status not in {"UNCERTAIN", "UNAVAILABLE", "NOT_APPLICABLE"}:
            raise HTTPException(409, "READY FOV has no frozen mask.")
        if snapshot.modality == "CFP" and status != "NOT_APPLICABLE":
            raise HTTPException(409, "CFP cannot inherit a UWF FOV plan.")
        identity = dict(scope=snapshot.scope, image_id=snapshot.image_id, case_revision=snapshot.revision,
                        source_sha256=sha(snapshot.source), source_rgb_sha256=rgb_hash(source),
                        wire_sha256=sha(snapshot.wire), wire_byte_count=len(snapshot.wire),
                        wire_media_type=snapshot.wire_media_type,
                        wire_dimensions={"width": wire.width, "height": wire.height},
                        wire_rgb_sha256=rgb_hash(wire), modality=snapshot.modality,
                        model_id=MODEL_ID, model_version=snapshot.model_version, model_pins=pins,
                        transform=transform, preparation_context=snapshot.preparation_context,
                        admission={key: snapshot.admission.get(key) for key in (
                            "source_origin", "retinal_modality", "modality_admission", "quality_state")},
                        admission_sha256=sha(canonical(snapshot.admission)), external_fov_status=status,
                        external_fov_reason_code=snapshot.external_fov_reason_code,
                        mask_sha256=mask_hash, mask_version=snapshot.mask_version,
                        mask_png_sha256=sha(snapshot.mask) if snapshot.mask else None)
        assets = {"original": png(source), "input": png(wire)}
        if overlay:
            assets["overlay"] = overlay
        display = dict(identity, mask={"kind": "OPTICAL_FOV" if mask_hash else "NONE",
                                      "version": snapshot.mask_version or "none", "sha256": mask_hash},
                       retained_fraction=retained, excluded_fraction=excluded, uncertain_fraction=0,
                       mask_application="CONDITIONAL_ON_NATIVE_ROI_SUCCESS" if mask_hash else "NONE_PLANNED",
                       input_kind="UNMASKED_WIRE" if mask_hash else "ORIGINAL_FALLBACK",
                       fallback_reason=snapshot.external_fov_reason_code or "No external FOV mask is planned")
        return display, assets

    def _current(self, image_id: str):
        try:
            current = self.snapshot(image_id)
            return current, self._freeze(current)
        except HTTPException:
            raise
        except (ValueError, KeyError, TypeError, OSError, AttributeError):
            raise HTTPException(503, "A verified preview representation is unavailable.") from None

    def _prune(self):
        self.plans = {key: plan for key, plan in self.plans.items() if plan.deadline > self.clock()}
        live = {(plan.snapshot.scope, plan.snapshot.image_id) for plan in self.plans.values()}
        self.generations = {key: value for key, value in self.generations.items() if key in live}

    def prepare(self, image_id: str, revision: int) -> dict:
        with self.lock:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", image_id):
                raise HTTPException(422, "Invalid image identity.")
            self._prune()
            snapshot, (identity, assets) = self._current(image_id)
            if snapshot.revision != revision:
                raise HTTPException(409, "Case changed before preview preparation.")
            size = sum(map(len, assets.values())) + len(snapshot.source) + len(snapshot.wire) + len(snapshot.mask or b"")
            if size > self.max_cache_bytes:
                raise HTTPException(413, "Frozen preview exceeds the cache size limit.")
            while self.plans and (len(self.plans) >= self.max_plans or size + sum(
                    sum(map(len, plan.assets.values())) + len(plan.snapshot.source)
                    + len(plan.snapshot.wire) + len(plan.snapshot.mask or b"") for plan in self.plans.values()) > self.max_cache_bytes):
                self.plans.pop(next(iter(self.plans)))
            token = secrets.token_hex(24)
            generation = self.generations.get((snapshot.scope, image_id), 0)
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.ttl)).isoformat()
            binding = dict(identity, plan_id=token, generation=generation, expires_at=expires_at)
            binding_hash = sha(canonical(binding))
            display = deepcopy(identity)
            for key in ("scope", "admission"):
                display.pop(key)
            display.update(schema_version="prism-input-preview.v1", status="READY", plan_id=token,
                           plan_sha256=binding_hash, baseline_preserved=True, candidate_applied=False,
                           submission_binding_enforced=True, preview_scope="API_SUBMISSION",
                           internal_roi="NOT_PREVIEWED", native_roi_status="NOT_RUN", native_roi_bbox=None,
                           exact_lesion_input_available=False, final_crop_or_tensor_sha256=None,
                           expires_at=expires_at)
            for name, data in assets.items():
                asset = {"url": f"/v1/cases/{image_id}/prism-input-preview/{token}/assets/{name}", "sha256": sha(data)}
                if name == "input":
                    asset["rgb_sha256"] = identity["wire_rgb_sha256"]
                display[{"original": "original_preview", "input": "input_preview", "overlay": "overlay"}[name]] = asset
            display.setdefault("overlay", None)
            self.plans[token] = _Plan(snapshot, sha(canonical(identity)), binding, display, assets,
                                      self.clock() + self.ttl, generation)
            return deepcopy(display)

    def _validate(self, image_id: str, token: str) -> _Plan:
        self._prune()
        plan = self.plans.get(token)
        if plan is None or plan.snapshot.image_id != image_id or plan.consumed:
            raise HTTPException(409, "Preview is missing, consumed or belongs to another case.")
        current, (identity, _) = self._current(image_id)
        if (plan.identity != sha(canonical(identity)) or current.scope != plan.snapshot.scope
                or self.generations.get((current.scope, image_id), 0) != plan.generation):
            raise HTTPException(409, "Preview is stale; prepare a new input plan.")
        return plan

    def asset(self, image_id: str, token: str, name: str) -> bytes:
        with self.lock:
            plan = self._validate(image_id, token)
            if name not in plan.assets:
                raise HTTPException(404, "Preview asset unavailable.")
            return plan.assets[name]

    def submit(self, image_id: str, token: str, request: PreviewSubmitRequest):
        with self.lock:
            plan = self._validate(image_id, token)
            expected = dict(revision=plan.snapshot.revision, source_sha256=plan.display["source_sha256"],
                            wire_sha256=plan.display["wire_sha256"], plan_sha256=plan.display["plan_sha256"],
                            mask_sha256=plan.display["mask"]["sha256"],
                            transform_sha256=plan.display["transform"]["sha256"], model_version=plan.snapshot.model_version)
            if request.model_dump() != expected:
                raise HTTPException(409, "Submission does not match the verified preview receipt.")
            plan.consumed = True  # Failure/timeout never implicitly retries a model call.
            key = (plan.snapshot.scope, image_id)
            self.generations[key] = plan.generation + 1  # Invalidate sibling plans too.
            try:
                return self.execute(plan.snapshot, deepcopy(plan.binding), plan.display["plan_sha256"],
                                    still_valid=lambda: self.clock() < plan.deadline)
            except HTTPException:
                raise
            except (ValueError, KeyError, TypeError, OSError, AttributeError, RuntimeError):
                raise HTTPException(502, "PRISM execution failed verification; this receipt cannot be reused.") from None


def install_prism_preview_routes(app, service: PrismPreviewService):
    @app.post("/v1/cases/{image_id}/prism-input-preview")
    def prepare(image_id: str, request: PreviewPrepareRequest):
        return service.prepare(image_id, request.revision)

    @app.get("/v1/cases/{image_id}/prism-input-preview/{token}/assets/{name}")
    def asset(image_id: str, token: str, name: str):
        return Response(service.asset(image_id, token, name), media_type="image/png",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.post("/v1/cases/{image_id}/prism-input-preview/{token}/infer")
    def submit(image_id: str, token: str, request: PreviewSubmitRequest):
        return service.submit(image_id, token, request)
