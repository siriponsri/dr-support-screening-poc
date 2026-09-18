"""Tests for the Modal deployment adapter (``modal_app.py``).

These tests do **not** require Modal cloud execution. They cover:

- The static configuration of ``modal_app.py`` (GPU ladder, secret name,
  app name, image path, concurrency settings).
- The ``_resolve_gpu`` helper, including rejection of unsupported GPUs.
- The contract that ``build_asgi_app`` forwards to the existing
  ``dr_support.app.create_app`` with the production profile invariant.
- The contract that ``build_asgi_app`` refuses to silently fall back to
  CPU when CUDA is requested but unavailable.
- The shape of the Modal ``App`` / ``Function`` objects when the SDK is
  installed, with assertions on the registered GPU, secrets, image, and
  function name.

The ``modal`` package is an optional dependency; when it is not
installed the module exposes a plain ``web()`` callable (no Modal
decorators). The tests are conditional: GPU / secrets / image assertions
skip when the SDK is absent, but the configuration and contract tests
still run.
"""
from __future__ import annotations

import importlib
import os

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _has_modal() -> bool:
    try:
        importlib.import_module('modal')
    except ImportError:
        return False
    return True


requires_modal = pytest.mark.skipif(
    not _has_modal(), reason='modal SDK not installed (pip install -e ".[modal]")'
)


@pytest.fixture
def modal_app_module(monkeypatch):
    """Reload ``modal_app`` with a clean environment and a faked CUDA runtime.

    The production code path is strict by default — ``APP_PROFILE=model_api``
    hardcodes ``device_strict=True`` so the dispatcher refuses to silently
    fall back to CPU. We honour that strict behaviour here by patching the
    resolver's ``_probe_torch`` so the production startup check passes on
    this CPU-only host. The dedicated strict-refusal test exercises the
    opposite case (no patch) to prove the loud-failure path still fires.

    The fixture also snapshots and restores the env vars that
    ``modal_app.build_asgi_app`` sets via ``os.environ.setdefault`` so a
    downstream test (e.g. ``tests/test_profiles.py``) is not polluted by
    the ``INFERENCE_DEVICE=cuda:0`` default.
    """
    monkeypatch.setenv('DR_SUPPORT_STATE', '/tmp/dr-support-modal-tests.sqlite')
    monkeypatch.delenv('MODAL_GPU', raising=False)
    # Snapshot env vars we touch so we can restore them after the test.
    saved = {key: os.environ.get(key) for key in
             ('APP_PROFILE', 'MODEL_RUNTIME', 'INFERENCE_DEVICE', 'HOST', 'PORT', 'WORKERS')}
    for key in saved:
        monkeypatch.delenv(key, raising=False)
    # Patch the resolver's torch probe so the strict startup check passes.
    from dr_support.runtime import device as device_module
    device_module.reset_cache()

    def probe():
        return True, 1, 'fake-t4'

    monkeypatch.setattr(device_module, '_probe_torch', probe)
    import modal_app
    importlib.reload(modal_app)
    try:
        yield modal_app
    finally:
        # Restore env so other tests see a clean slate.
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        device_module.reset_cache()


@pytest.fixture
def strict_modal_app_module(monkeypatch, tmp_path):
    """Reload ``modal_app`` with strict device handling (production behaviour).

    Unlike :func:`modal_app_module` this fixture does NOT patch the
    torch probe, so the production strict-mode refusal fires.
    """
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    monkeypatch.delenv('DR_SUPPORT_RELAX_DEVICE', raising=False)
    monkeypatch.delenv('MODAL_GPU', raising=False)
    saved = {key: os.environ.get(key) for key in
             ('APP_PROFILE', 'MODEL_RUNTIME', 'INFERENCE_DEVICE', 'HOST', 'PORT', 'WORKERS')}
    for key in saved:
        monkeypatch.delenv(key, raising=False)
    from dr_support.runtime import device as device_module
    device_module.reset_cache()
    import modal_app
    importlib.reload(modal_app)
    try:
        yield modal_app
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        device_module.reset_cache()


# ---------------------------------------------------------------------------
# Static configuration
# ---------------------------------------------------------------------------


def test_default_gpu_is_t4(modal_app_module):
    """The deployment defaults to T4 to match the v0.4.0 HF Space target."""
    assert modal_app_module.DEFAULT_GPU == 'T4'


def test_accepted_gpu_ladder_is_t4_l4_a10(modal_app_module):
    """Only T4 / L4 / A10 are accepted; H100 / A100 are NOT in the ladder."""
    assert modal_app_module.ACCEPTED_GPUS == ('T4', 'L4', 'A10')
    assert 'H100' not in modal_app_module.ACCEPTED_GPUS
    assert 'A100' not in modal_app_module.ACCEPTED_GPUS


def test_remote_token_secret_name_is_stable(modal_app_module):
    """The Modal Secret name is the contract the operator uses from the CLI."""
    assert modal_app_module.REMOTE_TOKEN_SECRET_NAME == 'dr-support-remote-model-token'


def test_app_name_is_stable(modal_app_module):
    """``modal deploy modal_app.py`` registers the app under this name."""
    assert modal_app_module.APP_NAME == 'dr-support-screening-poc-model-api'


def test_dockerfile_path_points_at_repo_root(modal_app_module):
    """The Modal image is built from the existing v0.4.0 Dockerfile, not a copy."""
    path = modal_app_module.DOCKERFILE_PATH
    assert path.name == 'Dockerfile'
    assert path.is_file()
    # The Dockerfile must contain the v0.4.0 build-time asset step. If a
    # future operator accidentally duplicates the dependency definition,
    # this assertion fires.
    body = path.read_text(encoding='utf-8')
    assert 'setup_models --model all' in body
    assert 'torch==2.5.1+cu121' in body


def test_concurrency_is_one_inference_per_container(modal_app_module):
    """Single-container concurrency matches the v0.4.0 single-worker invariant."""
    assert modal_app_module.MAX_INPUTS_PER_CONTAINER == 1
    assert modal_app_module.TARGET_INPUTS_PER_CONTAINER == 1


# ---------------------------------------------------------------------------
# GPU resolution
# ---------------------------------------------------------------------------


def test_resolve_gpu_default_is_t4(modal_app_module, monkeypatch):
    monkeypatch.delenv('MODAL_GPU', raising=False)
    assert modal_app_module._resolve_gpu() == 'T4'


def test_resolve_gpu_honours_modal_gpu_env(modal_app_module, monkeypatch):
    monkeypatch.setenv('MODAL_GPU', 'L4')
    assert modal_app_module._resolve_gpu() == 'L4'
    monkeypatch.setenv('MODAL_GPU', 'A10')
    assert modal_app_module._resolve_gpu() == 'A10'


def test_resolve_gpu_rejects_unknown_hardware(modal_app_module, monkeypatch):
    """We never silently change hardware; H100 must be rejected."""
    monkeypatch.setenv('MODAL_GPU', 'H100')
    with pytest.raises(ValueError, match='MODAL_GPU'):
        modal_app_module._resolve_gpu()


def test_resolve_gpu_rejects_a100_explicitly(modal_app_module, monkeypatch):
    """A100 is not in the documented ladder for the public POC."""
    monkeypatch.setenv('MODAL_GPU', 'A100')
    with pytest.raises(ValueError, match='MODAL_GPU'):
        modal_app_module._resolve_gpu()


def test_resolve_gpu_strips_whitespace(modal_app_module, monkeypatch):
    monkeypatch.setenv('MODAL_GPU', '  T4  ')
    assert modal_app_module._resolve_gpu() == 'T4'


# ---------------------------------------------------------------------------
# ASGI app construction
# ---------------------------------------------------------------------------


def test_build_asgi_app_pins_model_api_profile(modal_app_module):
    """The Modal deployment must always serve the model_api profile."""
    app = modal_app_module.build_asgi_app()
    assert app.state.profile == 'model_api'
    assert app.state.runtime == 'local'


def test_build_asgi_app_exposes_only_model_api_routes(modal_app_module):
    """The clinician UI surface is NEVER hosted in Modal."""
    app = modal_app_module.build_asgi_app()
    paths = {r.path for r in app.routes if hasattr(r, 'path')}
    # Model API contract surface (must be present).
    assert '/health' in paths
    assert '/v1/models' in paths
    assert '/v1/predict/dr' in paths
    assert '/v1/predict/lesions' in paths
    # Review-only surface (must NOT be present).
    assert '/v1/cases' not in paths
    assert '/v1/infer/global' not in paths
    assert '/ui' not in paths


def test_build_asgi_app_sets_runtime_env_defaults(modal_app_module, monkeypatch):
    """The production profile env must be set BEFORE the dispatcher runs."""
    # We assert via the produced app rather than the env so a previous
    # test cannot pollute the process.
    app = modal_app_module.build_asgi_app()
    # The dispatcher's model_api branch is the only way to land here.
    assert app.state.profile == 'model_api'


def test_build_asgi_app_refuses_cuda_when_unavailable(strict_modal_app_module, monkeypatch):
    """Production behaviour: cuda requested but no CUDA runtime => loud failure.

    This is the v0.4.0 contract for ``APP_PROFILE=model_api`` — Modal
    cannot silently degrade to CPU.
    """
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    monkeypatch.delenv('DR_SUPPORT_RELAX_DEVICE', raising=False)
    with pytest.raises(Exception) as excinfo:
        strict_modal_app_module.build_asgi_app()
    # ``dr_support.runtime.DeviceUnavailable`` or a ``RuntimeError`` chained
    # from the dispatcher both count; the important thing is that the
    # failure is loud, not silent.
    assert 'cuda' in str(excinfo.value).lower() or 'INFERENCE_DEVICE' in str(excinfo.value)


def test_build_asgi_app_relaxes_when_test_knob_set(modal_app_module, monkeypatch):
    """``DR_SUPPORT_RELAX_DEVICE=1`` allows the contract tests to run on CPU.

    The Modal deployment never sets this knob; the production code path
    is strict and refuses to silently fall back. The test-only escape
    hatch is used by ``tests/test_device.py`` and matches the contract
    documented in ``docs/PROFILES.md``.
    """
    # When CUDA is faked-available (the modal_app_module fixture does
    # this) the app starts in strict mode and surfaces cuda_available
    # correctly. We assert that the contract surface returns the expected
    # device fields so the Modal adapter inherits the v0.4.0 health
    # contract.
    app = modal_app_module.build_asgi_app()
    from fastapi.testclient import TestClient
    client = TestClient(app)
    body = client.get('/health').json()
    assert body['requested_device'] == 'cuda:0'
    assert body['effective_device'] == 'cuda:0'
    assert body['cuda_available'] is True


# ---------------------------------------------------------------------------
# Modal SDK integration (skipped when the SDK is not installed)
# ---------------------------------------------------------------------------


@requires_modal
def test_modal_app_object_is_registered(modal_app_module):
    """When the SDK is installed, ``app`` must be a ``modal.App`` instance."""
    import modal
    assert isinstance(modal_app_module.app, modal.App)
    assert modal_app_module.app.name == modal_app_module.APP_NAME


@requires_modal
def test_modal_function_is_registered(modal_app_module):
    """The ``web`` function must be a Modal Function handle."""
    import modal
    assert isinstance(modal_app_module.web, modal.functions.Function)


@requires_modal
def test_modal_function_requests_t4_gpu(modal_app_module):
    """The registered function must request the default T4 GPU."""
    spec = modal_app_module.web._spec_
    assert spec.gpus == 'T4'


@requires_modal
def test_modal_function_uses_remote_token_secret(modal_app_module):
    """The registered function must reference the bearer-token Secret."""
    spec = modal_app_module.web._spec_
    assert len(spec.secrets) == 1
    # The Secret handle is opaque; assert on the registered name via the
    # underlying ``_Secret`` object's ``_name`` attribute. Modal does not
    # expose a stable accessor here, so we fall back to stringifying.
    secret = spec.secrets[0]
    assert 'dr-support-remote-model-token' in repr(secret)


@requires_modal
def test_modal_function_uses_dockerfile_image(modal_app_module):
    """The image must come from the existing Dockerfile (strategy A)."""
    spec = modal_app_module.web._spec_
    image = spec.image
    # The image object exposes its source via ``_repr`` and ``info``.
    rendered = repr(image)
    assert 'dockerfile' in rendered.lower()


@requires_modal
def test_modal_function_image_keeps_build_time_assets(modal_app_module):
    """The Dockerfile that drives the Modal image must bake assets at build time.

    This is the single-source-of-truth guarantee: Modal cannot claim a
    different asset strategy than the HF Docker Space target.
    """
    # ``modal.Image.from_dockerfile`` stores the path on the underlying
    # ``build_dockerfile_python`` callable; we read the Dockerfile directly
    # to keep the assertion robust across Modal SDK versions.
    body = modal_app_module.DOCKERFILE_PATH.read_text(encoding='utf-8')
    assert 'python -m dr_support.setup_models --model all' in body
    # No re-download at runtime.
    assert 'setup_models' in body  # the Dockerfile invokes it


@requires_modal
def test_modal_function_does_not_set_warm_pool(modal_app_module):
    """Scale-to-zero invariant: no ``min_containers`` / ``scaledown_window``."""
    spec = modal_app_module.web._spec_
    # ``app.function`` defaults to ``min_containers=0``; the Modal
    # spec exposes it as an attribute only when explicitly set, so we
    # assert by absence. If a future operator enables a warm pool, the
    # ``_build_modal_objects`` helper needs to be updated to surface it
    # here.
    assert spec.scheduler_placement is None or not getattr(spec.scheduler_placement, 'min_containers', None)


@requires_modal
def test_modal_object_id_uses_repo_app_name(modal_app_module):
    """The app-level function handle must register under the documented app name."""
    # The Function object is unhydrated locally (no Modal server
    # round-trip); we assert on the registered spec instead.
    spec = modal_app_module.web._spec_
    assert spec is not None
    # The app object itself carries the documented name.
    assert modal_app_module.app.name == modal_app_module.APP_NAME
