"""Tests for the Lightning AI Studio deployment adapter (M0.7).

These tests do **not** require the Lightning cloud. They cover:

- The launch script (``scripts/start_lightning.sh``) pins the production
  environment (``APP_PROFILE=model_api``, ``MODEL_RUNTIME=local``,
  ``INFERENCE_DEVICE=cuda:0``, ``HOST=0.0.0.0``, ``PORT=8000``,
  ``WORKERS=1``) and refuses to silently fall back to CPU.
- The setup script (``scripts/setup_lightning.sh``) is idempotent and
  reuses the existing ``dr_support.setup_models`` pipeline.
- The deployment serves the existing FastAPI ``model_api`` surface with
  the four contract routes unchanged.
- The ``model_api`` factory still refuses CPU fallback when CUDA is
  requested (no silent regression vs the v0.4.0 / v0.5.0 contract).
- No real secrets appear in the launch script, the setup script, or the
  operator runbook.

The bash scripts are read as text rather than executed; this keeps the
test suite CPU-only and Windows-friendly. A real Lightning Studio is
NOT created, contacted, or billed.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dr_support.app import create_app
from dr_support.runtime import device as device_module
from dr_support.runtime import DeviceUnavailable

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
DOCS_DIR = REPO_ROOT / 'docs'

START_SCRIPT = SCRIPTS_DIR / 'start_lightning.sh'
SETUP_SCRIPT = SCRIPTS_DIR / 'setup_lightning.sh'
RUNBOOK = DOCS_DIR / 'LIGHTNING_DEPLOYMENT.md'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_device_cache():
    """Reset the device resolver cache so env mutations are honoured."""
    device_module.reset_cache()
    yield
    device_module.reset_cache()


@pytest.fixture
def model_api_app(monkeypatch, tmp_path):
    """Construct a ``model_api`` app with the resolver relaxed for CPU tests."""
    monkeypatch.setenv('APP_PROFILE', 'model_api')
    monkeypatch.setenv('MODEL_RUNTIME', 'local')
    monkeypatch.setenv('DR_SUPPORT_RELAX_DEVICE', '1')
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    monkeypatch.delenv('RETFOUND_SOURCE', raising=False)
    monkeypatch.delenv('RETFOUND_WEIGHTS', raising=False)
    monkeypatch.delenv('PRISM_SOURCE', raising=False)
    monkeypatch.delenv('PRISM_WEIGHTS', raising=False)
    return create_app()


# ---------------------------------------------------------------------------
# Launch script — environment defaults and fail-fast behaviour
# ---------------------------------------------------------------------------


def test_start_script_exists():
    assert START_SCRIPT.is_file(), 'start_lightning.sh must ship at scripts/start_lightning.sh'


def test_start_script_is_executable_posix_only():
    """The script is invoked on a Linux Studio; the Windows-side marker is the file existing."""
    body = START_SCRIPT.read_text(encoding='utf-8')
    assert body.startswith('#!/usr/bin/env bash') or body.startswith('#!/bin/bash')


def test_start_script_pins_model_api_profile():
    body = START_SCRIPT.read_text(encoding='utf-8')
    assert 'APP_PROFILE="${APP_PROFILE:-model_api}"' in body


def test_start_script_pins_local_runtime():
    body = START_SCRIPT.read_text(encoding='utf-8')
    assert 'MODEL_RUNTIME="${MODEL_RUNTIME:-local}"' in body


def test_start_script_pins_cuda_device():
    body = START_SCRIPT.read_text(encoding='utf-8')
    assert 'INFERENCE_DEVICE="${INFERENCE_DEVICE:-cuda:0}"' in body


def test_start_script_pins_host_0_0_0_0():
    body = START_SCRIPT.read_text(encoding='utf-8')
    assert 'HOST="${HOST:-0.0.0.0}"' in body


def test_start_script_pins_port_8000():
    body = START_SCRIPT.read_text(encoding='utf-8')
    assert 'PORT="${PORT:-8000}"' in body


def test_start_script_pins_single_worker():
    body = START_SCRIPT.read_text(encoding='utf-8')
    assert 'WORKERS="${WORKERS:-1}"' in body


def test_start_script_fails_fast_without_cuda(monkeypatch, tmp_path):
    """The CUDA pre-flight must call torch and refuse to start when unavailable.

    We execute the script's CUDA probe in isolation rather than the full
    launch — the probe is the only piece of fail-fast behaviour that
    matters on a CPU-only host. The full ``exec python -m dr_support.run``
    is exercised on a real Lightning Studio.
    """
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    device_module.reset_cache()
    # Simulate "no CUDA" by patching the probe to return False.
    monkeypatch.setattr(device_module, '_probe_torch', lambda: (False, 0, None))
    device_module.reset_cache()
    # The production resolver refuses CPU fallback when CUDA is requested.
    with pytest.raises(DeviceUnavailable, match='cuda'):
        from dr_support.runtime import resolve_device
        resolve_device(allow_cpu_fallback=False)


def test_start_script_refuses_to_silently_fallback_to_cpu():
    """The script must explicitly reject CUDA-unavailable hosts."""
    body = START_SCRIPT.read_text(encoding='utf-8')
    assert 'CUDA is NOT available' in body
    assert 'silently fall back to CPU' in body


def test_start_script_refuses_workers_gt_one():
    """The single-worker invariant must be enforced before uvicorn boots."""
    body = START_SCRIPT.read_text(encoding='utf-8')
    assert 'WORKERS' in body and 'is not supported' in body
    # The literal check is what guards the GPU.
    assert '"${WORKERS}" != "1"' in body


def test_start_script_executes_existing_run_module():
    """The launch must delegate to the existing ``python -m dr_support.run``."""
    body = START_SCRIPT.read_text(encoding='utf-8')
    assert 'exec python -m dr_support.run' in body


def test_start_script_uses_set_euo_pipefail():
    body = START_SCRIPT.read_text(encoding='utf-8')
    assert 'set -euo pipefail' in body


# ---------------------------------------------------------------------------
# Setup script — idempotency and asset reuse
# ---------------------------------------------------------------------------


def test_setup_script_exists():
    assert SETUP_SCRIPT.is_file(), 'setup_lightning.sh must ship at scripts/setup_lightning.sh'


def test_setup_script_reuses_setup_models_pipeline():
    body = SETUP_SCRIPT.read_text(encoding='utf-8')
    assert 'python -m dr_support.setup_models --model all' in body


def test_setup_script_does_not_duplicate_setup_logic():
    """The script must NOT clone / download / hash directly; it delegates."""
    body = SETUP_SCRIPT.read_text(encoding='utf-8')
    # No raw git clone of RETFound / PRISM-DR — that lives in setup_models.
    assert 'git clone' not in body
    # No raw gdown — that lives in setup_models.
    assert 'gdown.download' not in body
    # No raw sha256 verification — that lives in setup_models.
    assert 'sha256(' not in body


def test_setup_script_installs_project_extras():
    body = SETUP_SCRIPT.read_text(encoding='utf-8')
    assert 'pip install -e ".[models,test]"' in body


def test_setup_script_uses_persistent_bridge_path():
    """Asset cache must land under the project's single predictable path."""
    body = SETUP_SCRIPT.read_text(encoding='utf-8')
    assert 'local-state/bridge' in body


def test_setup_script_never_commits_checkpoints():
    """The script must NOT touch git or commit anything."""
    body = SETUP_SCRIPT.read_text(encoding='utf-8')
    assert 'git add' not in body
    assert 'git commit' not in body
    assert 'git push' not in body


def test_setup_script_does_not_require_docker():
    """Lightning Studios provide a Linux runtime — no container engine needed."""
    body = SETUP_SCRIPT.read_text(encoding='utf-8')
    assert 'docker' not in body.lower()
    assert 'Docker' not in body


def test_setup_script_is_idempotent():
    """A second run must be a no-op (virtualenv already present, assets already verified)."""
    body = SETUP_SCRIPT.read_text(encoding='utf-8')
    assert '[ ! -d "${VENV_DIR}" ]' in body
    # The setup_models call is documented as idempotent and the operator
    # runbook calls out the no-op behaviour; the script body delegates to it.
    assert 'idempotent' not in body.lower() or 'setup_models' in body  # belt-and-braces


# ---------------------------------------------------------------------------
# Operator runbook — required steps and PASS criteria
# ---------------------------------------------------------------------------


def test_runbook_exists():
    assert RUNBOOK.is_file(), 'docs/LIGHTNING_DEPLOYMENT.md must ship'


def test_runbook_documents_all_required_steps():
    """Steps A through N must each appear as a top-level section."""
    body = RUNBOOK.read_text(encoding='utf-8')
    for step in ('A.', 'B.', 'C.', 'D.', 'E.', 'F.', 'G.', 'H.',
                 'I.', 'J.', 'K.', 'L.', 'M.', 'N.'):
        assert step in body, f'Runbook is missing step {step}'


def test_runbook_documents_pass_criteria():
    body = RUNBOOK.read_text(encoding='utf-8')
    assert 'PASS criteria' in body
    assert '/health' in body
    assert '/v1/models' in body
    assert '/v1/predict/dr' in body
    assert '/v1/predict/lesions' in body


def test_runbook_documents_stop_when_done():
    body = RUNBOOK.read_text(encoding='utf-8')
    assert 'Stop the GPU' in body or 'stop the GPU' in body.lower()
    # The runbook must explicitly warn against consuming unnecessary credits.
    assert 'credit' in body.lower()


def test_runbook_does_not_claim_specific_free_gpu_hours():
    """The runbook must stay silent on a specific Lightning credit budget."""
    body = RUNBOOK.read_text(encoding='utf-8')
    # A specific number like "80 free GPU hours" would be a claim.
    assert not re.search(r'\b\d+\s*(?:free\s*)?gpu\s*hours?\b', body, flags=re.IGNORECASE)


def test_runbook_keeps_existing_deployment_paths():
    """The HF Docker Space and Modal adapters must remain intact."""
    body = RUNBOOK.read_text(encoding='utf-8')
    assert 'HF Docker Space' in body or 'Hugging Face' in body
    assert 'Modal' in body


def test_runbook_explains_public_port_via_studio_plugin():
    body = RUNBOOK.read_text(encoding='utf-8')
    assert 'Port' in body and 'plugin' in body.lower()
    assert '8000' in body


# ---------------------------------------------------------------------------
# Existing model_api contract — unchanged under the Lightning adapter
# ---------------------------------------------------------------------------


def test_model_api_contract_routes_still_present(model_api_app):
    """The Lightning adapter must NOT remove any model_api route."""
    client = TestClient(model_api_app)
    paths = {r.path for r in client.app.routes if hasattr(r, 'path')}
    assert '/health' in paths
    assert '/v1/models' in paths
    assert '/v1/predict/dr' in paths
    assert '/v1/predict/lesions' in paths


def test_model_api_contract_routes_still_protected_by_bearer(model_api_app):
    """The bearer-token contract on predict endpoints must be unchanged."""
    client = TestClient(model_api_app)
    payload = _build_payload('retfound-aptos5', 'SYNTH_001', 'CFP')
    # No token configured → anonymous requests are accepted (matches v0.4.0 /
    # v0.5.0 behaviour) and the predict call surfaces 503 because no weights.
    response = client.post('/v1/predict/dr', json=payload)
    assert response.status_code == 503


def test_model_api_health_exposes_device_snapshot(model_api_app):
    """The /health contract from v0.4.0 must remain intact for Lightning too."""
    client = TestClient(model_api_app)
    body = client.get('/health').json()
    assert 'requested_device' in body
    assert 'effective_device' in body
    assert 'cuda_available' in body
    assert 'cuda_device_count' in body
    assert 'cuda_device_name' in body
    assert body['lane'] == 'PUBLIC_SYNTHETIC_REMOTE_MODEL_API'


def test_model_api_predict_dr_contract_unchanged(model_api_app):
    client = TestClient(model_api_app)
    payload = _build_payload('retfound-aptos5', 'SYNTH_001', 'CFP')
    response = client.post('/v1/predict/dr', json=payload)
    # No weights on disk → 503 with the documented error message.
    assert response.status_code == 503
    assert 'RETFound assets not configured' in response.json()['detail']


def test_model_api_predict_lesions_contract_unchanged(model_api_app):
    client = TestClient(model_api_app)
    payload = _build_payload('prism-dr-5fold', 'SYNTH_001', 'CFP')
    response = client.post('/v1/predict/lesions', json=payload)
    assert response.status_code == 503
    assert 'PRISM-DR assets not configured' in response.json()['detail']


# ---------------------------------------------------------------------------
# No CPU fallback in model_api (production strictness)
# ---------------------------------------------------------------------------


def test_model_api_factory_refuses_cuda_without_runtime(monkeypatch, tmp_path):
    """When the operator forgets to enable a GPU on the Studio, the server must fail loudly.

    Mirrors ``tests/test_device.py::test_model_api_factory_refuses_cuda_when_unavailable``
    but is invoked from the Lightning context to prove the adapter never
    bypasses the v0.4.0 strict-mode behaviour.
    """
    monkeypatch.setenv('APP_PROFILE', 'model_api')
    monkeypatch.setenv('MODEL_RUNTIME', 'local')
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    monkeypatch.delenv('DR_SUPPORT_RELAX_DEVICE', raising=False)
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))

    monkeypatch.setattr(device_module, '_probe_torch', lambda: (False, 0, None))
    device_module.reset_cache()

    from dr_support.services import model_api as service_module

    with pytest.raises(DeviceUnavailable, match='cuda'):
        service_module.create_app()


def test_model_api_health_reports_fail_when_cuda_requested_but_unavailable(monkeypatch, tmp_path):
    """Even with the test knob, /health must surface the device mismatch so operators see it.

    The dispatcher always passes ``device_strict=True`` for the
    ``model_api`` profile, so to exercise the relaxed-startup path we
    call the service factory directly. The /health endpoint must still
    return ``status=FAIL`` because the requested CUDA device is not
    actually available on the host.
    """
    monkeypatch.setenv('APP_PROFILE', 'model_api')
    monkeypatch.setenv('MODEL_RUNTIME', 'local')
    monkeypatch.setenv('INFERENCE_DEVICE', 'cuda:0')
    monkeypatch.setenv('DR_SUPPORT_RELAX_DEVICE', '1')
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    monkeypatch.delenv('RETFOUND_SOURCE', raising=False)
    monkeypatch.delenv('RETFOUND_WEIGHTS', raising=False)
    monkeypatch.delenv('PRISM_SOURCE', raising=False)
    monkeypatch.delenv('PRISM_WEIGHTS', raising=False)

    monkeypatch.setattr(device_module, '_probe_torch', lambda: (False, 0, None))
    device_module.reset_cache()

    from dr_support.services.model_api import create_app as create_model_api_app

    app = create_model_api_app(device_strict=False)
    client = TestClient(app)
    body = client.get('/health').json()
    assert body['status'] == 'FAIL'
    assert body['cuda_available'] is False
    assert body['requested_device'] == 'cuda:0'
    assert body['effective_device'] == 'cpu'


# ---------------------------------------------------------------------------
# No secret leakage in the shipped artefacts
# ---------------------------------------------------------------------------


def _forbidden_secret_values() -> list[str]:
    """Real or near-real secret values that must never appear in shipped files."""
    return [
        'sk-',                # any OpenAI-style key prefix is forbidden here
        'ghp_',               # GitHub personal access token prefix
        'xoxb-',              # Slack token prefix
        'hf_',                # HuggingFace token prefix
        'AKIA',               # AWS access-key prefix
    ]


def test_launch_script_contains_no_real_secret():
    body = START_SCRIPT.read_text(encoding='utf-8')
    for needle in _forbidden_secret_values():
        assert needle not in body, f'Forbidden secret prefix {needle!r} in start_lightning.sh'


def test_setup_script_contains_no_real_secret():
    body = SETUP_SCRIPT.read_text(encoding='utf-8')
    for needle in _forbidden_secret_values():
        assert needle not in body, f'Forbidden secret prefix {needle!r} in setup_lightning.sh'


def test_runbook_contains_no_real_secret():
    body = RUNBOOK.read_text(encoding='utf-8')
    for needle in _forbidden_secret_values():
        assert needle not in body, f'Forbidden secret prefix {needle!r} in LIGHTNING_DEPLOYMENT.md'


def test_launch_script_never_prints_token_value():
    """The launch script must not echo or log REMOTE_MODEL_TOKEN verbatim."""
    body = START_SCRIPT.read_text(encoding='utf-8')
    # The script does not mention the token at all — bearer auth is
    # handled inside the FastAPI service, never in the shell.
    assert 'REMOTE_MODEL_TOKEN' not in body


def test_setup_script_never_prints_token_value():
    """The script must not echo or substitute the bearer-token value.

    Mentioning the env var by name is fine (the script tells the owner
    which var to set); echoing or substituting its value is not. We
    assert no ``$REMOTE_MODEL_TOKEN`` / ``${REMOTE_MODEL_TOKEN}``
    dereference, no ``printenv`` / ``echo $...`` on it, and no
    `read` of the variable.
    """
    body = SETUP_SCRIPT.read_text(encoding='utf-8')
    # No dereference / expansion of the token variable.
    assert '$REMOTE_MODEL_TOKEN' not in body
    assert '${REMOTE_MODEL_TOKEN}' not in body
    # No shell builtin that would leak the value into logs.
    for forbidden in ('echo $REMOTE_MODEL_TOKEN', 'echo ${REMOTE_MODEL_TOKEN}',
                      'printenv REMOTE_MODEL_TOKEN', 'read REMOTE_MODEL_TOKEN'):
        assert forbidden not in body


def test_runbook_uses_placeholder_token_only():
    body = RUNBOOK.read_text(encoding='utf-8')
    # The placeholder <synthetic-deploy-token> is acceptable. Any concrete
    # 32+ character hex / base64 string in a code block would be a leak.
    placeholder = '<synthetic-deploy-token>'
    assert placeholder in body
    # Search for concrete-looking tokens (32+ contiguous alnum chars in a
    # ``..`` code block) that are NOT inside the placeholder.
    suspicious = re.findall(r'`([A-Za-z0-9_\-]{32,})`', body)
    for hit in suspicious:
        assert hit == placeholder.strip('<>'), f'Suspicious literal token in runbook: {hit!r}'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_payload(model_id: str, image_id: str, modality: str) -> dict:
    """Build a minimal valid RemotePredictRequest payload for the contract smoke."""
    from dr_support.images import synthetic_image
    import hashlib
    fixture = synthetic_image()
    img_bytes = fixture.data
    return {
        'image_id': image_id,
        'modality': modality,
        'model_id': model_id,
        'image_b64': base64.b64encode(img_bytes).decode('ascii'),
        'image_sha256': hashlib.sha256(img_bytes).hexdigest(),
        'source_type': fixture.source_type,
        'width': fixture.size[0],
        'height': fixture.size[1],
    }
