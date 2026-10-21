"""Review-runtime adapter for frozen receipts; no model import or startup."""
from copy import deepcopy
from dataclasses import dataclass
import os
import secrets
from weakref import WeakKeyDictionary

from fastapi import HTTPException

from ..contracts import InferenceRequest, LesionResult, PrismProcessingEvidence
from .prism_preview import (
    MODEL_ID, PROTOCOL, PreviewSnapshot, PrismPreviewService, canonical, preparation_context, sha,
)


@dataclass(frozen=True)
class _Runtime:
    store: object
    provider: object
    wire: object
    derivative: object
    capability_id: str


class ReviewPrismPreview:
    def __init__(self, app, *, save_result, source_allowed, eligible, route, map_result, inference_lock):
        self.app = app
        self.save_result = save_result
        self.source_allowed = source_allowed
        self.eligible = eligible
        self.route = route
        self.map_result = map_result
        self.inference_lock = inference_lock
        self.scopes = WeakKeyDictionary()

    def snapshot(self, image_id):
        if os.environ.get("WORKERS", "1") != "1":
            raise HTTPException(503, "Preview binding requires the qualified single-worker review runtime.")
        state = self.app.state
        store = state.store
        with store.lock:
            image = state.images.get(image_id)
            admission = deepcopy(state.admissions.get(image_id) or {})
            if image is None:
                raise HTTPException(404, "Image not admitted.")
            if not self.source_allowed(admission.get("source_origin", "UNKNOWN")) or not self.eligible(admission):
                raise HTTPException(409, "Source/admission is not eligible for PRISM.")
            case = store.get(image_id)
            modality = admission.get("retinal_modality")
            if modality not in {"CFP", "UWF"}:
                raise HTTPException(409, "Confirmed image type is required.")
            for recorded in (case.get("source_sha256"), admission.get("source_sha256")):
                if recorded and recorded != image.sha256:
                    raise HTTPException(409, "Source identity changed.")
            if case.get("admission") and case["admission"] != admission:
                raise HTTPException(409, "Admission projections disagree; reload the case.")
            provider = state.providers.get(MODEL_ID)
            if (getattr(provider, "prism_preview_protocol", None) != PROTOCOL
                    or not callable(getattr(provider, "prism_preview_identity", None))
                    or not callable(getattr(provider, "prepare_prism_preview_candidate", None))
                    or not callable(getattr(provider, "infer_bound_prism", None))):
                raise HTTPException(503, "PRISM provider cannot enforce a frozen preview receipt.")
            identity = deepcopy(provider.prism_preview_identity())
            descriptor = identity["descriptor"]
            route = self.route(descriptor, modality)
            if (admission["source_origin"] == "HOSPITAL_AUTHORIZED"
                    and "HOSPITAL_AUTHORIZED" not in descriptor.get("authorized_source_origins", [])):
                raise HTTPException(409, "Model is not authorized for this source origin.")
            wire, derivative = state.derivatives.analysis_image(
                image, source_modality=modality, apply_uwf_mask=modality != "UWF",
            )
            audit = derivative.audit_record()
            if audit["source_sha256"] != image.sha256 or audit["analysis_sha256"] != wire.sha256:
                raise HTTPException(409, "Prepared wire lineage is inconsistent.")
            candidate = (provider.prepare_prism_preview_candidate(wire) if modality == "UWF" else
                         {"status": "NOT_APPLICABLE", "reason_code": None, "mask_png": None, "mask_version": None})
            width, height = image.size
            input_width, input_height = wire.size
            transform = dict(version=str(audit["transform_version"]), transform_id=audit["transform_id"],
                             representation_version=audit["representation_version"],
                             coordinate_mapping=derivative.coordinate_mapping.model_dump(mode="json"),
                             original_width=width, original_height=height,
                             input_width=input_width, input_height=input_height,
                             original_to_input=[input_width / width, 0, 0, input_height / height, 0, 0])
            self.scopes.setdefault(store, secrets.token_hex(16))
            return PreviewSnapshot(
                scope=self.scopes[store], image_id=image_id, revision=case["revision"], source=bytes(image.data),
                wire=bytes(wire.data), wire_media_type=wire.media_type, modality=modality,
                model_version=identity["model_version"], model_pins=identity["model_pins"], transform=transform,
                preparation_context=preparation_context(case), admission=admission,
                external_fov_status=candidate["status"], external_fov_reason_code=candidate.get("reason_code"),
                mask=bytes(candidate["mask_png"]) if candidate.get("mask_png") is not None else None,
                mask_version=candidate.get("mask_version"),
                runtime=_Runtime(store, provider, wire, derivative, route.capability_id),
            )

    def execute(self, snapshot, binding, plan_hash, *, still_valid):
        with self.inference_lock:
            return self._execute_locked(snapshot, binding, plan_hash, still_valid)

    def _execute_locked(self, snapshot, binding, plan_hash, still_valid):
        runtime = snapshot.runtime
        with runtime.store.lock:
            if self.app.state.store is not runtime.store:
                raise HTTPException(409, "Workspace changed; prepare a new preview.")
            fresh = self.snapshot(snapshot.image_id)
            identity, _ = PrismPreviewService._freeze(fresh)
            frozen = {key: value for key, value in binding.items() if key not in {"plan_id", "generation", "expires_at"}}
            if (identity != frozen or fresh.runtime.provider is not runtime.provider
                    or sha(canonical(binding)) != plan_hash):
                raise HTTPException(409, "Preview changed before provider execution.")
            if not still_valid():
                raise HTTPException(409, "Preview expired while waiting for the provider.")
            request = InferenceRequest(image_id=snapshot.image_id, modality=snapshot.modality, model_id=MODEL_ID)
        # The explicit protocol must consume this wire/mask/binding as frozen,
        # atomically validate pins before forward, and return its wire receipt.
        returned = runtime.provider.infer_bound_prism(
            request, runtime.wire, mask_png=snapshot.mask,
            binding=deepcopy(binding), plan_sha256=plan_hash,
        )
        if returned.get("preview_receipt") != {"plan_sha256": plan_hash, "wire_sha256": sha(snapshot.wire),
                                               "mask_sha256": binding["mask_sha256"],
                                               "transform_sha256": binding["transform"]["sha256"]}:
            raise HTTPException(502, "Provider did not attest the accepted input receipt.")
        result = LesionResult.model_validate(returned["result"])
        pins = binding["model_pins"]
        if (result.model_id != MODEL_ID or result.model_version != snapshot.model_version
                or result.modality != snapshot.modality
                or result.provenance.image_sha256 != sha(snapshot.wire)
                or result.provenance.source_type != snapshot.admission["source_origin"]
                or result.provenance.checkpoint_sha256 != pins["checkpoint_sha256"]
                or result.provenance.source_revision != pins["source_revision"]
                or result.provenance.preprocessing != pins["preprocessing"]
                or (result.width, result.height) != runtime.wire.size):
            raise HTTPException(502, "Provider result provenance does not match the frozen input.")
        processing = returned.get("processing_evidence")
        if snapshot.modality == "UWF":
            processing = PrismProcessingEvidence.model_validate(processing).model_dump(mode="json")
            if processing["input_image_sha256"] != sha(snapshot.wire):
                raise HTTPException(502, "PRISM processing evidence belongs to different input.")
            if (processing["external_fov_status"] != binding["external_fov_status"]
                    or len(processing["raw_boundary_classes"]) != len(result.lesions)):
                raise HTTPException(502, "PRISM processing metadata changed from the frozen plan.")
            if processing["native_roi_status"] == "FAILED":
                if (processing["processing_mode"] != "FALLBACK" or processing["fov_used_for_model_input"]
                        or processing["analysis_field"] is not None):
                    raise HTTPException(502, "Native ROI failure must discard the conditional FOV.")
            elif binding["mask_sha256"] is not None:
                field = processing["analysis_field"] or {}
                if (processing["processing_mode"] != "PREPARED" or not processing["fov_used_for_model_input"]
                        or field.get("mask_sha256") != binding["mask_sha256"]
                        or field.get("mask_version") != binding["mask_version"]
                        or field.get("source_rgb_sha256") != binding["wire_rgb_sha256"]
                        or (field.get("image_width"), field.get("image_height")) != runtime.wire.size):
                    raise HTTPException(502, "Applied FOV does not match the reviewed conditional mask.")
        result = self.map_result(result, runtime.derivative.coordinate_mapping)
        applied = self.save_result(request, "lesion-roi", result, runtime.derivative,
                         capability_id=runtime.capability_id, invocation_id="preview-" + binding["plan_id"],
                         request_case_revision=snapshot.revision, processing_evidence=processing,
                         target_store=runtime.store, target_provider=runtime.provider,
                         preview_binding={"plan_sha256": plan_hash, **binding})
        return {"status": "STALE_RESULT" if applied is False else "APPLIED",
                "result": result.model_dump(mode="json"),
                "preview_receipt": {"plan_id": binding["plan_id"], "plan_sha256": plan_hash,
                                    "wire_sha256": binding["wire_sha256"]}}
