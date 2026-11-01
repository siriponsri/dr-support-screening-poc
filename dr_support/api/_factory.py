"""Review workstation FastAPI factory: `create_app` is the composition root.

What lives here:
- case store selection (`_build_case_store`), the owned workspace session checks and `create_app`, which
  builds the app state (images, admissions, resolver, derivatives, workspaces) and installs, in order:
  the review workflow (`workflow.install_workflow`), workspace, dataset, screening report, Gold label and
  referral routes, the workspace scan, sign-in, the model connection (`api/model_connection.py`),
  inference and PRISM preview (`api/inference.py`), the home/SPA routes and, on the regular model
  server, the daily batch (`api/batches.py`).
"""
import os
from copy import deepcopy
from functools import wraps
from pathlib import Path
from threading import RLock

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from dr_support.contracts import (
    AdmissionMetadata,
)
from dr_support.providers.prism import PRISM
from dr_support.providers.remote import (
    RemoteGlobalProvider,
    RemoteLesionProvider,
)
from dr_support.providers.retfound import RETFound

from ..images import admitted_demo_images, admitted_samples, synthetic_image
from ..imaging import (
    DerivativeService,
    IntegrityStatus,
    SourceAlias,
    SourceIntegrity,
)
from .body_limit import BodyLimitMiddleware
from ..services.admission import (
    ADMISSION_REVIEW_FIELDS,
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
)
from ..services.deployment_profile import validate_deployment_environment
from ..services.workspaces import WorkspaceManager
from ..services.resolver import ResolverService
from ..services.source_identity import record_source_identity_on_creation
from ..services.source_mutation_gate import MutationFenced, SourceMutationGate, guard_writes
from ..services.model_gateway import (
    ModelConnection,
    probe_model_connection,
)
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
from ..services.screening_report import install_screening_report_routes
from ..services.gold_labels import install_gold_label_routes
from ..services.referral_outbox import install_referral_routes
from .batches import install_regular_routes
from .inference import install_inference_routes
# Re-exported for existing imports (tests use _factory.OwnedReachability and _factory.owned_status_probe).
from .inference import REMOTE_FAILURE_WORDING  # noqa: F401
from .model_connection import OwnedReachability, owned_status_probe  # noqa: F401
from .model_connection import install_model_connection


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
            raise ValueError(
                'The owned workspace session requires an explicit QA profile, PostgreSQL workspace and migration verify'
            )
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
    install_screening_report_routes(app)
    install_gold_label_routes(app)
    install_referral_routes(app)

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
    if (
        qa_fixed_session is None
        and qa_batch_profile is None
        and (
            workspace_manager.active_workspace is not None
            or hospital_roots_configured()
            or authorized_hospital_roots()
        )
    ):
        scan_active_workspace()
    inference_lock = RLock()

    @app.middleware('http')
    async def same_origin(request, call_next):
        origin = request.headers.get('origin')
        if request.method != 'GET' and origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Cross-origin mutation rejected'}, status_code=403)
        return await call_next(request)

    auth_file = (os.environ.get('DR_SUPPORT_AUTH_FILE') or '').strip()
    if auth_file:
        # Physician UX pilot sign-in; without the variable the app is unchanged.
        from ..services.pilot_auth import install_pilot_auth
        install_pilot_auth(app, auth_file)

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

    # Model connection routes, /health, /v1/models and /v1/capabilities (api/model_connection.py).
    connection = install_model_connection(
        app, deployment=deployment, qa_fixed_session=qa_fixed_session, workspace_authority=workspace_authority,
        workspace_prism_provider=workspace_prism_provider, workspace_global_probe=workspace_global_probe,
        # Looked up here at each call, so code and tests that replace _factory.probe_model_connection
        # keep working after the split.
        probe_model_connection=lambda *args, **kwargs: probe_model_connection(*args, **kwargs),
    )

    # Inference and PRISM preview routes (api/inference.py).
    infer = install_inference_routes(
        app, inference_lock=inference_lock, qa_batch_profile=qa_batch_profile,
        qa_fixed_session=qa_fixed_session, workspace_authority=workspace_authority,
        refresh_remote_state=connection.refresh_remote_state,
    )

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
