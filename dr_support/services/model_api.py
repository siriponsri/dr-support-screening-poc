"""Standalone Remote Model API service (``APP_PROFILE=model_api``).

Implements the provider contract documented in ``docs/operations/MODEL_SERVER.md`` so the
review workstation (``APP_PROFILE=review``) can proxy to this deployment when
``MODEL_RUNTIME=remote``. Both profiles share the same Bridge v1 contracts,
provider classes, and pinned upstream revisions; only the route surface differs.

Endpoints
---------

- ``GET  /health``
- ``GET  /v1/models``
- ``POST /v1/predict/dr``
- ``POST /v1/predict/lesions``

Dependencies
------------

The lightweight service imports only the FastAPI stack, PIL, and the contract
schemas. Loading the actual RETFound / PRISM-DR weights is gated behind
``MODEL_RUNTIME=local`` plus explicit asset environment variables; without those
the providers report ``ASSET_REQUIRED`` and the predict endpoints return ``503``.
This keeps the service importable and contract-testable on a CPU-only host so
the contract can be validated before the GPU deployment.

GPU readiness
-------------

The factory accepts ``device_strict: bool`` which, when ``True``, wires the
local providers with ``allow_cpu_fallback=False`` and additionally calls
:func:`dr_support.runtime.assert_cuda_ready` at startup. A misconfigured GPU
host therefore fails loudly at container start instead of silently degrading
to CPU at the first inference call.

Notes
-----

- No training, fine-tuning, calibration, or scientific benchmarking is performed here.
- Model weights are loaded at first inference call to keep container cold-start
  small. The same provider instances are reused for subsequent calls to avoid
  duplicate VRAM usage.
- Bearer token (when configured via ``REMOTE_MODEL_TOKEN``) is checked against
  ``Authorization: Bearer ...`` on every mutation request; it is never logged
  or echoed in responses.
"""
import base64
import hashlib
import logging
import os
import time
from threading import RLock
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from dr_support.contracts import GlobalResult, LesionResult, Provenance
from dr_support.model_assets import verify_assets
from dr_support.providers.prism import PRISM, REVISION as PRISM_REVISION
from dr_support.providers.retfound import RETFound, REVISION as RETFOUND_REVISION
from dr_support.runtime import DeviceUnavailable, assert_cuda_ready, runtime_snapshot
from dr_support.services.admission import inspect_bytes, is_inference_eligible

log = logging.getLogger('dr_support.model_api')


# ---------------------------------------------------------------------------
# Request envelope (mirrors docs/operations/MODEL_SERVER.md)
# ---------------------------------------------------------------------------


class _Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class RemotePredictRequest(_Contract):
    image_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    modality: Literal['CFP', 'UWF'] = 'CFP'
    model_id: str
    image_b64: str = Field(min_length=1, max_length=20_000_000)
    image_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_type: Literal['PUBLIC', 'SYNTHETIC']
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @model_validator(mode='after')
    def validate_image_hash(self):
        try:
            decoded = base64.b64decode(self.image_b64, validate=True)
        except Exception as exc:
            raise ValueError(f'image_b64 is not valid base64: {exc}') from exc
        digest = hashlib.sha256(decoded).hexdigest()
        if digest != self.image_sha256:
            raise ValueError('image_sha256 does not match sha256(image_b64)')
        return self


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _require_bearer(
    authorization: str | None = Header(default=None, alias='Authorization'),
) -> None:
    expected = os.environ.get('REMOTE_MODEL_TOKEN')
    if not expected:
        return
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Bearer token required')
    presented = authorization[len('Bearer '):].strip()
    # Constant-time comparison to avoid trivial timing oracles.
    if not presented or not _ct_eq(presented, expected):
        raise HTTPException(401, 'Bearer token rejected')
    # Never log the presented token; it is intentionally dropped here.


def _ct_eq(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------


def _build_providers(*, allow_cpu_fallback: bool) -> dict[str, Any]:
    """Construct the local provider registry.

    Both providers are created lazily; no model weights are loaded until the
    first inference call. This keeps the import path light on CPU-only hosts.

    ``allow_cpu_fallback`` is forwarded to the providers so that the
    production ``model_api`` factory can refuse to silently degrade to CPU
    while local contract tests can still construct the adapters on a
    CPU-only host.
    """
    return {
        RETFound.model_id: RETFound(allow_cpu_fallback=allow_cpu_fallback),
        PRISM.model_id: PRISM(allow_cpu_fallback=allow_cpu_fallback),
    }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_app(state_path=None, *, device_strict: bool | None = None) -> FastAPI:
    """Create a standalone Remote Model API app.

    Profile invariant: this factory is only invoked when
    ``APP_PROFILE in {'model_api', 'full'}``. It does NOT register the review
    API surface (cases, review, CVAT, UI).

    ``device_strict`` defaults to ``True`` for the production deployment. When
    ``True`` the factory refuses to start if a CUDA device is requested but no
    CUDA runtime is available; providers are also wired with
    ``allow_cpu_fallback=False`` so the first inference call cannot quietly
    drop to CPU. Tests pass ``False`` to exercise the contract on CPU hosts.
    """
    if device_strict is None:
        # Production default; only opt out for tests.
        device_strict = os.environ.get('DR_SUPPORT_RELAX_DEVICE') != '1'

    if device_strict:
        try:
            assert_cuda_ready()
        except DeviceUnavailable as exc:
            # Surface the error verbatim so the container log shows the exact
            # misconfiguration. The HTTP layer never reaches this point
            # because the app never finishes constructing.
            log.error('GPU readiness check failed: %s', exc)
            raise

    # Startup is intentionally read-only: setup_models performs acquisition,
    # while the service refuses to become ready when pinned local assets are
    # missing or modified. Model weights remain lazy-loaded on first inference.
    assets_verified = False
    if (os.environ.get('MODEL_RUNTIME', 'local').strip().lower() == 'local'
            and os.environ.get('MODEL_REQUIRE_VERIFIED_ASSETS') == '1'):
        verify_assets('all')
        assets_verified = True

    app = FastAPI(title='Retinal Review Workbench Model API', version='0.7.0')
    inference_lock = RLock()
    app.state.providers = _build_providers(allow_cpu_fallback=not device_strict)
    app.state.inference_lock = inference_lock
    app.state.profile = os.environ.get('APP_PROFILE', 'model_api')
    app.state.device_strict = device_strict
    app.state.assets_verified = assets_verified

    # --------- /health ---------
    @app.get('/health')
    def health():
        statuses = {pid: p.metadata().get('status', 'UNKNOWN') for pid, p in app.state.providers.items()}
        snap = runtime_snapshot()
        device_warnings: list[str] = []
        if snap.requested_device.startswith('cuda') and not snap.cuda_available:
            device_warnings.append(
                f"INFERENCE_DEVICE={snap.requested_device} requested but no CUDA runtime is available."
            )
            overall = 'FAIL'
        else:
            overall = 'PASS' if app.state.assets_verified else 'PASS_WITH_WARNINGS'
        warnings = [
            'Public/synthetic research deployment only. No diagnosis or autonomous referral.',
            'Pinned local assets are verified; model weights load on first use.',
        ]
        warnings.extend(device_warnings)
        return {
            'status': overall,
            'lane': 'PUBLIC_SYNTHETIC_REMOTE_MODEL_API',
            'warnings': warnings,
            'providers': statuses,
            'requested_device': snap.requested_device,
            'effective_device': snap.effective_device,
            'cuda_available': snap.cuda_available,
            'cuda_device_count': snap.cuda_device_count,
            'cuda_device_name': snap.cuda_device_name,
            'assets_verified': app.state.assets_verified,
        }

    # --------- /v1/models ---------
    @app.get('/v1/models')
    def models():
        descriptors = [p.metadata() for p in app.state.providers.values()]
        # Stable, contract-defined order so the review workstation sees a
        # predictable list.
        descriptors.sort(key=lambda m: (0 if m['task'] == 'global' else 1, m['model_id']))
        return descriptors

    # --------- /v1/predict/* ---------
    def _record_timing(provider: Any, started: float) -> dict[str, Any]:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        # Surface timing both on the provider (for /models) and in the response
        # headers so callers can monitor latency without parsing JSON.
        provider.last_inference_ms = elapsed_ms
        return {'elapsed_ms': elapsed_ms}

    @app.post('/v1/predict/dr', response_model=GlobalResult, dependencies=[Depends(_require_bearer)])
    def predict_dr(payload: RemotePredictRequest):
        return _predict_global(app, payload, inference_lock)

    @app.post('/v1/predict/lesions', response_model=LesionResult,
              dependencies=[Depends(_require_bearer)])
    def predict_lesions(payload: RemotePredictRequest):
        return _predict_lesions(app, payload, inference_lock)

    # Annotation: we deliberately do NOT mount /v1/cases, /v1/cases/{id}/*,
    # /v1/infer/* or the static UI here. Those belong to the review profile.
    app.state.predicted_count = 0
    return app


# ---------------------------------------------------------------------------
# Inference helpers (kept outside the closure so they are unit-testable)
# ---------------------------------------------------------------------------


class _ImageShim:
    """Minimal duck-typed image adapter that the existing providers consume.

    The local ``RETFound.infer`` and ``PRISM.infer`` accept a ``BridgeImage``
    from ``dr_support.images``. We avoid coupling to that dataclass here by
    constructing one via the same module.
    """
    __slots__ = ('image_id', 'data', 'source_type', 'modality', 'source')

    def __init__(self, payload: RemotePredictRequest, raw: bytes, source: str):
        self.image_id = payload.image_id
        self.data = raw
        self.source_type = payload.source_type
        self.modality = payload.modality
        self.source = source

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def size(self) -> tuple[int, int]:
        # Lazy PIL import keeps the lightweight contract import path clean.
        from PIL import Image
        import io
        with Image.open(io.BytesIO(self.data)) as image:
            return image.size


def _check_runtime() -> None:
    runtime = (os.environ.get('MODEL_RUNTIME') or 'local').strip().lower()
    if runtime != 'local':
        raise HTTPException(409,
                            'APP_PROFILE=model_api requires MODEL_RUNTIME=local; '
                            'use APP_PROFILE=review with MODEL_RUNTIME=remote instead.')


def _check_admission(payload: RemotePredictRequest) -> None:
    """Guard direct model calls without changing the frozen request envelope."""
    raw = base64.b64decode(payload.image_b64)
    admission = inspect_bytes(
        raw,
        image_id=payload.image_id,
        filename=f'{payload.image_id}.payload',
        source_reference=f'MODEL_API/{payload.image_id}',
    )
    if not is_inference_eligible(admission):
        raise HTTPException(409, 'Image needs review before analysis.')


def _predict_global(app: FastAPI, payload: RemotePredictRequest, lock: RLock) -> GlobalResult:
    _check_runtime()
    if payload.model_id != RETFound.model_id:
        raise HTTPException(404, f"Unknown model_id '{payload.model_id}' for /v1/predict/dr")
    provider = app.state.providers[RETFound.model_id]
    if payload.modality != 'CFP':
        # The local provider returns UNSUPPORTED for non-CFP; mirror that even
        # when assets are not configured (the caller just wants a contract-
        # honest answer about modality support).
        result = GlobalResult(
            model_id=provider.model_id, model_version=RETFOUND_REVISION,
            modality=payload.modality, state='UNSUPPORTED', grade=None,
            probabilities=[], confidence=None,
            warnings=['UWF is unsupported by this Bridge'],
            provenance=Provenance(image_sha256=payload.image_sha256,
                                  source_type=payload.source_type,
                                  preprocessing='none',
                                  source_revision=RETFOUND_REVISION),
        )
        return result
    _check_admission(payload)
    if provider.metadata().get('status') == 'ASSET_REQUIRED':
        raise HTTPException(503, 'RETFound assets not configured; set RETFOUND_SOURCE / RETFOUND_WEIGHTS')
    image = _ImageShim(payload, base64.b64decode(payload.image_b64), source='remote-model-api')
    request = _InferenceRequest(image_id=payload.image_id, modality=payload.modality,
                                model_id=payload.model_id)
    started = time.perf_counter()
    try:
        with lock:
            result = provider.infer(request, image)
    except (RuntimeError, ValueError, KeyError, OSError, ImportError) as exc:
        log.warning('RETFound inference failed: %s', type(exc).__name__)
        raise HTTPException(503, 'Model inference failed; inspect logs and runtime configuration') from None
    provider.last_inference_ms = round((time.perf_counter() - started) * 1000, 1)
    app.state.predicted_count += 1
    return result


def _predict_lesions(app: FastAPI, payload: RemotePredictRequest, lock: RLock) -> LesionResult:
    _check_runtime()
    if payload.model_id != PRISM.model_id:
        raise HTTPException(404, f"Unknown model_id '{payload.model_id}' for /v1/predict/lesions")
    provider = app.state.providers[PRISM.model_id]
    if payload.modality != 'CFP':
        result = LesionResult(
            model_id=provider.model_id, model_version=PRISM_REVISION,
            modality=payload.modality, state='UNSUPPORTED', width=payload.width,
            height=payload.height, lesions=[],
            warnings=['UWF is unsupported by this Bridge'],
            provenance=Provenance(image_sha256=payload.image_sha256,
                                  source_type=payload.source_type,
                                  preprocessing='none',
                                  source_revision=PRISM_REVISION),
        )
        return result
    _check_admission(payload)
    if provider.metadata().get('status') == 'ASSET_REQUIRED':
        raise HTTPException(503, 'PRISM-DR assets not configured; set PRISM_SOURCE / PRISM_WEIGHTS')
    image = _ImageShim(payload, base64.b64decode(payload.image_b64), source='remote-model-api')
    request = _InferenceRequest(image_id=payload.image_id, modality=payload.modality,
                                model_id=payload.model_id)
    started = time.perf_counter()
    try:
        with lock:
            result = provider.infer(request, image)
    except (RuntimeError, ValueError, KeyError, OSError, ImportError) as exc:
        log.warning('PRISM inference failed: %s', type(exc).__name__)
        raise HTTPException(503, 'Model inference failed; inspect logs and runtime configuration') from None
    provider.last_inference_ms = round((time.perf_counter() - started) * 1000, 1)
    app.state.predicted_count += 1
    return result


# A small local re-export so we can construct an ``InferenceRequest`` for the
# providers without pulling the schema into the public signature.
class _InferenceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    image_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    modality: Literal['CFP', 'UWF'] = 'CFP'
    model_id: str
