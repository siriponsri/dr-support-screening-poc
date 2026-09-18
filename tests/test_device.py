"""Tests for the runtime device resolver and provider device propagation.

These tests cover:

- The device resolver honours ``INFERENCE_DEVICE`` and refuses to silently
  fall back to CPU when a CUDA device is requested but no CUDA runtime is
  available.
- ``/health`` and ``/v1/models`` surface the requested / effective device
  along with ``cuda_available``.
- RETFound and PRISM metadata reports device information honestly, including
  a warning when the requested GPU device is unavailable.
- The ``model_api`` factory fails loudly (``DeviceUnavailable``) when CUDA is
  requested but missing, and that the contract / ``review`` profile tests are
  not affected.

Because ``torch`` is not installed on this CPU-only host, the tests patch the
resolver's internal ``_probe_torch`` function instead of attempting to
monkeypatch ``torch.cuda.is_available`` (which would fail the import path).
"""
from __future__ import annotations

import pytest

from dr_support.runtime import device as device_module
from dr_support.runtime import (
    DeviceSnapshot,
    DeviceUnavailable,
    assert_cuda_ready,
    is_cuda_requested,
    resolve_device,
    runtime_snapshot,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_device_cache():
    device_module.reset_cache()
    yield
    device_module.reset_cache()


@pytest.fixture
def fake_torch(monkeypatch):
    """Patch the resolver's internal torch probe so tests do not need torch.

    Defaults to "no CUDA". Tests override ``cuda_available`` and the device
    metadata as needed.
    """

    def _make(cuda_available: bool, count: int = 0, name: str | None = None):
        def probe():
            return cuda_available, count, name

        monkeypatch.setattr(device_module, '_probe_torch', probe)

    return _make


# ---------------------------------------------------------------------------
# Resolver unit tests
# ---------------------------------------------------------------------------


def test_is_cuda_requested_recognises_cuda_prefixes():
    assert is_cuda_requested('cuda') is True
    assert is_cuda_requested('cuda:0') is True
    assert is_cuda_requested('CUDA:0') is True
    assert is_cuda_requested('cpu') is False
    assert is_cuda_requested('') is False


def test_resolve_cpu_requested_with_cuda_available(fake_torch, monkeypatch):
    monkeypatch.setenv('INFERENCE_DEVICE', 'cpu')
    fake_torch(cuda_available=True, count=1, name='fake-t4')
    assert resolve_device() == 'cpu'
    snap = runtime_snapshot()
    assert snap.requested_device == 'cpu'
    assert snap.effective_device == 'cpu'
    assert snap.cuda_available is True


def test_resolve_cuda_requested_with_cuda_available(fake_torch, monkeypatch):
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    fake_torch(cuda_available=True, count=1, name='fake-t4')
    assert resolve_device() == 'cuda:0'
    snap = runtime_snapshot()
    assert snap.requested_device == 'cuda:0'
    assert snap.effective_device == 'cuda:0'
    assert snap.cuda_available is True


def test_resolve_cuda_requested_no_fallback_when_strict(fake_torch, monkeypatch):
    """The strict mode refuses to silently degrade to CPU."""
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    fake_torch(cuda_available=False)
    with pytest.raises(DeviceUnavailable, match='cuda'):
        resolve_device(allow_cpu_fallback=False)


def test_resolve_cuda_requested_falls_back_when_allowed(fake_torch, monkeypatch):
    """CPU development mode allows the fallback but reports the mismatch."""
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    fake_torch(cuda_available=False)
    assert resolve_device(allow_cpu_fallback=True) == 'cpu'
    snap = runtime_snapshot()
    assert snap.requested_device == 'cuda:0'
    assert snap.effective_device == 'cpu'
    assert snap.cuda_available is False


def test_resolve_rejects_unknown_device(fake_torch, monkeypatch):
    """Only ``cpu`` and ``cuda*`` are accepted; anything else is an error."""
    monkeypatch.setenv('INFERENCE_DEVICE', 'mps:0')
    fake_torch(cuda_available=False)
    with pytest.raises(DeviceUnavailable, match='cuda'):
        resolve_device(allow_cpu_fallback=False)


def test_assert_cuda_ready_passes_when_consistent(fake_torch, monkeypatch):
    monkeypatch.setenv('INFERENCE_DEVICE', 'cpu')
    fake_torch(cuda_available=False)
    snap = assert_cuda_ready()
    assert isinstance(snap, DeviceSnapshot)
    assert snap.requested_device == 'cpu'


def test_assert_cuda_ready_raises_on_mismatch(fake_torch, monkeypatch):
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    fake_torch(cuda_available=False)
    with pytest.raises(DeviceUnavailable):
        assert_cuda_ready()


# ---------------------------------------------------------------------------
# Snapshot is cached but force_refresh bypasses the cache
# ---------------------------------------------------------------------------


def test_snapshot_is_cached(fake_torch, monkeypatch):
    monkeypatch.setenv('INFERENCE_DEVICE', 'cpu')
    fake_torch(cuda_available=False)
    a = runtime_snapshot()
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    fake_torch(cuda_available=True, count=1)
    b = runtime_snapshot()  # same cache hit
    assert a is b
    c = runtime_snapshot(force_refresh=True)
    assert c is not a
    assert c.requested_device == 'cuda:0'


# ---------------------------------------------------------------------------
# Provider metadata surfaces device honestly
# ---------------------------------------------------------------------------


def test_retfound_metadata_reports_requested_and_effective_device(fake_torch, monkeypatch):
    monkeypatch.setenv('INFERENCE_DEVICE', 'cpu')
    fake_torch(cuda_available=False)
    from dr_support.providers.retfound import RETFound
    info = RETFound(allow_cpu_fallback=True).metadata()
    assert info['requested_device'] == 'cpu'
    assert info['effective_device'] == 'cpu'
    assert info['cuda_available'] is False


def test_retfound_metadata_warns_when_cuda_unavailable(fake_torch, monkeypatch):
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    fake_torch(cuda_available=False)
    from dr_support.providers.retfound import RETFound
    info = RETFound(allow_cpu_fallback=True).metadata()
    joined = ' '.join(info['warnings'])
    assert 'INFERENCE_DEVICE=cuda:0' in joined
    assert 'effective_device=cpu' in joined


def test_prism_metadata_reports_requested_and_effective_device(fake_torch, monkeypatch):
    monkeypatch.setenv('INFERENCE_DEVICE', 'cpu')
    fake_torch(cuda_available=False)
    from dr_support.providers.prism import PRISM
    info = PRISM(allow_cpu_fallback=True).metadata()
    assert info['requested_device'] == 'cpu'
    assert info['effective_device'] == 'cpu'
    assert info['cuda_available'] is False


def test_prism_metadata_warns_when_cuda_unavailable(fake_torch, monkeypatch):
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    fake_torch(cuda_available=False)
    from dr_support.providers.prism import PRISM
    info = PRISM(allow_cpu_fallback=True).metadata()
    joined = ' '.join(info['warnings'])
    assert 'INFERENCE_DEVICE=cuda:0' in joined
    assert 'effective_device=cpu' in joined


# ---------------------------------------------------------------------------
# No hidden CPU fallback in providers when strict
# ---------------------------------------------------------------------------


def test_retfound_strict_constructor_refuses_to_resolve_cuda_without_runtime(fake_torch, monkeypatch):
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    fake_torch(cuda_available=False)
    from dr_support.providers.retfound import RETFound
    provider = RETFound(allow_cpu_fallback=False)
    with pytest.raises(DeviceUnavailable, match='cuda'):
        provider._resolve_device()


def test_prism_strict_constructor_refuses_to_resolve_cuda_without_runtime(fake_torch, monkeypatch):
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    fake_torch(cuda_available=False)
    from dr_support.providers.prism import PRISM
    provider = PRISM(allow_cpu_fallback=False)
    with pytest.raises(DeviceUnavailable, match='cuda'):
        provider._resolve_device()


# ---------------------------------------------------------------------------
# PRISM inference-time CUDA cleanup is safe even when torch is unavailable
# ---------------------------------------------------------------------------


def test_prism_release_cuda_memory_is_safe_without_torch():
    from dr_support.providers.prism import PRISM
    # No torch import should be needed and the call must not raise even
    # when ``torch`` cannot be imported.
    PRISM._release_cuda_memory('cpu')  # no-op on cpu


def test_prism_release_cuda_memory_handles_missing_torch(monkeypatch):
    from dr_support.providers.prism import PRISM

    # Simulate torch being absent by removing it from the importable namespace.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == 'torch':
            raise ImportError('torch not installed')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', fake_import)
    PRISM._release_cuda_memory('cuda:0')  # must not raise


# ---------------------------------------------------------------------------
# model_api factory: strict by default, configurable for tests
# ---------------------------------------------------------------------------


@pytest.fixture
def model_api_factory(monkeypatch, tmp_path):
    """Build the model_api app with a configurable torch probe.

    The fixture patches ``_probe_torch`` at the resolver module so that the
    real ``assert_cuda_ready`` runs and reaches its own conclusion based on
    the patched host capability. This way the tests exercise the production
    code path, not a stubbed version of it.
    """
    monkeypatch.setenv('APP_PROFILE', 'model_api')
    monkeypatch.setenv('MODEL_RUNTIME', 'local')
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))

    from dr_support.services import model_api as service_module

    def _build(cuda_available: bool = True, count: int = 1, name: str | None = 'fake-t4',
               device: str = 'cuda:0', relax: bool = True):
        monkeypatch.setenv('INFERENCE_DEVICE', device)
        if relax:
            monkeypatch.setenv('DR_SUPPORT_RELAX_DEVICE', '1')
        else:
            monkeypatch.delenv('DR_SUPPORT_RELAX_DEVICE', raising=False)

        def probe():
            return cuda_available, count, name

        monkeypatch.setattr(device_module, '_probe_torch', probe)
        device_module.reset_cache()
        return service_module.create_app()

    return _build


def test_model_api_factory_refuses_cuda_when_unavailable(model_api_factory):
    """Default production behaviour: cuda requested but unavailable => loud failure."""
    with pytest.raises(DeviceUnavailable, match='cuda'):
        model_api_factory(cuda_available=False, relax=False)


def test_model_api_factory_relaxes_for_tests(model_api_factory):
    """``DR_SUPPORT_RELAX_DEVICE=1`` skips the startup assertion."""
    app = model_api_factory(cuda_available=False, relax=True)
    assert app.state.device_strict is False


def test_model_api_health_surfaces_device_snapshot(model_api_factory):
    from fastapi.testclient import TestClient
    app = model_api_factory(cuda_available=True, count=1, name='fake-t4', device='cuda:0')
    client = TestClient(app)
    body = client.get('/health').json()
    assert body['requested_device'] == 'cuda:0'
    assert body['effective_device'] == 'cuda:0'
    assert body['cuda_available'] is True
    assert body['cuda_device_count'] == 1
    assert body['cuda_device_name'] == 'fake-t4'


def test_model_api_health_fails_when_cuda_requested_but_unavailable(model_api_factory):
    from fastapi.testclient import TestClient
    app = model_api_factory(cuda_available=False, relax=True, device='cuda:0')
    client = TestClient(app)
    body = client.get('/health').json()
    assert body['status'] == 'FAIL'
    assert body['requested_device'] == 'cuda:0'
    assert body['effective_device'] == 'cpu'
    assert body['cuda_available'] is False
    assert any('cuda' in w.lower() for w in body['warnings'])


def test_model_api_v1_models_includes_device_fields(model_api_factory):
    from fastapi.testclient import TestClient
    app = model_api_factory(cuda_available=True, count=1, name='fake-t4', device='cuda:0')
    client = TestClient(app)
    descriptors = {m['model_id']: m for m in client.get('/v1/models').json()}
    for mid in ('retfound-aptos5', 'prism-dr-5fold'):
        m = descriptors[mid]
        assert m['requested_device'] == 'cuda:0'
        assert m['effective_device'] == 'cuda:0'
        assert m['cuda_available'] is True
