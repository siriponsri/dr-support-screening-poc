"""Review-runtime adapter for frozen receipts; no model import or startup."""
from copy import deepcopy
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
import os
import secrets
from weakref import WeakKeyDictionary

from fastapi import HTTPException

from ..contracts import InferenceRequest, LesionResult, PrismProcessingEvidence
from .prism_preview import (
    MODEL_ID, PROTOCOL, PreviewSnapshot, PrismPreviewService, canonical, preparation_context, sha,
)
from .source_identity import source_identity_reason


@dataclass(frozen=True)
class _Runtime:
    store: object
    provider: object
    wire: object
    derivative: object
    capability_id: str


class ReviewPrismPreview:
    def __init__(self, app, *, save_result, source_allowed, eligible, route, map_result, inference_lock,
                 workspace_authority=None):
        self.app = app
        self.save_result = save_result
        self.source_allowed = source_allowed
        self.eligible = eligible
        self.route = route
        self.map_result = map_result
        self.inference_lock = inference_lock
        self.scopes = WeakKeyDictionary()
        # Internal composition only. The ordinary app factory never supplies
        # this port; its presence does not qualify a provider or open a route.
        self.workspace_authority = workspace_authority
        if workspace_authority is not None:
            self._workspace_authority()

    def _workspace_authority(self):
        authority = self.workspace_authority
        if authority is None:
            return None
        from .prism_workspace_authority import WorkspaceAuthority
        state = self.app.state
        if (type(authority) is not WorkspaceAuthority
                or getattr(state, 'qa_fixed_session', None) is not None
                or getattr(state, 'qa_batch_profile', None) is not None
                or getattr(state, 'source_mutation_gate', None) is not authority.gate
                or getattr(state.store, 'source_mutation_gate', None) is not authority.gate
                or getattr(getattr(state, 'workspace_manager', None), 'source_mutation_gate', None)
                    is not authority.gate):
            raise ValueError('EXACT_WORKSPACE_AUTHORITY_AND_SHARED_WRITER_GATE_REQUIRED')
        return authority

    def register_workspace_plan(self, snapshot, binding, plan_hash):
        """Private plan callback for a separately qualified app composition."""
        authority = self._workspace_authority()
        if authority is None:
            raise ValueError('WORKSPACE_AUTHORITY_REQUIRED')
        authority.register_preview_plan(snapshot, binding, plan_hash)

    @contextmanager
    def _context_scope(self):
        authority = self._workspace_authority()
        # Consistent authority -> manager -> store order. These are synchronous
        # operations; no thread lock survives an ASGI await. The legacy path
        # keeps its original store-only scope.
        with authority.lock if authority is not None else nullcontext():
            manager = self.app.state.workspace_manager if authority is not None else None
            with manager.lock if manager is not None else nullcontext():
                yield

    def refresh(self, frozen):
        return self.snapshot(frozen.image_id, refresh_only=True)

    def snapshot(self, image_id, *, refresh_only=False):
        with self._context_scope():
            return self._snapshot(image_id, refresh_only=refresh_only)

    def _snapshot(self, image_id, *, refresh_only=False):
        if os.environ.get("WORKERS", "1") != "1":
            raise HTTPException(503, "Preview binding requires the qualified single-worker review runtime.")
        state = self.app.state
        authority = self._workspace_authority()
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
            # Hashing a known-invalid admission into a receipt cannot make it
            # eligible. Manual quality acceptance never clears source changes.
            if source_identity_reason(case, image, admission):
                raise HTTPException(409, "Source identity or integrity is unresolved; review the source record.")
            metadata = admission.get("source_metadata") or {}
            if (not isinstance(metadata, dict)
                    or metadata.get("integrity_status") not in {None, "OK", "DUPLICATE_CONTENT"}):
                raise HTTPException(409, "Source metadata integrity is unresolved.")
            # The compatibility helper checks the preferred recorded hash;
            # reject conflicts in either explicitly present cache as well.
            for recorded in (case.get("image_sha256"), case.get("source_sha256"), metadata.get("source_sha256")):
                if recorded is not None and recorded != image.sha256:
                    raise HTTPException(409, "Recorded source identities disagree.")
            if case.get("admission") and case["admission"] != admission:
                raise HTTPException(409, "Admission projections disagree; reload the case.")
            # Both are recorded server projections, never replacements derived
            # from the currently loaded bytes. Legacy gaps remain unsupported.
            case_hash = case.get("source_sha256") or case.get("image_sha256")
            image_recorded = case.get("image_sha256") or metadata.get("source_sha256")
            if not case_hash or not image_recorded:
                raise HTTPException(503, "Recorded source attestation is unavailable; no model work is permitted.")
            known_integrity = [admission.get("integrity_status"), (admission.get("integrity") or {}).get("status"),
                               metadata.get("integrity_status")]
            if not any(value in {"OK", "DUPLICATE_CONTENT"} for value in known_integrity):
                raise HTTPException(503, "Recorded integrity attestation is unavailable.")
            recorded = dict(case_source_sha256=case_hash, admission_source_sha256=admission["source_sha256"],
                            image_recorded_sha256=image_recorded, integrity_status="OK",
                            source_origin=admission["source_origin"], case_revision=case["revision"],
                            admission_sha256=sha(canonical(admission)))
            provider = state.providers.get(MODEL_ID)
            if authority is not None and getattr(provider, 'authority', None) is not authority:
                raise HTTPException(503, 'PRISM provider does not own this workspace authority.')
            if (getattr(provider, "prism_preview_protocol", None) != PROTOCOL
                    or not callable(getattr(provider, "prism_preview_identity", None))
                    or not callable(getattr(provider, "prepare_prism_preview_candidate", None))
                    or not callable(getattr(provider, "get_prism_preview_candidate", None))
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
            self.scopes.setdefault(store, secrets.token_hex(16))
            session = authority if authority is not None else getattr(state, 'qa_fixed_session', None)
            if session is not None and not refresh_only:
                context = dict(scope=self.scopes[store], image_id=image_id, case_revision=case['revision'],
                    source_sha256=image.sha256, wire_sha256=wire.sha256,
                    admission_sha256=sha(canonical(admission)), recorded_source_identity=recorded,
                    admission={key: admission.get(key) for key in ('source_origin', 'retinal_modality', 'modality_admission', 'quality_state')},
                    preparation_context=preparation_context(case), model_pins=identity['model_pins'])
                session.authorize_prepare(wire, context, original_bytes=bytes(image.data))
            # Preparation freezes CFP too; refresh can only read cached bytes.
            candidate_method = provider.get_prism_preview_candidate if refresh_only else provider.prepare_prism_preview_candidate
            try:
                candidate = candidate_method(wire)
            except ValueError:
                raise HTTPException(409, "Frozen candidate is unavailable; prepare a new preview.") from None
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
                recorded_source_identity=recorded,
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
        with self._context_scope(), runtime.store.lock:
            if self.app.state.store is not runtime.store:
                raise HTTPException(409, "Workspace changed; prepare a new preview.")
            fresh = self.refresh(snapshot)
            identity, _ = PrismPreviewService._freeze(fresh)
            frozen = {key: value for key, value in binding.items() if key not in {"plan_id", "generation", "expires_at"}}
            if (identity != frozen or fresh.runtime.provider is not runtime.provider
                    or sha(canonical(binding)) != plan_hash):
                raise HTTPException(409, "Preview changed before provider execution.")
            if not still_valid():
                raise HTTPException(409, "Preview expired while waiting for the provider.")
            request = InferenceRequest(image_id=snapshot.image_id, modality=snapshot.modality, model_id=MODEL_ID)
        authority = self._workspace_authority()
        if authority is not None:
            authority.authorize_execute(binding, plan_hash)
        # The explicit protocol must consume this wire/mask/binding as frozen,
        # atomically validate pins before forward, and return its wire receipt.
        def before_forward():
            # Called after any provider load, immediately before native ROI.
            # Never reacquire provider locks or recompute the mask here.
            with runtime.store.lock:
                state = self.app.state
                current_image = state.images.get(snapshot.image_id)
                current_case = runtime.store.get(snapshot.image_id)
                current_admission = state.admissions.get(snapshot.image_id) or {}
                if (state.store is not runtime.store or state.providers.get(MODEL_ID) is not runtime.provider
                        or not still_valid() or current_image is None
                        or current_image.sha256 != binding["source_sha256"]
                        or current_case.get("revision") != snapshot.revision
                        or (current_case.get("source_sha256") or current_case.get("image_sha256"))
                            != binding["recorded_source_identity"]["case_source_sha256"]
                        or (current_case.get("image_sha256")
                            or (current_admission.get("source_metadata") or {}).get("source_sha256"))
                            != binding["recorded_source_identity"]["image_recorded_sha256"]
                        or sha(canonical(current_admission)) != binding["admission_sha256"]
                        or source_identity_reason(current_case, current_image, current_admission)
                        or any(value is not None and value != binding["source_sha256"] for value in
                               (current_case.get("image_sha256"), current_case.get("source_sha256")))
                        or preparation_context(current_case) != snapshot.preparation_context):
                    raise HTTPException(409, "Source/context changed before model forward.")
        returned = runtime.provider.infer_bound_prism(
            request, runtime.wire, mask_png=snapshot.mask,
            binding=deepcopy(binding), plan_sha256=plan_hash, before_forward=before_forward,
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
        def save():
            return self.save_result(request, "lesion-roi", result, runtime.derivative,
                         capability_id=runtime.capability_id, invocation_id="preview-" + binding["plan_id"],
                         request_case_revision=snapshot.revision, processing_evidence=processing,
                         target_store=runtime.store, target_provider=runtime.provider,
                         preview_binding={"plan_sha256": plan_hash, **binding})
        session = getattr(self.app.state, 'qa_fixed_session', None)
        applied = session.commit_result(save) if session is not None else save()
        return {"status": "STALE_RESULT" if applied is False else "APPLIED",
                "result": result.model_dump(mode="json"),
                "processing_evidence": processing,
                "preview_receipt": {"plan_id": binding["plan_id"], "plan_sha256": plan_hash,
                                    "wire_sha256": binding["wire_sha256"]}}
