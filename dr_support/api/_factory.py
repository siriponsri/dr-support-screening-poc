"""Review workstation FastAPI factory.

Preserved from the V2 implementation. Routes the UI, cases, review state, CVAT
integration, and the inference dispatcher (which transparently routes to local
providers or the remote proxy based on ``MODEL_RUNTIME``).
"""
import os
from pathlib import Path
from threading import RLock

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from dr_support.contracts import (
    InferenceRequest,
    GlobalResult,
    LesionResult,
    ModelConnectionInput,
    ModelConnectionResponse,
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
)
from dr_support.runtime import runtime_snapshot
from dr_support.providers.retfound import RETFound

from ..images import admitted_demo_images, admitted_samples, synthetic_image
from ..services.admission import is_inference_eligible, legacy_admission, scan_input_folder
from ..services.workspaces import WorkspaceManager
from ..services.resolver import ResolverService
from ..services.model_gateway import (
    ModelConnection,
    ModelGatewayProbe,
    probe_model_connection,
    response_payload,
)
from ..workflow import install_workflow
from .workspaces import install_workspace_routes
from .dataset import install_dataset_routes


def create_app(state_path=None, include_samples=True, include_demo_fixtures=True):
    app = FastAPI(title='DR Support Screening POC', version='0.4.0')
    root = Path(__file__).resolve().parents[2]

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
    workspace_manager = WorkspaceManager(root, state_path=state_path)
    install_workflow(app, workspace_manager.store)
    workspace_manager.attach(app)
    install_workspace_routes(app, workspace_manager)
    install_dataset_routes(app)

    def apply_scan(scan):
        """Replace workspace-discovered records while preserving manual decisions."""
        store = app.state.store
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
                app.state.admissions[image_id] = saved
                app.state.workspace_admission_ids.add(image_id)
                continue
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
        app.state.admission_warnings = list(scan.warnings)

    def scan_active_workspace():
        profile = workspace_manager.active_workspace
        if profile is None:
            app.state.admission_warnings = ['No active workspace input folder is configured.']
            return {'records': [], 'warnings': list(app.state.admission_warnings), 'scanned': False}
        scan = scan_input_folder(profile.input_folder)
        apply_scan(scan)
        return {
            'records': [app.state.admissions[image_id] for image_id in app.state.admissions
                        if image_id in scan.records],
            'warnings': list(scan.warnings),
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

    @app.get('/v1/model-connection', response_model=ModelConnectionResponse)
    def model_connection():
        connection = getattr(app.state, 'model_connection', None)
        probe = getattr(app.state, 'model_connection_probe', None)
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
        providers = {
            RemoteGlobalProvider.model_id: RemoteGlobalProvider(
                base_url=candidate.url, token=candidate.token,
            ),
            RemoteLesionProvider.model_id: RemoteLesionProvider(
                base_url=candidate.url, token=candidate.token,
            ),
        }
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
        synthetic = [
            {'model_id': name, 'task': task, 'status': 'SYNTHETIC_FIXTURE',
             'modalities': ['CFP'], 'warnings': ['Not real model inference']}
            for name, task in [('mock-global', 'global'), ('mock-lesion', 'lesion-roi')]
        ]
        remote = []
        for provider in app.state.providers.values():
            try:
                remote.append(provider.metadata())
            except Exception as exc:  # pragma: no cover - defensive guard
                # Provider.metadata() must already degrade, but belt-and-
                # suspenders so a regression never produces HTTP 500 here.
                remote.append({
                    'model_id': getattr(provider, 'model_id', 'unknown'),
                    'task': getattr(provider, 'task', 'unknown'),
                    'runtime': 'remote',
                    'status': 'REMOTE_INVALID_SCHEMA',
                    'modalities': ['CFP'],
                    'warnings': [f'Provider metadata failed: {type(exc).__name__}: {exc}'],
                })
        return synthetic + remote

    def infer(request, task):
        image = app.state.images.get(request.image_id)
        if image is None:
            raise HTTPException(404, 'Image not admitted to public/synthetic registry')
        admission = app.state.admissions.get(request.image_id)
        if admission is None:
            # Every registry image must pass through an explicit compatibility
            # decision before it can reach either provider path.
            admission = legacy_admission(image)
            app.state.admissions[request.image_id] = admission
        if not is_inference_eligible(admission):
            raise HTTPException(409, 'Image needs review before analysis.')
        if request.modality != image.modality:
            raise HTTPException(422, 'Modality does not match admitted image')
        if request.model_id == 'mock-' + ('global' if task == 'global' else 'lesion'):
            if image.source_type != 'SYNTHETIC':
                raise HTTPException(422, 'Synthetic providers cannot infer on public images')
            result = infer_mock(request, image)
            save_result(request, task, result)
            return result
        provider = app.state.providers.get(request.model_id)
        if provider is None or provider.task != task:
            raise HTTPException(404, 'Unknown model for this task')
        try:
            with inference_lock:
                result = provider.infer(request, image)
            save_result(request, task, result)
            return result
        except RemoteTimeoutError:
            raise HTTPException(504, 'Remote model timeout; inspect REMOTE_MODEL_URL and runtime latency') from None
        except RemoteNotConfiguredError:
            raise HTTPException(503, 'AI analysis is not available.') from None
        except RemoteModelError as exc:
            raise HTTPException(502, f'Remote model error: {exc}') from None
        except (RuntimeError, ValueError, KeyError, OSError, ImportError):
            raise HTTPException(503, 'Model unavailable; inspect Models readiness and runtime configuration') from None

    def save_result(request, task, result):
        key = 'global' if task == 'global' else 'lesion'
        store = app.state.store
        with store.lock:
            case = store.get(request.image_id)
            value = result.model_dump(mode='json')
            if case[key] != value:
                case[key] = value
                case['revision'] += 1
                if key == 'global':
                    case['state'] = 'PENDING'
                    case['reviewed_grade'] = None
                    case['grade_review_source'] = None
                    case['clinician_review'] = None
                event = {'action': 'INFERENCE', 'model_id': request.model_id}
                provider = app.state.providers.get(request.model_id)
                if isinstance(provider, RemoteModelProvider):
                    event['runtime'] = 'remote'
                    if provider.last_inference_ms is not None:
                        event['latency_ms'] = round(provider.last_inference_ms, 1)
                case['events'].append(event)
                store.put(case)

    @app.post('/v1/infer/global', response_model=GlobalResult)
    def global_inference(request: InferenceRequest):
        return infer(request, 'global')

    @app.post('/v1/infer/lesion-roi', response_model=LesionResult)
    def lesion_inference(request: InferenceRequest):
        return infer(request, 'lesion-roi')

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
