"""Inference for the review app: `infer` (grading and lesion requests to local or remote providers), saving
results onto the case, the PRISM preview routes and the /v1 and /v2 inference routes.

Installed by `api._factory.create_app`; code moved verbatim from create_app."""

import logging
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from dr_support.contracts import (
    GlobalResult,
    InferenceRequest,
    LesionResult,
    Phase3Explanation,
    Phase3InputContext,
    Phase3ModelIdentity,
    Phase3ResultEnvelope,
    Phase3ReviewInferenceRequest,
    Phase3Runtime,
    PrismProcessingEvidence,
)
from dr_support.providers.mock import infer_mock
from dr_support.providers.remote import (
    RemoteAuthorizationError,
    RemoteConnectionLostError,
    RemoteHTTPError,
    RemoteModelError,
    RemoteModelProvider,
    RemoteNotConfiguredError,
    RemoteSchemaError,
    RemoteTimeoutError,
    RemoteUnreachableError,
)

from ..imaging import DerivativeError, DerivativePayloadTooLargeError, map_lesion_result_to_review
from ..phase3_registry import capability_descriptors, descriptor_for
from ..services.admission import is_inference_eligible, legacy_admission
from ..services.capability_routing import CapabilityRoutingError, route_capability
from ..services.prism_preview import PrismPreviewService, install_prism_preview_routes
from ..services.prism_preview_runtime import ReviewPrismPreview
from ..services.source_mutation_gate import MutationFenced, guard_writes, writer_scope
from ..services.source_policy import source_allowed_for_model

_MANUAL = ' Manual review remains available.'


_UNKNOWN = ' The result is unknown and nothing was saved. Do not resend this image now.'


REMOTE_FAILURE_WORDING = {
    RemoteUnreachableError: (
        503,
        'The model server could not be reached, so the image was not sent.' + _MANUAL,
    ),
    RemoteTimeoutError: (504, 'The model server did not reply in time.' + _UNKNOWN + _MANUAL),
    RemoteConnectionLostError: (
        502,
        'The connection to the model server was lost before a reply.' + _UNKNOWN + _MANUAL,
    ),
    RemoteHTTPError: (
        502,
        'The model server refused or could not complete this request. Nothing was saved.' + _MANUAL,
    ),
    RemoteSchemaError: (
        502,
        "The model server's reply could not be verified, so nothing was saved." + _MANUAL,
    ),
    RemoteAuthorizationError: (
        409,
        "This image's source is not approved for sending to the model server." + _MANUAL,
    ),
    RemoteModelError: (502, 'The model server request failed. Nothing was saved.' + _MANUAL),
}


def install_inference_routes(
    app, *, inference_lock, qa_batch_profile, qa_fixed_session, workspace_authority, refresh_remote_state
):
    """Add the inference routes and return `infer`, which the daily batch also uses."""
    def infer(request, task, *, invocation_id=None, request_case_revision=None):
        if qa_fixed_session is not None:
            raise HTTPException(423, 'Fixed QA session requires the bound preview path')
        if task == 'lesion-roi' and request.model_id == 'prism-dr-5fold':
            raise HTTPException(409, 'PRISM requires a verified, one-use input preview receipt.')
        image = app.state.images.get(request.image_id)
        if image is None:
            raise HTTPException(404, 'Image not admitted to public/synthetic registry')
        admission = app.state.admissions.get(request.image_id)
        if admission is None:
            # Every registry image must pass through an explicit compatibility
            # decision before it can reach either provider path.
            with writer_scope(app.state.source_mutation_gate):
                admission = legacy_admission(image)
                app.state.admissions[request.image_id] = admission
        if not source_allowed_for_model(admission.get('source_origin', 'UNKNOWN')):
            raise HTTPException(
                409,
                'This source is available for manual review only; model analysis is not approved for its origin.',
            )
        if not is_inference_eligible(admission) and not (
            qa_batch_profile is not None and qa_batch_profile.eligible(request, image, admission)
        ):
            raise HTTPException(409, 'Image needs review or its image type is not supported for AI analysis.')
        if request.modality != admission['retinal_modality']:
            raise HTTPException(422, 'Modality does not match admitted image')
        invocation_id = invocation_id or f'legacy-{uuid4().hex}'
        if request_case_revision is None:
            request_case_revision = app.state.store.get(request.image_id)['revision']
        prior_run = next(
            (item for item in reversed(app.state.store.get(request.image_id).get('inference_history', []))
             if item.get('invocation_id') == invocation_id and item.get('task') == task),
            None,
        )
        if prior_run and isinstance(prior_run.get('result'), dict):
            if qa_batch_profile is not None:
                raise HTTPException(409, 'Batch invocation was already consumed; no new request is permitted.')
            return (GlobalResult if task == 'global' else LesionResult).model_validate(prior_run['result'])
        if request.model_id == 'mock-' + ('global' if task == 'global' else 'lesion'):
            if image.source_type != 'SYNTHETIC':
                raise HTTPException(422, 'Synthetic providers cannot infer on public images')
            if request.modality != 'CFP':
                raise HTTPException(
                    409, 'No ready model is advertised for this image type; manual review remains available.'
                )
            result = infer_mock(request, image)
            save_result(
                request,
                task,
                result,
                invocation_id=invocation_id,
                request_case_revision=request_case_revision,
            )
            return result
        remote_probe = refresh_remote_state() if app.state.remote_runtime else None
        provider = app.state.providers.get(request.model_id)
        if provider is None or provider.task != task:
            if remote_probe is not None and not remote_probe.connection_verified:
                raise HTTPException(
                    503,
                    'AI analysis is not available; manual review remains available.',
                )
            raise HTTPException(404, 'Unknown model for this task')
        if isinstance(provider, RemoteModelProvider):
            readiness = remote_probe or provider.readiness_probe()
            if not readiness.connection_verified:
                if readiness.status == 'UNAVAILABLE':
                    raise HTTPException(
                        503,
                        'AI analysis is not available; manual review remains available.',
                    )
                raise HTTPException(
                    502,
                    'The Model API capability could not be verified; manual review remains available.',
                )
            descriptor = next(
                (item for item in readiness.models if item.get('model_id') == request.model_id),
                None,
            )
            if descriptor is None:
                raise HTTPException(
                    409,
                    'The selected model is no longer advertised; manual review remains available.',
                )
        else:
            descriptor = provider.metadata()
        # Reapply committed registry restrictions before routing. A remote
        # advertisement cannot promote a frozen disabled or deferred identity.
        descriptor = next(
            (
                item for item in capability_descriptors([descriptor], include_registry=True)
                if item.get('model_id') == request.model_id
            ),
            descriptor,
        )
        try:
            route = (
                qa_batch_profile.capability(request, descriptor)
                if qa_batch_profile is not None
                else route_capability(
                    descriptor,
                    model_id=request.model_id,
                    task=task,
                    modality=request.modality,
                )
            )
        except CapabilityRoutingError as exc:
            status = str(descriptor.get('status') or '')
            if status in {'REMOTE_NOT_CONFIGURED', 'REMOTE_UNREACHABLE'}:
                raise HTTPException(503, 'AI analysis is not available; manual review remains available.') from None
            if status.startswith('REMOTE_'):
                raise HTTPException(
                    502, 'The Model API capability could not be verified; manual review remains available.'
                ) from None
            raise HTTPException(409, str(exc)) from None
        try:
            source_modality = admission['retinal_modality']
            provider_owned_uwf_preprocessing = (
                source_modality == 'UWF'
                and request.model_id in {'prism-dr-5fold', 'uspec-uwf-grading'}
            )
            analysis_image, analysis_derivative = app.state.derivatives.analysis_image(
                image,
                source_modality=source_modality,
                apply_uwf_mask=not provider_owned_uwf_preprocessing,
            )
            if qa_batch_profile is not None:
                qa_batch_profile.claim(request, image, admission)
            from ..services.regular_queue import PAIR_KEY
            # Per-call context (request thread or batch worker): pairs this image's grader and PRISM holds.
            PAIR_KEY.set(analysis_derivative.lineage.source_sha256)
            with inference_lock:
                if (
                    isinstance(provider, RemoteModelProvider)
                    and request.model_id == 'prism-dr-5fold'
                    and source_modality == 'UWF'
                ):
                    result = provider.infer_phase3_lesions(
                        request,
                        analysis_image,
                        capability_id=route.capability_id or 'core_lesion_localization',
                        model_version=str(descriptor.get('revision') or descriptor.get('model_version') or ''),
                        source_sha256=analysis_derivative.lineage.source_sha256,
                        source_origin=admission['source_origin'],
                        representation_version=analysis_derivative.audit_record()['representation_version'],
                        transform_id=analysis_derivative.lineage.transform_id,
                        request_case_revision=request_case_revision,
                        invocation_id=invocation_id,
                    )
                else:
                    result = provider.infer(request, analysis_image)
            if task == 'lesion-roi':
                result = map_lesion_result_to_review(
                    result,
                    analysis_derivative.coordinate_mapping,
                )
            def commit_batch_result():
                return save_result(
                    request, task, result, analysis_derivative,
                capability_id=route.capability_id,
                invocation_id=invocation_id,
                processing_evidence=(
                    getattr(provider, 'last_processing_evidence', None)
                    if request.model_id == 'prism-dr-5fold'
                    and request.modality == 'UWF'
                    and task == 'lesion-roi'
                    else None
                ),
                request_case_revision=request_case_revision,
                )
            if qa_batch_profile is not None:
                qa_batch_profile.commit_result(commit_batch_result)
            else:
                commit_batch_result()
            return result
        except DerivativePayloadTooLargeError:
            raise HTTPException(
                413,
                'This image is too large for the analysis service. No automatic downscaling was applied; review it manually or provide a validated representation.',
            ) from None
        except DerivativeError:
            raise HTTPException(
                409,
                'A safe analysis representation is not available for this source. Review it manually or use a supported image.',
            ) from None
        except RemoteNotConfiguredError:
            raise HTTPException(503, 'AI analysis is not available.') from None
        except RemoteModelError as exc:
            # Plain clinician wording only; the class goes to the operator log. A reply that may
            # have been processed is never described as "not sent".
            logging.getLogger(__name__).warning('Remote inference refused: %s', type(exc).__name__)
            from ..services.regular_queue import RegularQueueError
            if isinstance(exc, RegularQueueError):
                raise HTTPException(503, exc.message) from None
            status, detail = REMOTE_FAILURE_WORDING.get(type(exc), REMOTE_FAILURE_WORDING[RemoteModelError])
            raise HTTPException(status, detail) from None
        except MutationFenced:
            raise
        except (RuntimeError, ValueError, KeyError, OSError, ImportError):
            raise HTTPException(503, 'Model unavailable; inspect Models readiness and runtime configuration') from None

    @guard_writes(lambda: app.state.source_mutation_gate)
    def save_result(
        request,
        task,
        result,
        analysis_derivative=None,
        *,
        capability_id=None,
        invocation_id=None,
        request_case_revision=None,
        processing_evidence=None,
        target_store=None,
        target_provider=None,
        preview_binding=None,
    ):
        if qa_batch_profile is not None:
            qa_batch_profile.verify_result(result)
        if processing_evidence is not None:
            processing_evidence = PrismProcessingEvidence.model_validate(processing_evidence).model_dump(mode='json')
        key = 'global' if task == 'global' else 'lesion'
        store = target_store if target_store is not None else app.state.store
        with store.lock:
            case = store.get(request.image_id)
            invocation_id = invocation_id or f'legacy-{uuid4().hex}'
            history = case.setdefault('inference_history', [])
            existing = next((entry for entry in history if entry.get('invocation_id') == invocation_id), None)
            if existing is not None:
                return existing.get('status') == 'APPLIED'
            value = result.model_dump(mode='json')
            derivative_record = analysis_derivative.audit_record() if analysis_derivative else None
            derivative_changed = derivative_record is not None and case.get('analysis_derivative') != derivative_record
            processing_changed = (
                (processing_evidence is not None or preview_binding is not None)
                and case.get('prism_processing') != processing_evidence
            )
            request_case_revision = case['revision'] if request_case_revision is None else request_case_revision
            stale = case['revision'] != request_case_revision
            provider = target_provider if target_provider is not None else app.state.providers.get(request.model_id)
            source_origin = (((preview_binding or {}).get('admission') or {}).get('source_origin')
                             or (case.get('admission') or {}).get('source_origin')
                             or getattr(app.state.images.get(request.image_id), 'source_origin', 'UNKNOWN'))
            input_context = {
                'source_sha256': derivative_record['source_sha256']
                if derivative_record
                else getattr(app.state.images.get(request.image_id), 'sha256', None),
                'analysis_sha256': derivative_record['analysis_sha256']
                if derivative_record
                else getattr(app.state.images.get(request.image_id), 'sha256', None),
                'transform_id': derivative_record['transform_id'] if derivative_record else 'IDENTITY',
                'representation_version': derivative_record['representation_version']
                if derivative_record
                else 'ORIGINAL',
                'source_origin': source_origin,
                'request_case_revision': request_case_revision,
            }
            entry = {
                'invocation_id': invocation_id,
                'capability_id': capability_id or descriptor_for(request.model_id).get('capability_id'),
                'task': task,
                'model_id': request.model_id,
                'model_version': value.get('model_version'),
                'status': 'STALE_RESULT' if stale else 'APPLIED',
                'case_revision': request_case_revision,
                'source_sha256': input_context['source_sha256'],
                'analysis_sha256': input_context['analysis_sha256'],
                'transform_id': input_context['transform_id'],
                'representation_version': input_context['representation_version'],
                'result': value,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }
            if processing_evidence is not None:
                entry['prism_processing'] = deepcopy(processing_evidence)
            history.append(entry)
            if preview_binding is not None:
                entry['preview_binding'] = preview_binding
            if stale:
                case['revision'] += 1
                case.setdefault('events', []).append({
                    'action': 'INFERENCE',
                    'status': 'STALE_RESULT',
                    'invocation_id': invocation_id,
                    'model_id': request.model_id,
                    'timestamp': entry['timestamp'],
                    'request_case_revision': request_case_revision,
                    'current_case_revision': case['revision'],
                })
                store.put(case)
                return False
            if case[key] != value or derivative_changed or processing_changed:
                case[key] = value
                if derivative_record is not None:
                    case['analysis_derivative'] = derivative_record
                if processing_evidence is not None or preview_binding is not None:
                    case['prism_processing'] = processing_evidence
                case['revision'] += 1
                event = {
                    'action': 'INFERENCE',
                    'status': 'APPLIED',
                    'invocation_id': invocation_id,
                    'model_id': request.model_id,
                    'capability_id': capability_id or descriptor_for(request.model_id).get('capability_id'),
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                }
                if derivative_record is not None:
                    event.update({
                        'source_sha256': derivative_record['source_sha256'],
                        'analysis_sha256': derivative_record['analysis_sha256'],
                        'transform_id': derivative_record['transform_id'],
                    })
                if isinstance(provider, RemoteModelProvider):
                    event['runtime'] = 'remote'
                    if provider.last_inference_ms is not None:
                        event['latency_ms'] = round(provider.last_inference_ms, 1)
                case['events'].append(event)
                store.put(case)
            elif history:
                # Preserve an idempotent run even when the latest projection
                # already matches; the history entry is the authoritative run.
                store.put(case)

    def preview_route(descriptor, modality):
        if qa_batch_profile is not None:
            return qa_batch_profile.preview_capability(descriptor, modality)
        if qa_fixed_session is not None:
            return qa_fixed_session.preview_capability(descriptor, modality)
        selected = next((item for item in capability_descriptors([descriptor], include_registry=True)
                         if item.get('model_id') == 'prism-dr-5fold'), descriptor)
        try:
            return route_capability(selected, model_id='prism-dr-5fold', task='lesion-roi', modality=modality)
        except CapabilityRoutingError:
            raise HTTPException(409, 'PRISM capability is not ready for this image type.') from None

    preview_runtime = ReviewPrismPreview(
        app,
        save_result=save_result,
        source_allowed=source_allowed_for_model,
        eligible=qa_batch_profile.preview_eligible
        if qa_batch_profile is not None
        else qa_fixed_session.preview_eligible
        if qa_fixed_session
        else is_inference_eligible,
        route=preview_route,
        map_result=map_lesion_result_to_review,
        inference_lock=inference_lock,
        workspace_authority=workspace_authority,
    )
    if workspace_authority is not None:
        register_plan = preview_runtime.register_workspace_plan
    elif qa_batch_profile is not None:
        register_plan = qa_batch_profile.register_preview_plan
    elif qa_fixed_session is not None:
        register_plan = qa_fixed_session.register_preview_plan
    else:
        register_plan = None
    # Installed before the routes below capture the service.
    app.state.prism_preview = PrismPreviewService(preview_runtime.snapshot, preview_runtime.execute,
                                                refresh=preview_runtime.refresh, register_plan=register_plan)
    install_prism_preview_routes(app, app.state.prism_preview)

    @app.post('/v1/infer/global', response_model=GlobalResult)
    def global_inference(request: InferenceRequest):
        if qa_batch_profile is not None:
            # The real Review UI keeps its existing request schema. Its exact
            # manifest job supplies the durable invocation identity server-side.
            return infer(request, 'global', invocation_id=qa_batch_profile.invocation_id())
        return infer(request, 'global')

    @app.post('/v1/infer/lesion-roi', response_model=LesionResult)
    def lesion_inference(request: InferenceRequest):
        return infer(request, 'lesion-roi')

    def phase3_review_inference(request, task):
        legacy_request = InferenceRequest(
            image_id=request.image_id,
            modality=request.modality,
            model_id=request.model_id,
        )
        result = infer(
            legacy_request,
            task,
            invocation_id=request.invocation_id,
            request_case_revision=request.request_case_revision,
        )
        case = app.state.store.get(request.image_id)
        entry = next(
            (item for item in reversed(case.get('inference_history', []))
             if item.get('invocation_id') == request.invocation_id),
            None,
        )
        entry = entry or {}
        source_sha = entry.get('source_sha256') or case.get('image_sha256')
        analysis_sha = entry.get('analysis_sha256') or source_sha
        source_origin = ((case.get('admission') or {}).get('source_origin')
                         or getattr(app.state.images.get(request.image_id), 'source_origin', 'UNKNOWN'))
        context = Phase3InputContext(
            image_id=request.image_id,
            source_sha256=source_sha,
            source_origin=source_origin,
            input_modality=request.modality,
            analysis_sha256=analysis_sha,
            representation_version=entry.get('representation_version') or 'ORIGINAL',
            transform_id=entry.get('transform_id') or 'IDENTITY',
            request_case_revision=request.request_case_revision,
        )
        descriptor = descriptor_for(request.model_id)
        provider = app.state.providers.get(request.model_id)
        prism_processing = (
            PrismProcessingEvidence.model_validate(entry['prism_processing'])
            if entry.get('prism_processing') is not None else None
        )
        return Phase3ResultEnvelope(
            schema_version='bridge.v2.1' if prism_processing is not None else 'bridge.v2',
            invocation_id=request.invocation_id,
            capability_id=request.capability_id,
            task=task,
            model=Phase3ModelIdentity(
                id=request.model_id,
                version=request.model_version,
                artifact_digest=descriptor.get('artifact_digest'),
                trained_domain=descriptor.get('trained_domain', 'UNKNOWN'),
                supported_modalities=list(descriptor.get('supported_modalities') or []),
                release_status=descriptor.get('release_status', 'UNKNOWN'),
            ),
            input=context,
            result=result,
            prism_processing=prism_processing,
            explanation=Phase3Explanation(
                status='UNAVAILABLE',
                invocation_id=request.invocation_id,
                model_id=request.model_id,
                source_sha256=source_sha,
                analysis_sha256=analysis_sha,
                warning='No typed explanation evidence is available for this invocation.',
            ),
            runtime=Phase3Runtime(
                runtime_id='review',
                device='remote' if getattr(app.state, 'remote_runtime', False) else 'local',
                latency_ms=getattr(provider, 'last_inference_ms', None),
            ),
            warnings=list(result.warnings),
            status=entry.get('status', 'APPLIED'),
        )

    @app.post('/v2/infer/global', response_model=Phase3ResultEnvelope, response_model_exclude_none=True)
    def phase3_global_inference(request: Phase3ReviewInferenceRequest):
        return phase3_review_inference(request, 'global')

    @app.post('/v2/infer/lesion-roi', response_model=Phase3ResultEnvelope, response_model_exclude_none=True)
    def phase3_lesion_inference(request: Phase3ReviewInferenceRequest):
        return phase3_review_inference(request, 'lesion-roi')

    return infer
