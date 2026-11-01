"""Shared AI queue status and the daily AI batch (regular model server only).

Installed by `api._factory.create_app` when a regular gate is passed in; code moved verbatim."""

import os
from pathlib import Path

from fastapi import HTTPException

from dr_support.contracts import InferenceRequest
from dr_support.providers.remote import RemoteUnreachableError

from ..services.admission import is_inference_eligible
from ..services.source_policy import source_allowed_for_model
from .inference import REMOTE_FAILURE_WORDING


def install_regular_routes(app, gate, infer, workspace_id):
    """Shared-queue status and the daily AI batch; only for the owned regular session."""
    from ..services.prism_preview import PreviewSubmitRequest
    from ..services.regular_batch import GRADER_MODELS, BatchRunner, BatchStore, PrismPrepareRefused
    from ..services.regular_queue import WORDING, RegularQueueError
    directory = (os.environ.get('DR_SUPPORT_REGULAR_BATCH_DIR') or '').strip()
    if not directory or not Path(directory).is_absolute():
        raise ValueError('The regular session requires an absolute private batch directory')

    def stage_for(image_id):
        admission = app.state.admissions.get(image_id)
        if (admission is None or not is_inference_eligible(admission)
                or not source_allowed_for_model(admission.get('source_origin', 'UNKNOWN'))):
            return None
        model_id = GRADER_MODELS.get(admission.get('retinal_modality'))
        return (model_id, admission['retinal_modality']) if model_id in app.state.providers else None

    def has_result(image_id, task):
        try:
            case = app.state.store.get(image_id)
        except Exception:
            return False
        models = set(GRADER_MODELS.values()) if task == 'global' else {'prism-dr-5fold'}
        return any(item.get('task') == task and item.get('model_id') in models and isinstance(item.get('result'), dict)
                   for item in case.get('inference_history', []))

    def run_grader(image_id, model_id, modality, invocation_id):
        infer(InferenceRequest(image_id=image_id, modality=modality, model_id=model_id), 'global',
              invocation_id=invocation_id)

    def run_prism(image_id):
        """The existing one-use receipt path: prepare for the current revision, submit exactly that receipt."""
        service = app.state.prism_preview
        revision = app.state.store.get(image_id)['revision']
        try:
            receipt = service.prepare(image_id, revision)
        except HTTPException as refusal:
            raise PrismPrepareRefused(refusal.status_code, str(refusal.detail)) from None
        service.submit(image_id, receipt['plan_id'], PreviewSubmitRequest(
            revision=revision, source_sha256=receipt['source_sha256'], wire_sha256=receipt['wire_sha256'],
            plan_sha256=receipt['plan_sha256'], mask_sha256=receipt['mask']['sha256'],
            transform_sha256=receipt['transform']['sha256'], model_version=receipt['model_version']))

    def release_image(image_id):
        image = app.state.images.get(image_id)
        if image is not None:
            gate.release(image.sha256)

    def queue_open():
        try:
            status = gate.public_status()
        except RegularQueueError:
            return False
        return bool(status['ai_open'] and status['invocations_available'] and not status['quarantined'])

    runner = BatchRunner(
        BatchStore(Path(directory) / workspace_id), workspace_id=workspace_id, stage_for=stage_for,
        has_result=has_result, run_grader=run_grader, run_prism=run_prism, queue_open=queue_open,
        release_image=release_image,
        deferred_details=set(WORDING.values()) | {
            REMOTE_FAILURE_WORDING[RemoteUnreachableError][1],
            'AI analysis is not available; manual review remains available.',
            # PRISM receipt refusals raised before the call is sent (the case changed under the receipt).
            'Case changed before preview preparation.', 'Preview is stale; prepare a new input plan.',
            'Workspace changed; prepare a new preview.', 'Preview changed before provider execution.',
            # PRISM preparation while the shared server loads or is busy; no model work started.
            'The model server did not answer in time. No model work was started; press Prepare again.',
            'PRISM is not available right now. No model work was started.'})
    app.state.regular_batches = runner

    @app.on_event('startup')
    def start_regular_batches():
        runner.start()

    @app.on_event('shutdown')
    def stop_regular_batches():
        runner.stop()

    @app.get('/v1/regular/status')
    def regular_status():
        try:
            return gate.public_status()
        except RegularQueueError as error:
            raise HTTPException(503, error.message) from None

    @app.get('/v1/batches')
    def list_batches():
        return {'batches': runner.list()}

    @app.post('/v1/batches')
    def create_batch(request: dict):
        image_ids = request.get('image_ids') if isinstance(request, dict) else None
        if request.get('all_ready') is True:
            image_ids = [image_id for image_id in app.state.admissions
                         if stage_for(image_id) is not None
                         and not (has_result(image_id, 'global') and has_result(image_id, 'lesion-roi'))]
            if not image_ids:
                raise HTTPException(409, 'No confirmed image is waiting for AI analysis.')
        try:
            return runner.create(image_ids if isinstance(image_ids, list) else [])
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @app.post('/v1/batches/{batch_id}/cancel')
    def cancel_batch(batch_id: str):
        try:
            return runner.cancel(batch_id)
        except (KeyError, OSError):
            raise HTTPException(404, 'Batch not found.') from None
