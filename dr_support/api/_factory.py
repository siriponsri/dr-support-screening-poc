"""Review workstation FastAPI factory.

Routes the clinician UI, cases, review state, CVAT integration, and the
inference dispatcher, which routes to local providers or the remote proxy.
"""
import hmac
import logging
import os
import time
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from threading import RLock
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from dr_support.contracts import (
    AdmissionMetadata,
    InferenceRequest,
    GlobalResult,
    LesionResult,
    ModelConnectionInput,
    ModelConnectionResponse,
    Phase3Explanation,
    Phase3InputContext,
    Phase3ModelIdentity,
    Phase3ResultEnvelope,
    PrismProcessingEvidence,
    Phase3ReviewInferenceRequest,
    Phase3Runtime,
)
from dr_support.providers.mock import infer_mock
from dr_support.providers.prism import PRISM
from dr_support.providers.remote import (
    RemoteAuthorizationError,
    RemoteConnectionLostError,
    RemoteGlobalProvider,
    RemoteHTTPError,
    RemoteLesionProvider,
    RemoteModelError,
    RemoteNotConfiguredError,
    RemoteModelProvider,
    RemoteSchemaError,
    RemoteTimeoutError,
    RemoteUnreachableError,
    provider_from_descriptor,
)
from dr_support.runtime import runtime_snapshot
from dr_support.providers.retfound import RETFound

from ..images import admitted_demo_images, admitted_samples, synthetic_image
from ..imaging import (
    DerivativeError,
    DerivativePayloadTooLargeError,
    DerivativeService,
    IntegrityStatus,
    SourceAlias,
    SourceIntegrity,
    map_lesion_result_to_review,
)
from .body_limit import BodyLimitMiddleware
from ..services.admission import (
    ADMISSION_REVIEW_FIELDS,
    is_inference_eligible,
    legacy_admission,
    preserve_admission_timestamps,
    scan_authorized_hospital_roots,
    scan_input_folder,
)
from ..services.source_policy import (
    HOSPITAL_ORIGIN,
    authorized_hospital_modality,
    authorized_hospital_roots,
    hospital_roots_configured,
    hospital_ingest_enabled,
    source_allowed_for_model,
)
from ..services.capability_routing import CapabilityRoutingError, route_capability
from ..services.deployment_profile import DeploymentProfileError, validate_deployment_environment
from ..services.prism_preview import PrismPreviewService, install_prism_preview_routes
from ..services.prism_preview_runtime import ReviewPrismPreview
from ..services.workspaces import WorkspaceManager
from ..services.resolver import ResolverService
from ..services.source_identity import record_source_identity_on_creation
from ..services.source_mutation_gate import MutationFenced, SourceMutationGate, guard_writes, writer_scope
from ..services.model_gateway import (
    ModelConnection,
    ModelGatewayProbe,
    _model_summary,
    probe_model_connection,
    response_payload,
)
from ..phase3_registry import capability_descriptors, descriptor_for
from ..persistence import (
    CASE_STORE_MODE_ENV,
    DATABASE_URL_ENV,
    DEFAULT_CASE_STORE_MODE,
    WORKSPACE_ID_ENV,
    CaseConflictError,
    PostgresCaseStore,
    PostgresDatabase,
    PostgresSettings,
    PostgresWorkspaceCatalog,
    SchemaMigrator,
)
from ..workflow import install_workflow
from .workspaces import install_workspace_routes
from .dataset import install_dataset_routes


def _resolve_case_store_mode(case_store_mode: str | None, state_path) -> str:
    configured_mode = (os.environ.get(CASE_STORE_MODE_ENV) or "").strip()
    configured_dsn = (os.environ.get(DATABASE_URL_ENV) or "").strip()
    if configured_mode:
        # An explicit environment mode is the operator's compatibility choice.
        mode = configured_mode
    elif configured_dsn:
        # A managed target wins over legacy paths and function-level defaults.
        mode = "postgres"
    elif case_store_mode:
        mode = case_store_mode
    elif state_path is not None:
        # A direct function argument is an explicit legacy compatibility call.
        mode = "sqlite"
    else:
        # Environment paths are provenance/configuration only; they must not
        # silently select SQLite when the managed mode has no DSN.
        mode = DEFAULT_CASE_STORE_MODE
    mode = mode.strip().lower()
    if mode not in {"sqlite", "postgres"}:
        raise ValueError(
            f"Unknown {CASE_STORE_MODE_ENV}={mode!r}; expected 'sqlite' or 'postgres'"
        )
    return mode


def _build_case_store(case_store_mode: str, state_path, workspace_id: str | None):
    if case_store_mode == "sqlite":
        return None, None, None, None
    if state_path is not None:
        raise ValueError("state_path cannot be used with PostgreSQL case storage")
    selected_workspace_id = (workspace_id or os.environ.get(WORKSPACE_ID_ENV) or "").strip()
    migration_mode = os.environ.get("DR_SUPPORT_DATABASE_MIGRATION_MODE", "apply").strip()
    if migration_mode not in {"apply", "verify"}:
        raise ValueError("DR_SUPPORT_DATABASE_MIGRATION_MODE must be apply or verify")
    settings = PostgresSettings.from_env()
    database = PostgresDatabase(settings)
    migrator = SchemaMigrator(database)
    if migration_mode == "verify":
        migrator.verify()
    else:
        migrator.migrate()
    if not selected_workspace_id:
        profile = PostgresWorkspaceCatalog(database).latest_opened()
        selected_workspace_id = profile.id if profile is not None else "ws_bootstrap"
    store = PostgresCaseStore(database, selected_workspace_id)
    store.ensure_workspace()
    return store, selected_workspace_id, settings, database


def _workspace_composition(function):
    @wraps(function)
    def composed(*args, **kwargs):
        authority = kwargs.get('workspace_authority')
        provider = kwargs.get('workspace_prism_provider')
        if authority is None and provider is None:
            return function(*args, **kwargs)
        from ..providers.prism_workspace_remote import WorkspaceRemotePRISM
        from ..services.m1_workspace_context import WorkspaceContextReader
        from ..services.prism_workspace_authority import WorkspaceAuthority
        if (type(authority) is not WorkspaceAuthority or type(provider) is not WorkspaceRemotePRISM
                or provider.authority is not authority or type(authority.context_reader) is not WorkspaceContextReader):
            raise ValueError('An exact owned workspace authority and PRISM provider pair is required')
        reader = authority.context_reader
        # Synchronous app composition only: no request or ASGI await holds this
        # lock. Concurrent factories cannot both write before the one-use bind.
        with authority.lock, reader._bind_lock:
            if reader._app is not None or reader._gate is not None:
                raise ValueError('The workspace context reader is already bound')
            WorkspaceAuthority._ready(authority)
            return function(*args, **kwargs)
    return composed


_MANUAL = ' Manual review remains available.'
_UNKNOWN = ' The result is unknown and nothing was saved. Do not resend this image now.'
# Remote grading failures in plain words. "Not sent" is used only when no connection was made.
REMOTE_FAILURE_WORDING = {
    RemoteUnreachableError: (503, 'The model server could not be reached, so the image was not sent.' + _MANUAL),
    RemoteTimeoutError: (504, 'The model server did not reply in time.' + _UNKNOWN + _MANUAL),
    RemoteConnectionLostError: (502, 'The connection to the model server was lost before a reply.' + _UNKNOWN + _MANUAL),
    RemoteHTTPError: (502, 'The model server refused or could not complete this request. Nothing was saved.' + _MANUAL),
    RemoteSchemaError: (502, "The model server's reply could not be verified, so nothing was saved." + _MANUAL),
    RemoteAuthorizationError: (409, "This image's source is not approved for sending to the model server." + _MANUAL),
    RemoteModelError: (502, 'The model server request failed. Nothing was saved.' + _MANUAL),
}


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


class OwnedReachability:
    """Live reachability of the owned M1 model route, checked at most once per ``ttl`` seconds.

    The check (health and model list) reuses the session's backend-held token and never
    returns it, never swaps the owned provider or endpoint, never enters a writer scope and
    never loads or runs a model. Any failure, including an unexpected one, means unreachable.
    """

    def __init__(self, check, *, clock=time.monotonic, ttl=5.0):
        self.check, self.clock, self.ttl = check, clock, ttl
        self.lock = RLock()
        self.checked = None
        self.reachable = False

    def __call__(self):
        with self.lock:
            now = self.clock()
            if self.checked is not None and 0 <= now - self.checked < self.ttl:
                return self.reachable
            try:
                live = self.check()
                self.reachable = bool(live.server_reachable and live.connection_verified)
            except Exception:
                self.reachable = False
            self.checked = self.clock()
            return self.reachable


def owned_status_probe(models, reachable):
    """Status for the owned M1 session: identity fixed at start, reachability live."""
    if reachable:
        return ModelGatewayProbe(True, True, True, True, 'CONNECTED',
                                 'Connected to the model server. Each result is checked when it is saved.', models)
    return ModelGatewayProbe(False, True, False, False, 'UNAVAILABLE',
                             'The model server is not reachable right now. Manual review remains available.', models)


@_workspace_composition
def create_app(
    state_path=None,
    include_samples=True,
    include_demo_fixtures=True,
    *,
    case_store_mode: str | None = None,
    workspace_id: str | None = None,
    qa_fixed_session=None,
    qa_batch_profile=None,
    source_mutation_gate=None,
    workspace_authority=None,
    workspace_prism_provider=None,
    regular_gate=None,
):
    # Reject an invalid private boundary before creating stores or migrating DBs.
    # Availability is deliberately not checked here: review remains usable offline.
    deployment = validate_deployment_environment()
    workspace_global_probe = None
    if workspace_authority is not None:
        from ..providers.prism_workspace_remote import WorkspaceRemotePRISM
        if (qa_fixed_session is not None or qa_batch_profile is not None
                or (source_mutation_gate is not None and source_mutation_gate is not workspace_authority.gate)):
            raise ValueError('The owned workspace session requires its own writer gate and excludes isolated QA')
        if (deployment.profile not in {'QA_SERVER', 'QA_LOCAL'}
                or os.environ.get('DR_SUPPORT_DATABASE_MIGRATION_MODE') != 'verify'
                or not isinstance(workspace_id, str) or not workspace_id.strip()
                or _resolve_case_store_mode(case_store_mode, state_path) != 'postgres' or state_path is not None):
            raise ValueError('The owned workspace session requires an explicit QA profile, PostgreSQL workspace and migration verify')
        identity = WorkspaceRemotePRISM.prism_preview_identity(workspace_prism_provider)
        url = workspace_prism_provider.channel.client.base_url
        if (url.host not in {'127.0.0.1', '::1'} or url.path != '/' or url.username or url.password
                or url.query or url.fragment or str(url).rstrip('/') != deployment.model_endpoint
                or identity['descriptor'].get('ready') is not True):
            raise ValueError('The owned model channel must match the configured loopback endpoint and loaded identity')
        reader = workspace_authority.context_reader
        runtime_database = PostgresDatabase(PostgresSettings.from_env())
        reader.preflight_runtime_database(runtime_database)
        # ensure_workspace() would insert a bare row for an unknown ID; the
        # owned session only opens an existing, unarchived catalog profile.
        if PostgresWorkspaceCatalog(runtime_database).get(workspace_id.strip()) is None:
            raise ValueError('The owned session requires an existing PostgreSQL workspace profile')
        # USPEC/RETFound grading stays on the existing remote providers. One
        # authenticated discovery against the owned endpoint/token happens at
        # composition and fixes the model identity; later status GETs only recheck
        # reachability (workspace_reachable) and never change that identity.
        workspace_global_probe = probe_model_connection(
            deployment.model_endpoint, os.environ.get('REMOTE_MODEL_TOKEN') or None,
        )
        advertised = {item.get('model_id'): item for item in workspace_global_probe.models
                      if item.get('task') == 'global' and item.get('ready') is True}
        if (not workspace_global_probe.verified
                or 'UWF' not in (advertised.get('uspec-uwf-grading') or {}).get('modalities', [])
                or 'CFP' not in (advertised.get('retfound-aptos5') or {}).get('modalities', [])):
            raise ValueError('The owned session requires ready USPEC UWF and RETFound CFP grading at startup')
        workspace_authority._ready()
        source_mutation_gate = workspace_authority.gate
    if source_mutation_gate is not None:
        if (type(source_mutation_gate) is not SourceMutationGate
                or source_mutation_gate.snapshot().state != 'OPEN'):
            raise ValueError('An open source mutation gate must be explicitly injected')
        if qa_fixed_session is not None or qa_batch_profile is not None:
            raise ValueError('Source mutation gates cannot be combined with isolated QA sessions')
    if qa_batch_profile is not None:
        from batch_profile import TechnicalBatchProfile
        if type(qa_batch_profile) is not TechnicalBatchProfile or qa_fixed_session is not None:
            raise ValueError('Explicit isolated batch profile required')
    app = FastAPI(title='Retinal Review Workbench', version='0.7.0')
    # Bounded request bodies (AC-12); the review API takes no file uploads.
    app.add_middleware(BodyLimitMiddleware)
    app.state.source_mutation_gate = source_mutation_gate
    app.state.workspace_authority = workspace_authority
    app.state.regular_gate = regular_gate
    if regular_gate is not None:
        import httpx
        from ..services.regular_queue import RegularGate, RegularTransport
        if type(regular_gate) is not RegularGate or workspace_authority is None:
            raise ValueError('The regular queue requires the owned workspace session')
        # Global grading providers send through the same ticketed transport as PRISM.
        app.state.model_gateway_transport = RegularTransport(regular_gate, httpx.HTTPTransport(retries=0))
    root = Path(__file__).resolve().parents[2]

    if qa_fixed_session is not None:
        from ..services.prism_fixed_session import FixedQASession
        if not isinstance(qa_fixed_session, FixedQASession):
            raise ValueError('Explicit fixed QA session injection required')
        resolved_case_store_mode, selected_store = 'qa_injected', qa_fixed_session.store
        selected_workspace_id, postgres_database = 'fixed-qa-session', None
    else:
        resolved_case_store_mode = _resolve_case_store_mode(case_store_mode, state_path)
        selected_store, selected_workspace_id, _postgres_settings, postgres_database = _build_case_store(
            resolved_case_store_mode, state_path, workspace_id
        )
    app.state.qa_fixed_session = qa_fixed_session

    demo_folder = (os.environ.get('DR_DEMO_FOLDER') or '').strip()
    if qa_fixed_session is not None:
        app.state.images = dict(qa_fixed_session.images)
    elif demo_folder and include_demo_fixtures:
        app.state.images = admitted_demo_images(demo_folder)
    elif include_demo_fixtures:
        fixture = synthetic_image()
        app.state.images = {fixture.image_id: fixture}
        if include_samples:
            app.state.images.update(admitted_samples(root))
    else:
        app.state.images = {}
    app.state.admissions = deepcopy(qa_fixed_session.admissions) if qa_fixed_session is not None else {
        image_id: legacy_admission(image) for image_id, image in app.state.images.items()
    }
    app.state.workspace_image_ids = set()
    app.state.workspace_admission_ids = set()
    app.state.resolver = ResolverService()
    app.state.derivatives = DerivativeService()
    if selected_store is not None and source_mutation_gate is not None:
        selected_store.source_mutation_gate = source_mutation_gate
    if qa_fixed_session is not None:
        workspace_manager = WorkspaceManager.for_fixed_qa_store(root, selected_store)
    elif selected_store is None:
        workspace_manager = WorkspaceManager(root, state_path=state_path, source_mutation_gate=source_mutation_gate)
    else:
        workspace_manager = WorkspaceManager(
            root,
            store=selected_store,
            database_status="postgres",
            database_path="Managed PostgreSQL storage",
            postgres_database=postgres_database,
            source_mutation_gate=source_mutation_gate,
        )
    if source_mutation_gate is not None:
        workspace_manager.store.source_mutation_gate = source_mutation_gate
    install_workflow(app, workspace_manager.store, persist_automatic_updates=not (
        qa_batch_profile is not None and qa_batch_profile.saved_results_only
    ))
    workspace_manager.attach(app)
    app.state.case_store_mode = resolved_case_store_mode
    app.state.workspace_id = selected_workspace_id
    install_workspace_routes(app, workspace_manager)
    install_dataset_routes(app)

    @app.exception_handler(CaseConflictError)
    async def case_conflict(_request, _exc):
        return JSONResponse({"detail": "Case changed; reload"}, status_code=409)

    @app.exception_handler(MutationFenced)
    async def mutation_fenced(_request, _exc):
        return JSONResponse({"detail": (
            "Changes are paused while a model operation is being verified. "
            "Keep your unsaved work and try again later."
        )}, status_code=409)

    def previous_source_records():
        """Index persisted workspace references without changing case identity."""
        previous = {}
        with app.state.store.lock:
            # The newest version at a reference has the latest updated_at: it is
            # admitted after the older version's last admission change.
            cases = sorted(app.state.store.all_cases(), key=lambda case: (
                ((case.get('admission') or {}).get('updated_at') or ''),
                case.get('image_id') or '',
            ))
            for case in cases:
                admission = case.get('admission') or {}
                aliases = (admission.get('integrity') or {}).get('aliases') or []
                if not aliases and admission.get('source_reference'):
                    aliases = [{
                        'filename': admission.get('filename') or case.get('image_id') or 'unknown',
                        'source_reference': admission['source_reference'],
                    }]
                for alias in aliases:
                    reference = alias.get('source_reference')
                    if isinstance(reference, str) and (
                        reference.startswith('WORKSPACE_INPUT/')
                        or reference.startswith(f'{HOSPITAL_ORIGIN}/')
                    ):
                        previous[reference] = admission
        return previous

    @guard_writes(lambda: app.state.source_mutation_gate)
    def mark_missing_sources(scan):
        """Retain missing-source evidence without reintroducing deleted cases."""
        current_references = {
            alias.source_reference
            for record in scan.records.values()
            for alias in (
                SourceAlias.model_validate(item)
                for item in (record.get('integrity') or {}).get('aliases', [])
            )
        }
        warnings = []
        store = app.state.store
        with store.lock:
            for case in store.all_cases():
                admission = case.get('admission') or {}
                reference = admission.get('source_reference')
                if not isinstance(reference, str) or not (
                    reference.startswith('WORKSPACE_INPUT/')
                    or reference.startswith(f'{HOSPITAL_ORIGIN}/')
                ):
                    continue
                aliases = (admission.get('integrity') or {}).get('aliases') or [{
                    'filename': admission.get('filename') or case.get('image_id') or 'unknown',
                    'source_reference': reference,
                }]
                if any(alias.get('source_reference') in current_references for alias in aliases):
                    continue
                if admission.get('integrity_status') == IntegrityStatus.SOURCE_MISSING:
                    continue
                integrity = SourceIntegrity(
                    status=IntegrityStatus.SOURCE_MISSING,
                    aliases=[SourceAlias.model_validate(alias) for alias in aliases],
                    duplicate_content=len(aliases) > 1,
                )
                updated = dict(admission)
                updated['integrity_status'] = IntegrityStatus.SOURCE_MISSING
                updated['integrity'] = integrity
                updated = AdmissionMetadata.model_validate(updated).model_dump(mode='json')
                if updated != admission:
                    case['admission'] = updated
                    store.put(case)
                warnings.append(f"{admission.get('filename') or case.get('image_id')}: source is missing.")
        return warnings

    @guard_writes(lambda: app.state.source_mutation_gate)
    def apply_scan(scan):
        """Replace workspace-discovered records while preserving manual decisions."""
        store = app.state.store
        missing_warnings = mark_missing_sources(scan)
        for image_id in app.state.workspace_image_ids:
            app.state.images.pop(image_id, None)
        for image_id in app.state.workspace_admission_ids:
            app.state.admissions.pop(image_id, None)
        app.state.workspace_image_ids = set()
        app.state.workspace_admission_ids = set()
        for image_id, record in scan.records.items():
            case = store.get(image_id)
            saved = case.get('admission')
            if saved and saved.get('admission_method') == 'MANUAL':
                preserved = dict(saved)
                for key in (
                    'source_sha256', 'source_format', 'source_media_type', 'source_dimensions',
                    'source_metadata', 'integrity_status', 'integrity',
                ):
                    if key in record:
                        preserved[key] = record[key]
                preserved = AdmissionMetadata.model_validate(preserved).model_dump(mode='json')
                app.state.admissions[image_id] = preserved
                app.state.workspace_admission_ids.add(image_id)
                if preserved != saved:
                    case['admission'] = preserved
                    store.put(case)
                continue
            if saved and saved.get('retinal_modality_method') == 'MANUAL':
                record = {**record, **{
                    key: saved[key] for key in (
                        'retinal_modality', 'retinal_modality_state',
                        'retinal_modality_method', 'retinal_modality_candidate',
                    ) if key in saved
                }}
                record = AdmissionMetadata.model_validate(record).model_dump(mode='json')
            # Confirm Image records who reviewed the admission; a rescan never clears it.
            if saved and any(saved.get(key) is not None for key in ADMISSION_REVIEW_FIELDS):
                record = {**record, **{key: saved.get(key) for key in ADMISSION_REVIEW_FIELDS}}
                record = AdmissionMetadata.model_validate(record).model_dump(mode='json')
            # A rescan (including the one at every start) keeps the first admission time.
            record = preserve_admission_timestamps(saved, record)
            app.state.admissions[image_id] = record
            app.state.workspace_admission_ids.add(image_id)
            # Existing cases are never filled here; only a new case records it.
            record_source_identity_on_creation(case, record)
            case['admission'] = record
            history = case.setdefault('admission_history', [])
            if not history or history[-1].get('new') != {
                'modality_admission': record['modality_admission'],
                'quality_state': record['quality_state'],
            }:
                history.append({
                    'action': 'AUTOMATIC_ADMISSION',
                    'method': record['admission_method'],
                    'reason_code': record['admission_reason_code'],
                    'quality_reason_code': record.get('quality_reason_code'),
                    'new': {
                        'modality_admission': record['modality_admission'],
                        'quality_state': record['quality_state'],
                    },
                    'timestamp': record['updated_at'],
                })
            store.put(case)
        app.state.images = {
            **app.state.images,
            **scan.images,
        }
        app.state.workspace_image_ids = set(scan.images)
        app.state.admission_warnings = list(scan.warnings) + missing_warnings

    @guard_writes(lambda: app.state.source_mutation_gate)
    def scan_active_workspace():
        if qa_fixed_session is not None:
            raise HTTPException(423, 'Fixed QA session excludes scans')
        # The unified private lane has two explicit server-side roots. It does
        # not use the workspace folder or filename heuristics to assign a
        # modality, and it deliberately shares one case store/workspace.
        if hospital_roots_configured() or authorized_hospital_roots():
            scan = scan_authorized_hospital_roots(
                previous_records=previous_source_records(),
            )
            apply_scan(scan)
            return {
                'records': [app.state.admissions[image_id] for image_id in scan.records],
                'warnings': list(app.state.admission_warnings),
                'scanned': True,
            }

        profile = workspace_manager.active_workspace
        if profile is None:
            app.state.admission_warnings = ['No active workspace input folder is configured.']
            return {'records': [], 'warnings': list(app.state.admission_warnings), 'scanned': False}
        hospital_lane = hospital_ingest_enabled(profile.input_folder)
        modality = authorized_hospital_modality(profile.input_folder) if hospital_lane else None
        scan = scan_input_folder(
            profile.input_folder,
            previous_records=previous_source_records(),
            source_origin=HOSPITAL_ORIGIN if hospital_lane else 'WORKSPACE',
            retinal_modality=modality or 'UNKNOWN',
            retinal_modality_method='AUTHORIZED_SOURCE' if hospital_lane and modality else 'NONE',
        )
        apply_scan(scan)
        return {
            'records': [app.state.admissions[image_id] for image_id in scan.records],
            'warnings': list(app.state.admission_warnings),
            'scanned': True,
        }

    app.state.scan_active_workspace = scan_active_workspace
    app.state.admission_warnings = []
    if qa_fixed_session is None and qa_batch_profile is None and (workspace_manager.active_workspace is not None or hospital_roots_configured() or authorized_hospital_roots()):
        scan_active_workspace()
    inference_lock = RLock()

    @app.middleware('http')
    async def same_origin(request, call_next):
        origin = request.headers.get('origin')
        if request.method != 'GET' and origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Cross-origin mutation rejected'}, status_code=403)
        return await call_next(request)

    runtime = (os.environ.get('MODEL_RUNTIME') or 'local').strip().lower()
    if qa_fixed_session is not None:
        app.state.remote_runtime = False
        app.state.model_connection = None
        app.state.model_connection_probe = None
        app.state.providers = {'prism-dr-5fold': qa_fixed_session.provider}
    elif workspace_authority is not None:
        app.state.remote_runtime = True
        app.state.model_connection = ModelConnection(
            (os.environ.get('REMOTE_MODEL_NAME') or 'Model API').strip(), deployment.model_endpoint,
            os.environ.get('REMOTE_MODEL_TOKEN') or None,
        )
        app.state.model_connection_probe = workspace_global_probe
        # Global providers are added from the cached discovery once the
        # provider helpers below exist; PRISM is only the owned bound provider.
        app.state.providers = {'prism-dr-5fold': workspace_prism_provider}
    elif runtime == 'remote':
        app.state.remote_runtime = True
        configured_url = (os.environ.get('REMOTE_MODEL_URL') or '').strip().rstrip('/')
        configured_token = os.environ.get('REMOTE_MODEL_TOKEN') or None
        configured_name = (os.environ.get('REMOTE_MODEL_NAME') or 'Model API').strip()
        app.state.model_connection = (
            ModelConnection(configured_name, configured_url, configured_token)
            if configured_url else None
        )
        app.state.model_connection_probe = None
        app.state.providers = {
            RemoteGlobalProvider.model_id: RemoteGlobalProvider(
                base_url=configured_url, token=configured_token,
            ),
            RemoteLesionProvider.model_id: RemoteLesionProvider(
                base_url=configured_url, token=configured_token,
            ),
        }
    else:
        app.state.remote_runtime = False
        # The legacy review-API factory is invoked from the backward-compat
        # `dr_support.api:app` shim and from the `full` profile demo. In both
        # cases CPU fallback is acceptable so the V2 UI smoke test keeps
        # working on a CPU-only host; production GPU deployments use the
        # `model_api` factory in `services/model_api.py` which is strict.
        app.state.providers = {
            'retfound-aptos5': RETFound(allow_cpu_fallback=True),
            'prism-dr-5fold': PRISM(allow_cpu_fallback=True),
        }

    def remote_transport():
        """Use the shared transport hook, preserving injected providers in tests."""

        transport = getattr(app.state, 'model_gateway_transport', None)
        if transport is not None:
            return transport
        for provider in getattr(app.state, 'providers', {}).values():
            if isinstance(provider, RemoteModelProvider):
                return provider._transport
        return None

    def connection_probe(connection: ModelConnection) -> ModelGatewayProbe:
        return probe_model_connection(
            connection.url,
            connection.token,
            transport=remote_transport(),
        )

    def providers_from_probe(
        connection: ModelConnection,
        probe: ModelGatewayProbe,
        *,
        reuse_existing: bool = False,
    ):
        providers = {}
        existing = app.state.providers if reuse_existing else {}
        for advertised in probe.models:
            try:
                provider = existing.get(advertised.get('model_id'))
                if not (
                    isinstance(provider, RemoteModelProvider)
                    and provider.base_url == connection.url
                    and provider._explicit_token == connection.token
                    and provider.task == advertised.get('task')
                ):
                    provider = provider_from_descriptor(
                        advertised,
                        base_url=connection.url,
                        token=connection.token,
                        transport=remote_transport(),
                    )
            except ValueError:
                continue
            providers[provider.model_id] = provider
        return providers

    workspace_global_descriptors = ()
    if workspace_authority is not None:
        workspace_global_descriptors = tuple(
            dict(item) for item in workspace_global_probe.models
            if item.get('task') == 'global' and item.get('model_id') != 'prism-dr-5fold'
        )
        global_providers = providers_from_probe(app.state.model_connection, ModelGatewayProbe(
            *(getattr(workspace_global_probe, key) for key in (
                'server_reachable', 'api_contract_valid', 'connection_verified', 'capabilities_ready',
                'status', 'message')),
            workspace_global_descriptors, workspace_global_probe.descriptor_status,
        ))
        # providers_from_probe skips a malformed descriptor; never continue as
        # a silent PRISM-only session.
        if not {'uspec-uwf-grading', 'retfound-aptos5'} <= set(global_providers):
            raise ValueError('The owned session requires USPEC UWF and RETFound CFP grading providers')
        app.state.providers = {**global_providers, 'prism-dr-5fold': workspace_prism_provider}

    def workspace_cached_probe():
        # Read-only: never a writer scope, so status polling cannot fence or
        # race preview entry, and it still answers while entry is FENCED.
        from ..providers.prism_workspace_remote import WorkspaceRemotePRISM
        try:
            current = validate_deployment_environment()
            connection = app.state.model_connection
            if (current != deployment or app.state.workspace_authority is not workspace_authority
                    or app.state.source_mutation_gate is not workspace_authority.gate
                    or app.state.providers.get('prism-dr-5fold') is not workspace_prism_provider
                    or workspace_prism_provider.authority is not workspace_authority
                    or connection.url != deployment.model_endpoint
                    or connection.token != owned_connection_token):
                raise ValueError()
            descriptor = WorkspaceRemotePRISM.prism_preview_identity(workspace_prism_provider)['descriptor']
            # Same summary shape as ordinary discovery (the response contract
            # forbids the provider descriptor's extra identity fields).
            summary = _model_summary([descriptor], assets_verified=True)
            if not summary:
                raise ValueError()
            descriptor = summary[0]
        except (ValueError, RuntimeError, AttributeError):
            raise HTTPException(409, 'The model session changed. Stop and restart with the approved configuration.') from None
        # Model identity stays the one authenticated at session start; only reachability is
        # rechecked live, so a dropped or restored link shows truthfully.
        return owned_status_probe((*workspace_global_descriptors, descriptor), workspace_reachable())

    # Authenticated control-plane check over the owned route with the backend-held token.
    workspace_reachable = OwnedReachability(
        lambda: probe_model_connection(deployment.model_endpoint, owned_connection_token))

    owned_connection_token = app.state.model_connection.token if workspace_authority is not None else None

    def owned_connection(request: ModelConnectionInput) -> ModelConnection:
        """Allow only a display-name change of the owned session connection.

        URL or token replacement is refused before any probe or state change:
        the owned channel, authority and plans are bound to the configured
        endpoint, so a swap requires stopping and restarting the session.
        """
        try:
            candidate = ModelConnection(request.name, request.url, request.token or owned_connection_token)
        except DeploymentProfileError as exc:
            raise HTTPException(422, str(exc)) from None
        if (candidate.url != deployment.model_endpoint
                or (request.token is not None and not hmac.compare_digest(
                    request.token.encode(), (owned_connection_token or '').encode()))):
            raise HTTPException(
                409, 'The model connection is fixed for this session. Stop and restart with the approved configuration.',
            )
        return candidate

    @guard_writes(lambda: None if workspace_authority is not None else app.state.source_mutation_gate)
    def refresh_remote_state():
        if workspace_authority is not None:
            return workspace_cached_probe()
        if qa_fixed_session is not None:
            return None
        if not app.state.remote_runtime:
            return None
        connection = getattr(app.state, 'model_connection', None)
        if connection is None:
            return None
        probe = connection_probe(connection)
        app.state.model_connection_probe = probe
        providers = providers_from_probe(connection, probe, reuse_existing=True)
        if providers:
            app.state.providers = providers
        return probe

    def display_provider_metadata(provider, probe: ModelGatewayProbe | None = None):
        if not isinstance(provider, RemoteModelProvider) or probe is None:
            return provider.metadata()
        descriptor = next(
            (item for item in probe.models if item.get('model_id') == provider.model_id),
            None,
        )
        if descriptor is None:
            return {
                'model_id': provider.model_id,
                'task': provider.task,
                'runtime': 'remote',
                'remote_url': provider.base_url,
                'status': (
                    'REMOTE_MODEL_NOT_LISTED'
                    if probe.connection_verified
                    else probe.descriptor_status or probe.status
                ),
                'modalities': [],
                'ready': False,
                'warnings': [probe.message],
            }
        metadata = dict(descriptor)
        metadata['runtime'] = 'remote'
        metadata['remote_url'] = provider.base_url
        metadata['warnings'] = list(dict.fromkeys([
            *(metadata.get('warnings') or []),
            *provider._runtime_warnings(),
        ]))
        if not probe.connection_verified:
            metadata['ready'] = False
            metadata['warnings'].append(
                'Model API health is not verified; manual review remains available.'
            )
        return metadata

    @app.get('/v1/model-connection', response_model=ModelConnectionResponse)
    def model_connection():
        connection = getattr(app.state, 'model_connection', None)
        probe = refresh_remote_state() if connection is not None else None
        return response_payload(connection, probe=probe, managed_by_operator=workspace_authority is not None)

    @app.post('/v1/model-connection/test', response_model=ModelConnectionResponse)
    def test_model_connection(request: ModelConnectionInput):
        if workspace_authority is not None:
            owned_connection(request)
            return response_payload(app.state.model_connection, probe=workspace_cached_probe(), managed_by_operator=True)
        try:
            connection = ModelConnection(request.name, request.url, request.token)
        except DeploymentProfileError as exc:
            raise HTTPException(422, str(exc)) from None
        probe = connection_probe(connection)
        return response_payload(connection, probe=probe)

    @app.put('/v1/model-connection', response_model=ModelConnectionResponse)
    @guard_writes(lambda: None if workspace_authority is not None else app.state.source_mutation_gate)
    def save_model_connection(request: ModelConnectionInput):
        if workspace_authority is not None:
            with writer_scope(app.state.source_mutation_gate, invalidate=False):
                candidate = owned_connection(request)
                probe = workspace_cached_probe()
                app.state.model_connection = candidate
                return response_payload(candidate, probe=probe, managed_by_operator=True)
        previous = getattr(app.state, 'model_connection', None)
        token = request.token
        if token is None and previous is not None and previous.url == request.url:
            token = previous.token
        try:
            candidate = ModelConnection(request.name, request.url, token)
        except DeploymentProfileError as exc:
            raise HTTPException(422, str(exc)) from None
        probe = connection_probe(candidate)
        if not probe.verified:
            # Do not mutate either the active providers or the saved candidate.
            raise HTTPException(502, probe.message)
        providers = providers_from_probe(candidate, probe)
        if not providers:
            raise HTTPException(502, 'Model API advertised no supported inference capability.')
        app.state.providers = providers
        app.state.model_connection = candidate
        app.state.model_connection_probe = probe
        return response_payload(candidate, probe=probe)

    @app.get('/health')
    def health():
        snap = runtime_snapshot()
        return {
            'status': 'PASS_WITH_WARNINGS',
            'lane': (
                'PRIVATE_AUTHORIZED_RESEARCH_BRIDGE'
                if os.environ.get('DR_SUPPORT_HOSPITAL_SCOPE', '').strip() == 'PRIVATE_PROJECT_EVALUATION'
                and os.environ.get('DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL') == '1'
                else 'PUBLIC_SYNTHETIC_BRIDGE'
            ),
            'warnings': ['Research-only; model readiness is reported separately'],
            'requested_device': snap.requested_device,
            'effective_device': snap.effective_device,
            'cuda_available': snap.cuda_available,
        }

    @app.get('/v1/models')
    def models():
        # The review Worklist page depends on this endpoint returning valid
        # JSON. Each provider is wrapped in its own try/except so a single
        # failure degrades that descriptor instead of crashing the whole
        # response (which would surface as HTTP 500 + text/plain and break the
        # UI's `response.json()` call).
        probe = refresh_remote_state()
        synthetic = [
            {'model_id': name, 'task': task, 'status': 'SYNTHETIC_FIXTURE',
             'modalities': ['CFP'], 'capability_id': f'{name}-fixture',
             'revision': 'synthetic-v1', 'preprocessing': 'synthetic-v1',
             'warnings': ['Not real model inference']}
            for name, task in [('mock-global', 'global'), ('mock-lesion', 'lesion-roi')]
        ]
        remote = []
        for provider in app.state.providers.values():
            try:
                remote.append(display_provider_metadata(provider, probe))
            except Exception as exc:  # pragma: no cover - defensive guard
                # Provider.metadata() must already degrade, but belt-and-
                # suspenders so a regression never produces HTTP 500 here.
                remote.append({
                    'model_id': getattr(provider, 'model_id', 'unknown'),
                    'task': getattr(provider, 'task', 'unknown'),
                    'runtime': 'remote',
                    'status': 'REMOTE_INVALID_SCHEMA',
                    'modalities': [],
                    'warnings': [f'Provider metadata failed: {type(exc).__name__}: {exc}'],
                })
        return capability_descriptors([*synthetic, *remote], include_registry=False)

    @app.get('/v1/capabilities')
    def capabilities():
        """Return the full deterministic capability/readiness view."""

        probe = refresh_remote_state()
        return capability_descriptors([
            *(display_provider_metadata(provider, probe) for provider in app.state.providers.values())
        ])

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
        if not is_inference_eligible(admission) and not (qa_batch_profile is not None and qa_batch_profile.eligible(request, image, admission)):
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
                raise HTTPException(409, 'No ready model is advertised for this image type; manual review remains available.')
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
            route = qa_batch_profile.capability(request, descriptor) if qa_batch_profile is not None else route_capability(
                descriptor,
                model_id=request.model_id,
                task=task,
                modality=request.modality,
            )
        except CapabilityRoutingError as exc:
            status = str(descriptor.get('status') or '')
            if status in {'REMOTE_NOT_CONFIGURED', 'REMOTE_UNREACHABLE'}:
                raise HTTPException(503, 'AI analysis is not available; manual review remains available.') from None
            if status.startswith('REMOTE_'):
                raise HTTPException(502, 'The Model API capability could not be verified; manual review remains available.') from None
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
                'source_sha256': derivative_record['source_sha256'] if derivative_record else getattr(app.state.images.get(request.image_id), 'sha256', None),
                'analysis_sha256': derivative_record['analysis_sha256'] if derivative_record else getattr(app.state.images.get(request.image_id), 'sha256', None),
                'transform_id': derivative_record['transform_id'] if derivative_record else 'IDENTITY',
                'representation_version': derivative_record['representation_version'] if derivative_record else 'ORIGINAL',
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
        app, save_result=save_result, source_allowed=source_allowed_for_model,
        eligible=qa_batch_profile.preview_eligible if qa_batch_profile is not None else qa_fixed_session.preview_eligible if qa_fixed_session else is_inference_eligible,
        route=preview_route,
        map_result=map_lesion_result_to_review, inference_lock=inference_lock,
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

    @app.get('/')
    def home():
        return RedirectResponse('/app/' if (root / 'frontend/dist/index.html').exists()
                                else '/ui/index.html')

    app.mount('/ui', StaticFiles(directory=str(root / 'web')), name='ui')
    frontend_dist = root / 'frontend/dist'
    if frontend_dist.is_dir() and (frontend_dist / 'index.html').is_file():
        class SPAStaticFiles(StaticFiles):
            async def get_response(self, path, scope):
                try:
                    return await super().get_response(path, scope)
                except StarletteHTTPException as exc:
                    if exc.status_code != 404:
                        raise
                    return FileResponse(frontend_dist / 'index.html')

        app.mount('/app', SPAStaticFiles(directory=str(frontend_dist), html=True), name='app')
    else:
        @app.get('/app')
        @app.get('/app/{path:path}')
        def missing_react_app(path: str = ''):
            return JSONResponse(
                {'detail': 'React app is not built. Run `cd frontend && npm run build`.'},
                status_code=503,
            )
    app.state.infer = infer
    app.state.regular_batches = None
    if regular_gate is not None:
        install_regular_routes(app, regular_gate, infer, workspace_id)
    if qa_batch_profile is not None:
        qa_batch_profile.bind(app)
    if qa_fixed_session is not None:
        qa_fixed_session.bind(app)
        qa_fixed_session.seal()
    if workspace_authority is not None:
        # One-use bind after every store/provider/preview object exists and
        # before the app is exposed; the composition decorator holds the lock.
        workspace_authority.context_reader.bind(app, workspace_authority.gate)
    return app
