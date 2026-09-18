"""Provider-neutral API. Run with python -m uvicorn dr_support.api:app."""
import os
from pathlib import Path
from threading import RLock
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from .store import Store
from .workflow import install_workflow
from .images import admitted_samples
from dr_support.contracts import InferenceRequest, GlobalResult, LesionResult
from dr_support.providers.mock import infer_mock
from .images import synthetic_image
from dr_support.providers.retfound import RETFound
from dr_support.providers.prism import PRISM
from dr_support.providers.remote import (
    RemoteModelProvider,
    RemoteGlobalProvider,
    RemoteLesionProvider,
    RemoteModelError,
    RemoteTimeoutError,
)


def create_app(state_path=None, include_samples=True):
    app = FastAPI(title='DR Support Screening POC', version='1.0')
    fixture = synthetic_image()
    root = Path(__file__).resolve().parents[1]
    app.state.images = {fixture.image_id: fixture}
    if include_samples:
        app.state.images.update(admitted_samples(root))
    store = Store(state_path or (os.environ.get('DR_SUPPORT_STATE') or str(root / 'local-state/bridge/reviews.sqlite')))
    install_workflow(app, store)
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
        # REMOTE_MODEL_URL is required; REMOTE_MODEL_TOKEN is optional and read at request time.
        if not os.environ.get('REMOTE_MODEL_URL'):
            raise RuntimeError('REMOTE_MODEL_URL must be set when MODEL_RUNTIME=remote')
        app.state.providers = {
            RemoteGlobalProvider.model_id: RemoteGlobalProvider(),
            RemoteLesionProvider.model_id: RemoteLesionProvider(),
        }
    else:
        app.state.remote_runtime = False
        app.state.providers = {"retfound-aptos5": RETFound(), "prism-dr-5fold": PRISM()}

    @app.get('/health')
    def health():
        return {'status': 'PASS_WITH_WARNINGS', 'lane': 'PUBLIC_SYNTHETIC_BRIDGE',
                'warnings': ['Research-only; model readiness is reported separately']}

    @app.get('/v1/models')
    def models():
        return [{'model_id': name, 'task': task, 'status': 'SYNTHETIC_FIXTURE',
                 'modalities': ['CFP'], 'warnings': ['Not real model inference']}
                for name, task in [('mock-global', 'global'), ('mock-lesion', 'lesion-roi')]] + [
                    p.metadata() for p in app.state.providers.values()]

    def infer(request, task):
        image = app.state.images.get(request.image_id)
        if image is None:
            raise HTTPException(404, 'Image not admitted to public/synthetic registry')
        if request.modality != image.modality:
            raise HTTPException(422, 'Modality does not match admitted image')
        if request.model_id == 'mock-' + ('global' if task == 'global' else 'lesion'):
            if image.source_type != "SYNTHETIC":
                raise HTTPException(422, "Synthetic providers cannot infer on public images")
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
        except RemoteModelError as exc:
            raise HTTPException(502, f'Remote model error: {exc}') from None
        except (RuntimeError, ValueError, KeyError, OSError, ImportError):
            raise HTTPException(503, 'Model unavailable; inspect Models readiness and runtime configuration') from None

    def save_result(request, task, result):
        key = 'global' if task == 'global' else 'lesion'
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

    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import RedirectResponse

    @app.get("/")
    def home():
        return RedirectResponse("/ui/index.html")

    app.mount("/ui", StaticFiles(directory=str(root / "web")), name="ui")
    app.state.infer = infer
    return app


app = create_app()
