"""Tests for the multi-runtime-profile architecture (review / model_api / full).

These tests do not download model weights and do not require a GPU. They cover:

- Profile dispatch (``dr_support.app.create_app``)
- Profile / runtime invariants (rejection of incompatible combinations)
- The standalone ``model_api`` surface (contract routes without real inference)
- Bearer-token enforcement on the model_api mutation endpoints
- M4-style integration: a remote review profile can proxy to a local model_api profile
  using the existing ``RemoteModelProvider`` adapter.
"""
import base64
import hashlib
import io

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from dr_support.app import create_app
from dr_support.images import synthetic_image


# ---------------------------------------------------------------------------
# Profile dispatch
# ---------------------------------------------------------------------------


def test_review_profile_is_default_and_routes_cases(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_PROFILE', 'review')
    monkeypatch.setenv('MODEL_RUNTIME', 'remote')
    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    app = create_app()
    assert app.state.profile == 'review'
    assert app.state.runtime == 'remote'
    # Review routes must be present.
    paths = _collect_paths(app)
    assert '/v1/cases' in paths
    assert '/v1/infer/global' in paths
    assert '/ui' in paths or '/ui/index.html' in paths  # static mount or route
    # The standalone model_api routes must NOT be present in review profile.
    assert '/v1/predict/dr' not in paths
    assert '/v1/predict/lesions' not in paths


def test_model_api_profile_registers_only_model_routes(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_PROFILE', 'model_api')
    monkeypatch.setenv('MODEL_RUNTIME', 'local')
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    app = create_app()
    assert app.state.profile == 'model_api'
    assert app.state.runtime == 'local'
    paths = _collect_paths(app)
    assert '/health' in paths
    assert '/v1/models' in paths
    assert '/v1/predict/dr' in paths
    assert '/v1/predict/lesions' in paths
    # Review-only routes must NOT be mounted.
    assert '/v1/cases' not in paths
    assert '/v1/infer/global' not in paths
    assert '/v1/infer/lesion-roi' not in paths
    assert '/ui' not in paths


def test_full_profile_exposes_both_surfaces(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_PROFILE', 'full')
    monkeypatch.setenv('MODEL_RUNTIME', 'local')
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    app = create_app()
    assert app.state.profile == 'full'
    paths = _collect_paths(app)
    assert '/v1/cases' in paths
    assert '/v1/predict/dr' in paths
    assert '/v1/predict/lesions' in paths


def test_unknown_profile_rejected(monkeypatch):
    monkeypatch.setenv('APP_PROFILE', 'nonsense')
    with pytest.raises(ValueError, match='APP_PROFILE'):
        create_app()


# ---------------------------------------------------------------------------
# Profile / runtime invariants
# ---------------------------------------------------------------------------


def test_review_profile_rejects_local_runtime(monkeypatch):
    monkeypatch.setenv('APP_PROFILE', 'review')
    monkeypatch.setenv('MODEL_RUNTIME', 'local')
    monkeypatch.delenv('REMOTE_MODEL_URL', raising=False)
    with pytest.raises(RuntimeError, match='MODEL_RUNTIME=remote'):
        create_app()


def test_review_profile_requires_remote_url(monkeypatch):
    monkeypatch.setenv('APP_PROFILE', 'review')
    monkeypatch.setenv('MODEL_RUNTIME', 'remote')
    monkeypatch.delenv('REMOTE_MODEL_URL', raising=False)
    with pytest.raises(RuntimeError, match='REMOTE_MODEL_URL'):
        create_app()


def test_model_api_profile_rejects_remote_runtime(monkeypatch):
    monkeypatch.setenv('APP_PROFILE', 'model_api')
    monkeypatch.setenv('MODEL_RUNTIME', 'remote')
    with pytest.raises(RuntimeError, match='MODEL_RUNTIME=local'):
        create_app()


def test_full_profile_rejects_remote_runtime(monkeypatch):
    monkeypatch.setenv('APP_PROFILE', 'full')
    monkeypatch.setenv('MODEL_RUNTIME', 'remote')
    with pytest.raises(RuntimeError, match='MODEL_RUNTIME=local'):
        create_app()


# ---------------------------------------------------------------------------
# model_api surface (without real weights)
# ---------------------------------------------------------------------------


@pytest.fixture
def model_api_app(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_PROFILE', 'model_api')
    monkeypatch.setenv('MODEL_RUNTIME', 'local')
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    # No model weights on disk; providers report ASSET_REQUIRED.
    monkeypatch.delenv('RETFOUND_SOURCE', raising=False)
    monkeypatch.delenv('RETFOUND_WEIGHTS', raising=False)
    monkeypatch.delenv('PRISM_SOURCE', raising=False)
    monkeypatch.delenv('PRISM_WEIGHTS', raising=False)
    return create_app()


def test_model_api_health_reports_provider_statuses(model_api_app):
    client = TestClient(model_api_app)
    response = client.get('/health')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] in {'PASS', 'PASS_WITH_WARNINGS'}
    assert body['lane'] == 'PUBLIC_SYNTHETIC_REMOTE_MODEL_API'
    statuses = body['providers']
    assert statuses['retfound-aptos5'] == 'ASSET_REQUIRED'
    assert statuses['prism-dr-5fold'] == 'ASSET_REQUIRED'


def test_model_api_v1_models_advertises_assets_required(model_api_app):
    client = TestClient(model_api_app)
    response = client.get('/v1/models')
    assert response.status_code == 200
    descriptors = {m['model_id']: m for m in response.json()}
    assert descriptors['retfound-aptos5']['task'] == 'global'
    assert descriptors['retfound-aptos5']['status'] == 'ASSET_REQUIRED'
    assert descriptors['prism-dr-5fold']['task'] == 'lesion-roi'
    assert descriptors['prism-dr-5fold']['status'] == 'ASSET_REQUIRED'


def test_model_api_predict_dr_returns_503_when_assets_missing(model_api_app):
    client = TestClient(model_api_app)
    payload = _build_payload('retfound-aptos5', '01_dr', 'CFP', width=3504, height=2336)
    response = client.post('/v1/predict/dr', json=payload)
    assert response.status_code == 503
    assert 'RETFound assets not configured' in response.json()['detail']


def test_model_api_predict_lesions_returns_503_when_assets_missing(model_api_app):
    client = TestClient(model_api_app)
    payload = _build_payload('prism-dr-5fold', '01_dr', 'CFP', width=3504, height=2336)
    response = client.post('/v1/predict/lesions', json=payload)
    assert response.status_code == 503
    assert 'PRISM-DR assets not configured' in response.json()['detail']


def test_model_api_predict_dr_rejects_unknown_model_id(model_api_app):
    client = TestClient(model_api_app)
    payload = _build_payload('not-a-model', '01_dr', 'CFP')
    response = client.post('/v1/predict/dr', json=payload)
    assert response.status_code == 404


def test_model_api_predict_dr_rejects_non_cfp_modality(model_api_app):
    client = TestClient(model_api_app)
    payload = _build_payload('retfound-aptos5', '01_dr', 'UWF')
    response = client.post('/v1/predict/dr', json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body['state'] == 'UNSUPPORTED'
    assert body['grade'] is None
    assert any('UWF' in w for w in body['warnings'])


@pytest.mark.parametrize('path,model_id', [
    ('/v1/predict/dr', 'retfound-aptos5'),
    ('/v1/predict/lesions', 'prism-dr-5fold'),
])
def test_model_api_predict_routes_enforce_admission(path, model_id, model_api_app):
    client = TestClient(model_api_app)
    image = Image.new('RGB', (400, 300), '#777777')
    output = io.BytesIO()
    image.save(output, format='PNG')
    raw = output.getvalue()
    payload = _build_payload(model_id, 'ambiguous', 'CFP', width=400, height=300)
    payload['image_b64'] = base64.b64encode(raw).decode('ascii')
    payload['image_sha256'] = hashlib.sha256(raw).hexdigest()

    response = client.post(path, json=payload)

    assert response.status_code == 409
    assert response.json()['detail'] == 'Image needs review before analysis.'


def test_model_api_envelope_validates_image_sha256(model_api_app):
    client = TestClient(model_api_app)
    payload = _build_payload('retfound-aptos5', '01_dr', 'CFP', mutate_hash=True)
    response = client.post('/v1/predict/dr', json=payload)
    # Pydantic validation errors surface as 422.
    assert response.status_code == 422


def test_model_api_envelope_rejects_invalid_base64(model_api_app):
    client = TestClient(model_api_app)
    payload = _build_payload('retfound-aptos5', '01_dr', 'CFP', mutate_b64=True)
    response = client.post('/v1/predict/dr', json=payload)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Bearer-token enforcement
# ---------------------------------------------------------------------------


def test_model_api_predict_requires_bearer_when_token_set(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_PROFILE', 'model_api')
    monkeypatch.setenv('MODEL_RUNTIME', 'local')
    monkeypatch.setenv('REMOTE_MODEL_TOKEN', 'synthetic-deploy-token')
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    app = create_app()
    client = TestClient(app)
    payload = _build_payload('retfound-aptos5', '01_dr', 'CFP')
    # Missing Authorization header should be 401.
    response = client.post('/v1/predict/dr', json=payload)
    assert response.status_code == 401
    # Wrong token rejected.
    response = client.post('/v1/predict/dr', json=payload,
                           headers={'Authorization': 'Bearer wrong-token'})
    assert response.status_code == 401
    # Correct token accepted (predict call returns 503 because weights are not
    # configured; that's fine for this assertion — we just want auth to pass).
    response = client.post('/v1/predict/dr', json=payload,
                           headers={'Authorization': 'Bearer synthetic-deploy-token'})
    assert response.status_code == 503
    assert 'Bearer token' not in response.text
    assert 'synthetic-deploy-token' not in response.text


def test_model_api_health_is_unauthenticated(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_PROFILE', 'model_api')
    monkeypatch.setenv('MODEL_RUNTIME', 'local')
    monkeypatch.setenv('REMOTE_MODEL_TOKEN', 'synthetic-deploy-token')
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    app = create_app()
    client = TestClient(app)
    # /health must work without auth so the HF liveness probe is never gated.
    response = client.get('/health')
    assert response.status_code == 200
    assert 'synthetic-deploy-token' not in response.text


# ---------------------------------------------------------------------------
# M4: review profile can proxy to a local model_api profile
# ---------------------------------------------------------------------------


def test_review_profile_proxies_to_local_model_api(monkeypatch, tmp_path):
    """A genuine end-to-end smoke for the M4 integration."""
    # Configure the model_api profile first (local), so we can grab its
    # ASGI transport and inject it as the remote backend for the review profile.
    monkeypatch.setenv('APP_PROFILE', 'model_api')
    monkeypatch.setenv('MODEL_RUNTIME', 'local')
    monkeypatch.delenv('REMOTE_MODEL_TOKEN', raising=False)
    model_api_client = TestClient(create_app(), base_url='https://remote.test')

    calls = []

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return model_api_client.build_request(request.method, request.url.path,
                                              headers=request.headers,
                                              content=request.content).send()

    monkeypatch.setenv('APP_PROFILE', 'review')
    monkeypatch.setenv('MODEL_RUNTIME', 'remote')
    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    review_app = create_app()
    # Inject the transport into the RemoteGlobalProvider and RemoteLesionProvider
    # so they hit our model_api_client instead of real network.
    from dr_support.providers.remote import RemoteModelProvider
    for provider in review_app.state.providers.values():
        if isinstance(provider, RemoteModelProvider):
            provider._transport = httpx.MockTransport(transport)

    review_client = TestClient(review_app)
    fixture = synthetic_image()
    review_app.state.images[fixture.image_id] = fixture
    # Review app forwards the predict call to the model_api app. Because the
    # model_api app has no weights, the call surfaces 503 to the review app,
    # which the remote adapter maps to a 502 to the UI. Either way, the call
    # must reach the model_api and the auth envelope must round-trip.
    response = review_client.post('/v1/infer/global',
                                  json={'image_id': fixture.image_id,
                                        'model_id': 'retfound-aptos5',
                                        'modality': 'CFP'})
    assert response.status_code in (502, 503)
    assert any(call.url.path == '/v1/predict/dr' for call in calls)
    # Ensure the review surface still works (worklist) on the merged app.
    cases = review_client.get('/v1/cases').json()
    assert any(c['image_id'] == fixture.image_id for c in cases)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_paths(app) -> set[str]:
    """Return every routed path including mounted sub-apps."""
    paths: set[str] = set()
    for route in app.routes:
        path = getattr(route, 'path', None)
        if path:
            paths.add(path)
        # StaticFiles is mounted under a sub-app; expose the mount prefix too.
        routes = getattr(route, 'routes', None)
        if routes:
            for sub in routes:
                sub_path = getattr(sub, 'path', None)
                if sub_path:
                    paths.add(sub_path)
    return paths


def _build_payload(model_id: str, image_id: str, modality: str,
                   *, width: int | None = None, height: int | None = None,
                   mutate_hash: bool = False, mutate_b64: bool = False) -> dict:
    fixture = synthetic_image()
    if width is None or height is None:
        width, height = fixture.size
    image_bytes = fixture.data
    image_b64 = base64.b64encode(image_bytes).decode('ascii')
    if mutate_b64:
        image_b64 = image_b64[:-4] + '!!!!'  # corrupt base64
    digest = hashlib.sha256(image_bytes).hexdigest()
    if mutate_hash:
        digest = '0' * 64
    return {
        'image_id': image_id,
        'modality': modality,
        'model_id': model_id,
        'image_b64': image_b64,
        'image_sha256': digest,
        'source_type': fixture.source_type,
        'width': width,
        'height': height,
    }
