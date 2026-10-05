"""Review workstation FastAPI factory.

Routes the clinician UI, cases, review state, CVAT integration, and the
inference dispatcher, which routes to local providers or the remote proxy.
"""
import os
from datetime import datetime, timezone
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
    Phase3ReviewInferenceRequest,
    Phase3Runtime,
)
from dr_support.providers.mock import infer_mock
from dr_support.providers.prism import PRISM
from dr_support.providers.remote import (
    RemoteGlobalProvider,
    RemoteLesionProvider,
    RemoteModelError,
    RemoteNotConfiguredError,
    RemoteModelProvider,
    RemoteTimeoutError,
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
from ..services.admission import is_inference_eligible, legacy_admission, scan_input_folder
from ..services.capability_routing import CapabilityRoutingError, route_capability
from ..services.workspaces import WorkspaceManager
from ..services.resolver import ResolverService
from ..services.model_gateway import (
    ModelConnection,
    ModelGatewayProbe,
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
    settings = PostgresSettings.from_env()
    database = PostgresDatabase(settings)
    SchemaMigrator(database).migrate()
    if not selected_workspace_id:
        profile = PostgresWorkspaceCatalog(database).latest_opened()
        selected_workspace_id = profile.id if profile is not None else "ws_bootstrap"
    store = PostgresCaseStore(database, selected_workspace_id)
    store.ensure_workspace()
    return store, selected_workspace_id, settings, database


def create_app(
    state_path=None,
    include_samples=True,
    include_demo_fixtures=True,
    *,
    case_store_mode: str | None = None,
    workspace_id: str | None = None,
):
    app = FastAPI(title='Retinal Review Workbench', version='0.7.0')
    root = Path(__file__).resolve().parents[2]

    resolved_case_store_mode = _resolve_case_store_mode(case_store_mode, state_path)
    selected_store, selected_workspace_id, _postgres_settings, postgres_database = _build_case_store(
        resolved_case_store_mode, state_path, workspace_id
    )

    demo_folder = (os.environ.get('DR_DEMO_FOLDER') or '').strip()
    if demo_folder and include_demo_fixtures:
        app.state.images = admitted_demo_images(demo_folder)
    elif include_demo_fixtures:
        fixture = synthetic_image()
        app.state.images = {fixture.image_id: fixture}
        if include_samples:
            app.state.images.update(admitted_samples(root))
    else:
        app.state.images = {}
    app.state.admissions = {
        image_id: legacy_admission(image) for image_id, image in app.state.images.items()
    }
    app.state.workspace_image_ids = set()
    app.state.workspace_admission_ids = set()
    app.state.resolver = ResolverService()
    app.state.derivatives = DerivativeService()
    if selected_store is None:
        workspace_manager = WorkspaceManager(root, state_path=state_path)
    else:
        workspace_manager = WorkspaceManager(
            root,
            store=selected_store,
            database_status="postgres",
            database_path="Managed PostgreSQL storage",
            postgres_database=postgres_database,
        )
    install_workflow(app, workspace_manager.store)
    workspace_manager.attach(app)
    app.state.case_store_mode = resolved_case_store_mode
    app.state.workspace_id = selected_workspace_id
    install_workspace_routes(app, workspace_manager)
    install_dataset_routes(app)

    @app.exception_handler(CaseConflictError)
    async def case_conflict(_request, _exc):
        return JSONResponse({"detail": "Case changed; reload"}, status_code=409)

    def previous_source_records():
        """Index persisted workspace references without changing case identity."""
        previous = {}
        with app.state.store.lock:
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
                    if isinstance(reference, str) and reference.startswith('WORKSPACE_INPUT/'):
                        previous[reference] = admission
        return previous

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
                if not isinstance(reference, str) or not reference.startswith('WORKSPACE_INPUT/'):
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
            app.state.admissions[image_id] = record
            app.state.workspace_admission_ids.add(image_id)
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

    def scan_active_workspace():
        profile = workspace_manager.active_workspace
        if profile is None:
            app.state.admission_warnings = ['No active workspace input folder is configured.']
            return {'records': [], 'warnings': list(app.state.admission_warnings), 'scanned': False}
        scan = scan_input_folder(
            profile.input_folder,
            previous_records=previous_source_records(),
        )
        apply_scan(scan)
        return {
            'records': [app.state.admissions[image_id] for image_id in scan.records],
            'warnings': list(app.state.admission_warnings),
            'scanned': True,
        }

    app.state.scan_active_workspace = scan_active_workspace
    app.state.admission_warnings = []
    if workspace_manager.active_workspace is not None:
        scan_active_workspace()
    inference_lock = RLock()

    @app.middleware('http')
    async def same_origin(request, call_next):
        origin = request.headers.get('origin')
        if request.method != 'GET' and origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Cross-origin mutation rejected'}, status_code=403)
        return await call_next(request)

    runtime = (os.environ.get('MODEL_RUNTIME') or 'local').strip().lower()
    if runtime == 'remote':
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

    def connection_probe(connection: ModelConnection) -> ModelGatewayProbe:
        return probe_model_connection(
            connection.url,
            connection.token,
            transport=getattr(app.state, 'model_gateway_transport', None),
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
                ):
                    provider = provider_from_descriptor(
                        advertised,
                        base_url=connection.url,
                        token=connection.token,
                        transport=getattr(app.state, 'model_gateway_transport', None),
                    )
            except ValueError:
                continue
            providers[provider.model_id] = provider
        return providers

    def refresh_remote_state():
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
        return response_payload(connection, probe=probe)

    @app.post('/v1/model-connection/test', response_model=ModelConnectionResponse)
    def test_model_connection(request: ModelConnectionInput):
        connection = ModelConnection(request.name, request.url, request.token)
        probe = connection_probe(connection)
        return response_payload(connection, probe=probe)

    @app.put('/v1/model-connection', response_model=ModelConnectionResponse)
    def save_model_connection(request: ModelConnectionInput):
        previous = getattr(app.state, 'model_connection', None)
        token = request.token
        if token is None and previous is not None and previous.url == request.url:
            token = previous.token
        candidate = ModelConnection(request.name, request.url, token)
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
            'lane': 'PUBLIC_SYNTHETIC_BRIDGE',
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
        image = app.state.images.get(request.image_id)
        if image is None:
            raise HTTPException(404, 'Image not admitted to public/synthetic registry')
        admission = app.state.admissions.get(request.image_id)
        if admission is None:
            # Every registry image must pass through an explicit compatibility
            # decision before it can reach either provider path.
            admission = legacy_admission(image)
            app.state.admissions[request.image_id] = admission
        if admission.get('source_origin') not in {'PUBLIC', 'SYNTHETIC'}:
            raise HTTPException(
                409,
                'This source is available for manual review only; model analysis is not approved for its origin.',
            )
        if not is_inference_eligible(admission):
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
        try:
            route_capability(
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
            analysis_image, analysis_derivative = app.state.derivatives.analysis_image(
                image, source_modality=admission['retinal_modality'],
            )
            with inference_lock:
                result = provider.infer(request, analysis_image)
            if task == 'lesion-roi':
                result = map_lesion_result_to_review(
                    result,
                    analysis_derivative.coordinate_mapping,
                )
            save_result(
                request,
                task,
                result,
                analysis_derivative,
                invocation_id=invocation_id,
                request_case_revision=request_case_revision,
            )
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
        except RemoteTimeoutError:
            raise HTTPException(504, 'Remote model timeout; inspect REMOTE_MODEL_URL and runtime latency') from None
        except RemoteNotConfiguredError:
            raise HTTPException(503, 'AI analysis is not available.') from None
        except RemoteModelError as exc:
            raise HTTPException(502, f'Remote model error: {exc}') from None
        except (RuntimeError, ValueError, KeyError, OSError, ImportError):
            raise HTTPException(503, 'Model unavailable; inspect Models readiness and runtime configuration') from None

    def save_result(
        request,
        task,
        result,
        analysis_derivative=None,
        *,
        invocation_id=None,
        request_case_revision=None,
    ):
        key = 'global' if task == 'global' else 'lesion'
        store = app.state.store
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
            request_case_revision = case['revision'] if request_case_revision is None else request_case_revision
            stale = case['revision'] != request_case_revision
            provider = app.state.providers.get(request.model_id)
            source_origin = ((case.get('admission') or {}).get('source_origin')
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
                'capability_id': descriptor_for(request.model_id).get('capability_id'),
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
            history.append(entry)
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
            if case[key] != value or derivative_changed:
                case[key] = value
                if derivative_record is not None:
                    case['analysis_derivative'] = derivative_record
                case['revision'] += 1
                event = {
                    'action': 'INFERENCE',
                    'status': 'APPLIED',
                    'invocation_id': invocation_id,
                    'model_id': request.model_id,
                    'capability_id': descriptor_for(request.model_id).get('capability_id'),
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

    @app.post('/v1/infer/global', response_model=GlobalResult)
    def global_inference(request: InferenceRequest):
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
        return Phase3ResultEnvelope(
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

    @app.post('/v2/infer/global', response_model=Phase3ResultEnvelope)
    def phase3_global_inference(request: Phase3ReviewInferenceRequest):
        return phase3_review_inference(request, 'global')

    @app.post('/v2/infer/lesion-roi', response_model=Phase3ResultEnvelope)
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
    return app
