"""Derived annotation-assist visibility only. No exclusion algorithm or model.

Provider is explicitly injected after core review; absent/unknown/stale evidence
retains suggestions. Raw detections and all human/clinical state are untouched.
"""

import base64
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import os

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response
from PIL import Image
from pydantic import BaseModel, Field

from ..presentation import lesion_review_view
from .source_identity import source_identity_reason


POLICY = "annotation-artifact-visibility.v1"
FLAG = "DR_SUPPORT_ANNOTATION_ASSIST_ARTIFACT_ROI"
MAX_MASK_BYTES = 2_000_000
_UNSET = object()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def enabled():
    return os.environ.get(FLAG) == "1" and os.environ.get("APP_PROFILE", "review") == "review"


def suggestions(case):
    return deepcopy((lesion_review_view(case.get("lesion")) or {}).get("lesions", []))


def input_binding(case, image):
    width, height = image.size
    return {"source_sha256": image.sha256, "raw_result_sha256": digest(case.get("lesion")),
            "image_id": image.image_id, "width": width, "height": height,
            "coordinate_space": "ORIGINAL", "transform_version": "identity-original-pixels.v1"}


def scope_for_app(app, store):
    profile = getattr(getattr(app.state, "workspace_manager", None), "active_workspace", None)
    database = getattr(store, "database", None)
    return digest({"workspace_id": getattr(app.state, "workspace_id", None) or getattr(profile, "id", None),
                   "schema": getattr(getattr(database, "settings", None), "schema", None),
                   "legacy_store": digest(str(getattr(store, "path", "")))})


def scoped_binding(case, image, scope):
    return {**input_binding(case, image), "scope_sha256": scope}


def decision_digest(state):
    return digest({key: state[key] for key in (
        "input_binding", "provider_identity", "mask_png_sha256", "suppressed", "policy_version",
        "status", "evidence_kind", "shadow_proposals", "proposal_metadata", "mask_semantics")})


def intact_mask(state):
    png = base64.b64decode(state["mask_png_base64"], validate=True)
    return (0 < len(png) <= MAX_MASK_BYTES
            and hashlib.sha256(png).hexdigest() == state["mask_png_sha256"]
            and decision_digest(state) == state["binding_sha256"])


def protected_ids(case):
    # Any existing explicit human decision/derivation stays authoritative.
    return {entry.get("detection_id") for entry in case.get("ai_annotation_reviews", [])} | {
        entry.get("source_detection_id") for entry in case.get("human_annotations", [])}


def source_unresolved(case, image, admission_projection=_UNSET):
    admission = case.get("admission") or {}
    if admission_projection is not _UNSET and admission_projection != case.get("admission"):
        return "ADMISSION_PROJECTION_MISMATCH"
    metadata = admission.get("source_metadata") or {}
    return (source_identity_reason(case, image, admission)
            or (isinstance(metadata, dict)
                and metadata.get("integrity_status") not in {None, "OK", "DUPLICATE_CONTENT"})
            or any(value is not None and value != image.sha256 for value in (
                case.get("source_sha256"), case.get("image_sha256"),
                metadata.get("source_sha256") if isinstance(metadata, dict) else "INVALID")))


def all_visible(case, status, *, active=True, scope=None):
    rows = suggestions(case)
    return {"enabled": active, "status": status, "policy_version": POLICY,
            "visible_ids": [row["detection_id"] for row in rows], "suppressed_ids": [],
            "suppressed": [], "restored_ids": [], "binding_sha256": None, "overlay_url": None,
            "provenance_class": "NON_GOLD_AI_VISIBILITY_ONLY",
            "negative_labels_from_suppression": False, "scope_sha256": scope}


def project(case, image, provider=None, *, scope=None, admission=_UNSET):
    if not enabled():
        return all_visible(case, "DISABLED", active=False, scope=scope)
    state = case.get("artifact_roi_assist")
    if not state:
        return all_visible(case, "NOT_PREPARED", scope=scope)
    if state.get("status") not in {"READY", "SHADOW_ONLY"}:
        return all_visible(case, state.get("status", "UNAVAILABLE_RETAINED_ALL"), scope=scope)
    try:
        if (image is None or state["input_binding"] != scoped_binding(case, image, scope)
                or source_unresolved(case, image, admission)
                or provider is None or state["provider_identity"] != provider.identity()
                or state["policy_version"] != POLICY or not intact_mask(state)):
            return all_visible(case, "STALE_OR_UNAVAILABLE_RETAINED_ALL", scope=scope)
        public = {key: deepcopy(value) for key, value in state.items()
                  if key not in {"mask_png_base64", "restore_history"}}
        restored = set(state["restored_ids"]) | protected_ids(case)
        suppressed = [row for row in state["suppressed"] if row["detection_id"] not in restored]
        public["suppressed"] = suppressed
        public["shadow_proposals"] = [row for row in public.get("shadow_proposals", [])
                                      if row["detection_id"] not in restored]
        public["suppressed_ids"] = [row["detection_id"] for row in suppressed]
        public["visible_ids"] = [row["detection_id"] for row in suggestions(case)
                                 if row["detection_id"] not in set(public["suppressed_ids"])]
        public["enabled"] = True
        public["overlay_url"] = (f"/v1/cases/{image.image_id}/artifact-roi/overlay"
                                 f"?binding_sha256={state['binding_sha256']}") if state.get("mask_png_base64") else None
        return public
    except Exception:
        return all_visible(case, "INVALID_BINDING_RETAINED_ALL", scope=scope)


def prepare(case, image, provider, *, scope=None, admission=_UNSET):
    rows = suggestions(case)
    baseline = all_visible(case, "UNAVAILABLE_RETAINED_ALL", scope=scope)
    if (image is None or (case.get("admission") or {}).get("retinal_modality") != "UWF"
            or source_unresolved(case, image, admission)):
        return {**baseline, "status": "SOURCE_OR_MODALITY_UNRESOLVED_RETAINED_ALL"}
    raw = case.get("lesion") or {}
    if (raw.get("model_id") != "prism-dr-5fold"
            or (raw.get("width"), raw.get("height")) != image.size
            or (raw.get("provenance") or {}).get("image_sha256") != image.sha256):
        return {**baseline, "status": "UNKNOWN_TRANSFORM_RETAINED_ALL"}
    if provider is None:
        return baseline
    try:
        identity = deepcopy(provider.identity())
        if (not isinstance(identity, dict) or not identity.get("method_version")
                or not identity.get("mask_version")):
            return baseline
        binding = input_binding(case, image)
        ids = [row["detection_id"] for row in rows]
        if len(set(ids)) != len(ids):
            return {**baseline, "status": "AMBIGUOUS_IDS_RETAINED_ALL"}
        # CPU core adapter returns already-decided IDs. No geometry/mask policy
        # is implemented here; task-2 owns the sure-exclude decision algorithm.
        from .artifact_roi_core_adapter import TechnicalFrameArtifactProvider, bind_full_result_packet
        from .artifact_roi_shadow_adapter import EmpiricalRimShadowProvider
        from .artifact_roi_replay import CachedArtifactReplayProvider
        from .artifact_roi_generic_adapter import GenericUwfArtifactProvider, REASON
        generic = type(provider) is GenericUwfArtifactProvider
        packet = (provider.derive_bound(case, image, deepcopy(rows)) if type(provider) in {CachedArtifactReplayProvider, GenericUwfArtifactProvider}
                  else bind_full_result_packet(provider, case, image, deepcopy(rows))
                  if type(provider) in {TechnicalFrameArtifactProvider, EmpiricalRimShadowProvider}
                  else provider.derive(image, deepcopy(rows)))
        png = packet.get("exclude_mask_png")
        if (packet.get("status") not in {"READY", "SHADOW_ONLY"} or packet.get("input_binding") != binding
                or packet.get("provider_identity") != identity
                or not isinstance(png, bytes) or not 0 < len(png) <= MAX_MASK_BYTES
                or packet.get("mask_png_sha256") != hashlib.sha256(png).hexdigest()):
            return {**baseline, "status": packet.get("status") if packet.get("status") in {
                "TECHNICAL_FRAME_UNAVAILABLE_RETAINED_ALL", "UNKNOWN_SOURCE_BINDING_RETAINED_ALL",
                "EMPIRICAL_SHADOW_UNAVAILABLE_RETAINED_ALL", "CACHED_REPLAY_UNAVAILABLE_RETAINED_ALL", "GENERIC_UWF_RETAINED_ALL"}
                else "UNAVAILABLE_RETAINED_ALL"}
        with Image.open(io.BytesIO(png)) as mask:
            if (mask.format != "PNG" or mask.mode != "L" or mask.size != image.size
                    or not {color for _, color in mask.getcolors(maxcolors=257)} <= {0, 255}):
                return baseline
        suppressed = packet.get("suppressed")
        expected_reason = REASON if generic else "EMPIRICAL_ARTIFACT_PROPOSAL" if packet["status"] == "SHADOW_ONLY" else "SURE_EXCLUDED_ARTIFACT"
        if (not isinstance(suppressed, list) or len(suppressed) > len(ids)
                or any(not isinstance(row, dict) or set(row) != {"detection_id", "reason"}
                       or row["detection_id"] not in ids or row["reason"] != expected_reason
                       for row in suppressed)
                or len({row["detection_id"] for row in suppressed}) != len(suppressed)):
            return baseline
        state = {**baseline, "status": packet["status"], "input_binding": scoped_binding(case, image, scope),
                 "provider_identity": identity, "mask_png_sha256": packet["mask_png_sha256"],
                 "evidence_kind": identity.get("evidence_kind", "INJECTED_TEST_ADAPTER"),
                 "mask_semantics": ("255=EMPIRICAL_EXCLUSION_CORE_CANDIDATE;0=RETAIN_OR_UNCERTAIN" if generic else "255=EMPIRICAL_ARTIFACT_PROPOSAL_ONLY;0=RETAIN_OR_UNCERTAIN"
                                    if packet["status"] == "SHADOW_ONLY"
                                    else "255=TECHNICAL_EXCLUDE_CORE;0=RETAIN_OR_UNCERTAIN"),
                 "suppressed": [deepcopy(row) for row in suppressed if row["detection_id"] not in protected_ids(case)],
                 "mask_png_base64": base64.b64encode(png).decode(), "restore_history": []}
        state["shadow_proposals"] = deepcopy(state["suppressed"]) if state["status"] == "SHADOW_ONLY" else []
        metadata = packet.get("proposal_metadata") or {}
        if len(canonical(metadata)) > 65536:
            return baseline
        state["proposal_metadata"] = deepcopy(metadata)
        if state["status"] == "SHADOW_ONLY":
            state["suppressed"] = []
        state["binding_sha256"] = decision_digest(state)
        previous = case.get("artifact_roi_assist") or {}
        if previous.get("binding_sha256") == state["binding_sha256"]:
            state["restored_ids"] = deepcopy(previous.get("restored_ids", []))
            state["restore_history"] = deepcopy(previous.get("restore_history", []))
        state["suppressed_ids"] = [row["detection_id"] for row in state["suppressed"]
                                   if row["detection_id"] not in state["restored_ids"]]
        state["visible_ids"] = [key for key in ids if key not in state["suppressed_ids"]]
        return state
    except Exception:
        return {**baseline, "status": "CORE_FAILED_RETAINED_ALL"}


class PrepareRequest(BaseModel):
    revision: int = Field(strict=True, ge=0)
    scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class RestoreRequest(PrepareRequest):
    binding_sha256: str
    detection_ids: list[str] = Field(max_length=500)


def install(app, detail, current_store, get_image, require_current):
    from .source_mutation_gate import guard_writes
    mutation_gate = lambda: getattr(app.state, "source_mutation_gate", None)
    def gate():
        if not enabled():
            raise HTTPException(404, "Annotation-assist artifact view is disabled")

    @contextmanager
    def locked(image_id):
        with app.state.workspace_manager.lock:
            store = current_store()
            with store.lock:
                yield store, get_image(image_id), scope_for_app(app, store)

    def read_field(image_id):
        # Source identity is required; quality, physician review, a model
        # result and inference eligibility are deliberately irrelevant here.
        from .artifact_roi_generic_adapter import GenericUwfArtifactProvider
        with locked(image_id) as (store, image, scope):
            case = store.get(image_id)
            admission = app.state.admissions.get(image_id)
            # Read-only snapshots may not yet have hydrated case.admission.
            # Join the actual admitted projection locally; never replace an
            # existing conflicting record or persist this image-only read.
            if case.get("admission") is None and admission is not None:
                case = {**case, "admission": deepcopy(admission)}
            if image is None or source_unresolved(case, image, admission):
                raise HTTPException(409, "Source identity changed; reload image-only field")
            if image.modality != "UWF":
                raise HTTPException(422, "Image-only field is an experimental UWF annotation assist")
            provider = getattr(app.state, "artifact_roi_provider", None)
            if type(provider) is not GenericUwfArtifactProvider:
                provider = GenericUwfArtifactProvider()
            return provider.image_field(image)

    @app.get("/v1/cases/{image_id}/artifact-roi/field")
    def field_metadata(image_id: str):
        gate()
        value, png = read_field(image_id)
        value["overlay_url"] = (f"/v1/cases/{image_id}/artifact-roi/field/overlay"
             f"?source_sha256={value['source_sha256']}&field_sha256={value['field_sha256']}") if png else None
        return JSONResponse(value, headers={"Cache-Control": "no-store"})

    @app.get("/v1/cases/{image_id}/artifact-roi/field/overlay")
    def field_overlay(image_id: str, source_sha256: str, field_sha256: str):
        gate()
        value, png = read_field(image_id)
        if value["source_sha256"] != source_sha256 or value["field_sha256"] != field_sha256 or not png:
            raise HTTPException(409, "Image-only annotation field changed or is unavailable")
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store",
                        "X-Source-SHA256": value["source_sha256"], "X-Field-SHA256": value["field_sha256"]})

    @app.post("/v1/cases/{image_id}/artifact-roi/prepare")
    @guard_writes(mutation_gate)
    def refresh(image_id: str, request: PrepareRequest):
        gate()
        with locked(image_id) as (store, image, scope):
            case = store.get(image_id)
            if case["revision"] != request.revision or request.scope_sha256 != scope:
                raise HTTPException(409, "Case changed; reload artifact view")
            try:
                require_current(case, image, case.get("admission") or {})
                state = prepare(case, image, getattr(app.state, "artifact_roi_provider", None), scope=scope,
                                admission=app.state.admissions.get(image_id))
            except HTTPException:
                state = all_visible(case, "STALE_RESULT_RETAINED_ALL", scope=scope)
            # Preparing an identical visibility view is a read-equivalent retry.
            # Derived membership may differ after restore; its authoritative
            # restored_ids/history remain part of the equality check.
            derived = {"visible_ids", "suppressed_ids"}
            previous = case.get("artifact_roi_assist") or {}
            if ({key: value for key, value in previous.items() if key not in derived}
                    == {key: value for key, value in state.items() if key not in derived}
                    and (not state.get("mask_png_base64")
                         or (case.get("artifact_roi_masks") or {}).get(state["mask_png_sha256"])
                         == state["mask_png_base64"])):
                return detail(image_id)
            if state.get("mask_png_base64"):
                masks = case.setdefault("artifact_roi_masks", {})
                prior = masks.get(state["mask_png_sha256"])
                if prior is not None and prior != state["mask_png_base64"]:
                    state = all_visible(case, "INVALID_MASK_ARCHIVE_RETAINED_ALL", scope=scope)
                else:
                    masks.setdefault(state["mask_png_sha256"], state["mask_png_base64"])
            case["artifact_roi_assist"] = state
            # No clinical event/review/completeness/annotation hash is touched.
            case.setdefault("artifact_roi_history", []).append({
                key: deepcopy(value) for key, value in state.items() if key != "mask_png_base64"})
            case["revision"] += 1
            store.put(case)
            return detail(image_id)

    @app.post("/v1/cases/{image_id}/artifact-roi/restore")
    @guard_writes(mutation_gate)
    def restore(image_id: str, request: RestoreRequest):
        gate()
        with locked(image_id) as (store, image, scope):
            case = store.get(image_id)
            view = project(case, image, getattr(app.state, "artifact_roi_provider", None), scope=scope,
                           admission=app.state.admissions.get(image_id))
            if (case["revision"] != request.revision or request.scope_sha256 != scope or view["status"] != "READY"
                    or request.binding_sha256 != view["binding_sha256"]
                    or not set(request.detection_ids) <= set(view["suppressed_ids"])):
                raise HTTPException(409, "Artifact binding changed; retained suggestions require reload")
            state = case["artifact_roi_assist"]
            state["restored_ids"] = sorted(set(state["restored_ids"]) | set(request.detection_ids))
            event = {"action": "RESTORE_AI_VISIBILITY", "detection_ids": list(request.detection_ids),
                     "binding_sha256": state["binding_sha256"], "scope_sha256": scope,
                     "case_revision": case["revision"] + 1,
                     "timestamp": datetime.now(timezone.utc).isoformat(),
                     "provenance_class": "NON_GOLD_AI_VISIBILITY_ONLY"}
            state["restore_history"].append(deepcopy(event))
            # Keep restores across later source/model/mask re-preparations too.
            case.setdefault("artifact_roi_history", []).append(deepcopy(event))
            case["revision"] += 1
            store.put(case)
            return detail(image_id)

    @app.get("/v1/cases/{image_id}/artifact-roi/overlay")
    def overlay(image_id: str, binding_sha256: str):
        gate()
        with locked(image_id) as (store, image, scope):
            case = store.get(image_id)
            view = project(case, image, getattr(app.state, "artifact_roi_provider", None), scope=scope,
                           admission=app.state.admissions.get(image_id))
            if view["status"] not in {"READY", "SHADOW_ONLY"} or view["binding_sha256"] != binding_sha256:
                raise HTTPException(409, "Artifact overlay is stale or unavailable")
            binary = Image.open(io.BytesIO(base64.b64decode(case["artifact_roi_assist"]["mask_png_base64"])))
            rgba = Image.new("RGBA", binary.size, (255, 120, 0, 0))
            rgba.putalpha(binary.point(lambda value: 100 if value == 255 else 0))
            output = io.BytesIO()
            rgba.save(output, "PNG")
            return Response(output.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


def export_rows(cases, *, images=None, admissions=None, provider=None, scope=None):
    """Separate non-gold sidecar; never creates a negative or a training label."""
    rows = []
    for case in cases:
        if not case.get("artifact_roi_assist"):
            continue
        historical = {key: deepcopy(value) for key, value in case["artifact_roi_assist"].items()
                      if key != "mask_png_base64"}
        # Active membership uses precisely the same policy as UI/restore/overlay:
        # source authorities, integrity, mask, raw result, provider, mode and scope.
        # Missing image authority cannot be reconstructed from an old receipt.
        state = project(case, (images or {}).get(case["image_id"]), provider, scope=scope,
                        admission=admissions.get(case["image_id"]) if admissions is not None else _UNSET)
        if (historical.get("status") in {"READY", "SHADOW_ONLY"}
                and state["status"] not in {"READY", "SHADOW_ONLY", "DISABLED"}):
            state["status"] = "STALE_RETAIN_ALL"
        # A live display URL is not a portable dataset artifact.
        state["overlay_url"] = None
        rows.append({"image_id": case["image_id"], "case_revision": case.get("revision"),
             "provenance_class": "NON_GOLD_AI_VISIBILITY_ONLY",
             "negative_labels_from_suppression": False,
             "state": state, "historical_decision": historical,
             "history": deepcopy(case.get("artifact_roi_history", []))})
    return rows
