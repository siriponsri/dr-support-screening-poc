"""Mocked integration tests for the provider-neutral REMOTE inference adapter.

These tests do not exercise a real Remote Model API. They inject an
``httpx.MockTransport`` so the backend proxy runs against a deterministic
in-memory handler. The same pattern is used by CVAT Online tests.
"""
import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from dr_support.api import create_app
from dr_support.contracts import GlobalResult, InferenceRequest
from dr_support.images import synthetic_image
from dr_support.providers.remote import (
    RemoteGlobalProvider,
    RemoteHTTPError,
    RemoteLesionProvider,
    RemoteModelProvider,
    RemoteSchemaError,
    RemoteTimeoutError,
)


FIXTURE_IMAGE = synthetic_image()


SAMPLE_GLOBAL_BODY = {
    'schema_version': 'bridge.v1',
    'model_id': 'retfound-aptos5',
    'model_version': 'remote-rev-aaaa',
    'modality': 'CFP',
    'state': 'AI_SUGGESTION',
    'grade': 2,
    'probabilities': [0.05, 0.10, 0.70, 0.10, 0.05],
    'confidence': 0.70,
    'warnings': ['Research-only; served by remote'],
    'provenance': {
        'image_sha256': FIXTURE_IMAGE.sha256,
        'source_type': 'SYNTHETIC',
        'preprocessing': 'remote-v1',
        'source_revision': 'remote-rev-aaaa',
        'checkpoint_sha256': {'retfound-remote': 'a' * 64},
    },
}


SAMPLE_LESION_BODY = {
    'schema_version': 'bridge.v1',
    'model_id': 'prism-dr-5fold',
    'model_version': 'remote-rev-bbbb',
    'modality': 'CFP',
    'state': 'AI_SUGGESTION',
    'width': FIXTURE_IMAGE.size[0],
    'height': FIXTURE_IMAGE.size[1],
    'lesions': [
        {
            'source_label': 'MA',
            'canonical_label': 'MICROANEURYSM',
            'rectangle': [250.0, 160.0, 264.0, 176.0],
            'score': 0.8,
            'state': 'AI_SUGGESTION',
        }
    ],
    'warnings': ['Research-only; served by remote'],
    'provenance': {
        'image_sha256': FIXTURE_IMAGE.sha256,
        'source_type': 'SYNTHETIC',
        'preprocessing': 'remote-v1',
        'source_revision': 'remote-rev-bbbb',
        'checkpoint_sha256': {'prism-remote': 'b' * 64},
    },
}


def _wire_remote_app(monkeypatch, handler, *, token='synthetic-remote-secret', runtime='remote',
                     url='https://remote.test'):
    """Inject a mocked remote transport into the FastAPI app under test."""
    monkeypatch.setenv('MODEL_RUNTIME', runtime)
    monkeypatch.setenv('REMOTE_MODEL_URL', url)
    if token is None:
        monkeypatch.delenv('REMOTE_MODEL_TOKEN', raising=False)
    else:
        monkeypatch.setenv('REMOTE_MODEL_TOKEN', token)
    transport = httpx.MockTransport(handler)
    app = create_app(include_samples=False)
    for provider in app.state.providers.values():
        if isinstance(provider, RemoteModelProvider):
            provider._transport = transport
            provider._client_timeout = 5.0
    return app


def _success_handler(global_body=None, lesion_body=None):
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == '/models':
            return httpx.Response(200, json=[
                {
                    'model_id': 'retfound-aptos5',
                    'task': 'global',
                    'revision': 'remote-rev-aaaa',
                    'checkpoint_sha256': {'retfound-remote': 'a' * 64},
                    'modalities': ['CFP'],
                    'status': 'LOADED',
                    'warnings': ['Remote is healthy'],
                    'preprocessing': 'remote-v1',
                },
                {
                    'model_id': 'prism-dr-5fold',
                    'task': 'lesion-roi',
                    'revision': 'remote-rev-bbbb',
                    'checkpoint_sha256': {'prism-remote': 'b' * 64},
                    'modalities': ['CFP'],
                    'status': 'LOADED',
                    'warnings': ['Remote is healthy'],
                    'preprocessing': 'remote-v1',
                },
            ])
        if request.url.path == '/v1/predict/dr':
            return httpx.Response(200, json=global_body or SAMPLE_GLOBAL_BODY)
        if request.url.path == '/v1/predict/lesions':
            return httpx.Response(200, json=lesion_body or SAMPLE_LESION_BODY)
        return httpx.Response(404, json={'detail': 'not found'})

    return calls, handle


# ---------------------------------------------------------------------------
# Provider-level tests (no FastAPI)
# ---------------------------------------------------------------------------


def test_remote_provider_proxies_inference_payload_and_token(monkeypatch):
    captured = {}
    global_body = json.loads(json.dumps(SAMPLE_GLOBAL_BODY))

    def handle(request: httpx.Request) -> httpx.Response:
        captured['path'] = request.url.path
        captured['headers'] = dict(request.headers)
        captured['json'] = request.read()
        return httpx.Response(200, json=global_body)

    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    monkeypatch.setenv('REMOTE_MODEL_TOKEN', 'super-secret-remote-token')
    provider = RemoteGlobalProvider(transport=httpx.MockTransport(handle), timeout=5.0)
    request = InferenceRequest(image_id=FIXTURE_IMAGE.image_id, modality='CFP',
                               model_id=RemoteGlobalProvider.model_id)
    result = provider.infer(request, FIXTURE_IMAGE)

    assert captured['path'] == '/v1/predict/dr'
    # httpx stores headers case-insensitively (lowercase) in MockTransport captures.
    headers_lower = {k.lower(): v for k, v in captured['headers'].items()}
    assert headers_lower.get('authorization') == 'Bearer super-secret-remote-token'
    assert headers_lower.get('accept') == 'application/json'
    body = json.loads(captured['json'])
    assert body['image_id'] == FIXTURE_IMAGE.image_id
    assert body['modality'] == 'CFP'
    assert body['model_id'] == 'retfound-aptos5'
    assert base64.b64decode(body['image_b64']) == FIXTURE_IMAGE.data
    assert body['image_sha256'] == FIXTURE_IMAGE.sha256
    assert isinstance(result, GlobalResult)
    assert result.grade == 2
    assert provider.last_inference_ms is not None and provider.last_inference_ms >= 0
    assert provider.last_remote_revision == 'remote-rev-aaaa'
    assert provider.last_remote_checkpoint_sha256 == {'retfound-remote': 'a' * 64}


def test_remote_provider_omits_authorization_when_token_unset(monkeypatch):
    captured = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured['headers'] = dict(request.headers)
        return httpx.Response(200, json=SAMPLE_LESION_BODY)

    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    monkeypatch.delenv('REMOTE_MODEL_TOKEN', raising=False)
    provider = RemoteLesionProvider(transport=httpx.MockTransport(handle), timeout=5.0)
    request = InferenceRequest(image_id=FIXTURE_IMAGE.image_id, model_id=provider.model_id)
    provider.infer(request, FIXTURE_IMAGE)
    assert 'Authorization' not in captured['headers']


def test_remote_provider_timeout_raises_remote_timeout(monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('simulated timeout', request=request)

    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    provider = RemoteGlobalProvider(transport=httpx.MockTransport(handle), timeout=0.01)
    request = InferenceRequest(image_id=FIXTURE_IMAGE.image_id, model_id=provider.model_id)
    with pytest.raises(RemoteTimeoutError):
        provider.infer(request, FIXTURE_IMAGE)
    assert provider.last_error and 'timeout' in provider.last_error


def test_remote_provider_non_2xx_raises_remote_http(monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text='service unavailable')

    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    provider = RemoteGlobalProvider(transport=httpx.MockTransport(handle), timeout=5.0)
    request = InferenceRequest(image_id=FIXTURE_IMAGE.image_id, model_id=provider.model_id)
    with pytest.raises(RemoteHTTPError):
        provider.infer(request, FIXTURE_IMAGE)
    assert provider.last_error == 'HTTP 503'


def test_remote_provider_malformed_payload_raises_schema_error(monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'this': 'is not a valid Bridge v1 result'})

    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    provider = RemoteGlobalProvider(transport=httpx.MockTransport(handle), timeout=5.0)
    request = InferenceRequest(image_id=FIXTURE_IMAGE.image_id, model_id=provider.model_id)
    with pytest.raises(RemoteSchemaError):
        provider.infer(request, FIXTURE_IMAGE)
    assert provider.last_error == 'schema mismatch'


def test_remote_provider_metadata_surfaces_remote_revision_hash_and_latency(monkeypatch):
    calls, handle = _success_handler()

    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    provider = RemoteGlobalProvider(transport=httpx.MockTransport(handle), timeout=5.0)
    # No inference yet — metadata should fall back to /models advertisement.
    info = provider.metadata()
    assert info['runtime'] == 'remote'
    assert info['revision'] == 'remote-rev-aaaa'
    assert info['checkpoint_sha256'] == {'retfound-remote': 'a' * 64}
    assert info['status'] == 'LOADED'
    assert any('remote-rev-aaaa' in w or 'remote' in w.lower() for w in info['warnings'])
    assert provider.last_metadata_ms is not None
    assert any(call.url.path == '/models' for call in calls)


def test_remote_provider_metadata_reports_unreachable_when_remote_down(monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('simulated offline', request=request)

    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    provider = RemoteGlobalProvider(transport=httpx.MockTransport(handle), timeout=0.1)
    info = provider.metadata()
    assert info['status'] == 'REMOTE_UNREACHABLE'
    assert info['remote_url'] == 'https://remote.test'
    assert any('REMOTE_UNREACHABLE' in w for w in info['warnings'])


def test_remote_provider_metadata_reports_model_not_listed(monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{'model_id': 'something-else', 'task': 'global'}])

    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    provider = RemoteGlobalProvider(transport=httpx.MockTransport(handle), timeout=5.0)
    info = provider.metadata()
    assert info['status'] == 'REMOTE_MODEL_NOT_LISTED'


def test_remote_provider_rejects_missing_url(monkeypatch):
    monkeypatch.delenv('REMOTE_MODEL_URL', raising=False)
    with pytest.raises(ValueError, match='REMOTE_MODEL_URL'):
        RemoteGlobalProvider()


def test_remote_provider_rejects_non_http_scheme(monkeypatch):
    with pytest.raises(ValueError, match='http'):
        RemoteGlobalProvider(base_url='ftp://remote.test')


def test_remote_provider_never_includes_token_in_metadata(monkeypatch):
    calls, handle = _success_handler()
    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    monkeypatch.setenv('REMOTE_MODEL_TOKEN', 'super-secret-remote-token')
    provider = RemoteGlobalProvider(transport=httpx.MockTransport(handle), timeout=5.0)
    info = provider.metadata()
    dumped = json.dumps(info)
    assert 'super-secret-remote-token' not in dumped
    # And the Authorization header was sent (proves wiring), but not leaked.
    sent_auth = next((call.headers.get('authorization') or call.headers.get('Authorization'))
                     for call in calls if call.headers.get('authorization') or call.headers.get('Authorization'))
    assert sent_auth == 'Bearer super-secret-remote-token'


# ---------------------------------------------------------------------------
# FastAPI-level tests (full proxy via create_app)
# ---------------------------------------------------------------------------


def test_api_routes_inference_through_remote_provider(monkeypatch, tmp_path):
    calls, handle = _success_handler()
    app = _wire_remote_app(monkeypatch, handle, token='synthetic-remote-secret',
                           url='https://remote.test')
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    client = TestClient(app)

    response = client.post('/v1/infer/global',
                           json={'image_id': FIXTURE_IMAGE.image_id,
                                 'model_id': 'retfound-aptos5', 'modality': 'CFP'})
    assert response.status_code == 200
    body = response.json()
    assert body['grade'] == 2
    assert body['model_version'] == 'remote-rev-aaaa'

    response = client.post('/v1/infer/lesion-roi',
                           json={'image_id': FIXTURE_IMAGE.image_id,
                                 'model_id': 'prism-dr-5fold', 'modality': 'CFP'})
    assert response.status_code == 200
    body = response.json()
    assert body['lesions'][0]['canonical_label'] == 'MICROANEURYSM'

    paths = [call.url.path for call in calls]
    assert '/v1/predict/dr' in paths and '/v1/predict/lesions' in paths

    case = client.get(f'/v1/cases/{FIXTURE_IMAGE.image_id}').json()
    inference_events = [e for e in case['events'] if e.get('action') == 'INFERENCE']
    assert inference_events, 'no INFERENCE events recorded'
    assert all(e.get('runtime') == 'remote' for e in inference_events)
    assert all(isinstance(e.get('latency_ms'), (int, float)) for e in inference_events)


def test_api_returns_504_when_remote_times_out(monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('simulated', request=request)

    app = _wire_remote_app(monkeypatch, handle)
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    client = TestClient(app)
    response = client.post('/v1/infer/global',
                           json={'image_id': FIXTURE_IMAGE.image_id,
                                 'model_id': 'retfound-aptos5'})
    assert response.status_code == 504
    assert 'timeout' in response.json()['detail'].lower()


def test_api_returns_502_when_remote_returns_non_2xx(monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/models':
            return httpx.Response(200, json=[{'model_id': 'retfound-aptos5', 'task': 'global'}])
        return httpx.Response(500, json={'error': 'upstream'})

    app = _wire_remote_app(monkeypatch, handle)
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    client = TestClient(app)
    response = client.post('/v1/infer/global',
                           json={'image_id': FIXTURE_IMAGE.image_id,
                                 'model_id': 'retfound-aptos5'})
    assert response.status_code == 502
    assert 'Remote model error' in response.json()['detail']


def test_api_returns_502_when_remote_returns_malformed_payload(monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/models':
            return httpx.Response(200, json=[{'model_id': 'retfound-aptos5', 'task': 'global'}])
        return httpx.Response(200, json={'not': 'a bridge result'})

    app = _wire_remote_app(monkeypatch, handle)
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    client = TestClient(app)
    response = client.post('/v1/infer/global',
                           json={'image_id': FIXTURE_IMAGE.image_id,
                                 'model_id': 'retfound-aptos5'})
    assert response.status_code == 502


def test_api_v1_models_surfaces_remote_runtime_metadata(monkeypatch):
    _, handle = _success_handler()
    app = _wire_remote_app(monkeypatch, handle)
    client = TestClient(app)
    response = client.get('/v1/models')
    assert response.status_code == 200
    descriptors = {m['model_id']: m for m in response.json()}
    assert descriptors['retfound-aptos5']['runtime'] == 'remote'
    assert descriptors['retfound-aptos5']['revision'] == 'remote-rev-aaaa'
    assert descriptors['prism-dr-5fold']['runtime'] == 'remote'
    assert descriptors['prism-dr-5fold']['revision'] == 'remote-rev-bbbb'


def test_api_rejects_missing_remote_url_when_runtime_remote(monkeypatch):
    monkeypatch.setenv('MODEL_RUNTIME', 'remote')
    monkeypatch.delenv('REMOTE_MODEL_URL', raising=False)
    monkeypatch.delenv('REMOTE_MODEL_TOKEN', raising=False)
    with pytest.raises(RuntimeError, match='REMOTE_MODEL_URL'):
        create_app(include_samples=False)


def test_api_local_mode_is_unaffected_by_remote_env(monkeypatch):
    monkeypatch.delenv('MODEL_RUNTIME', raising=False)
    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    monkeypatch.setenv('REMOTE_MODEL_TOKEN', 'should-not-be-used')
    client = TestClient(create_app(include_samples=False))
    app = client.app
    assert app.state.remote_runtime is False
    assert not any(isinstance(p, RemoteModelProvider) for p in app.state.providers.values())
    descriptors = {m['model_id']: m for m in client.get('/v1/models').json()}
    # Local metadata does not advertise the remote runtime field.
    assert 'runtime' not in descriptors['retfound-aptos5']


def test_api_does_not_leak_token_through_models_endpoint(monkeypatch, tmp_path):
    calls, handle = _success_handler()
    app = _wire_remote_app(monkeypatch, handle, token='synthetic-remote-secret')
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    client = TestClient(app)
    response = client.get('/v1/models')
    assert response.status_code == 200
    assert 'synthetic-remote-secret' not in response.text
    # Run lesion inference first so the CVAT sync has an upstream prediction to bind to,
    # then confirm the CVAT round-trip still surfaces OWNER_ACTION_REQUIRED without CVAT_TOKEN.
    client.post('/v1/infer/lesion-roi', json={'image_id': FIXTURE_IMAGE.image_id,
                                              'model_id': 'prism-dr-5fold'})
    cvat_response = client.post(f'/v1/cases/{FIXTURE_IMAGE.image_id}/cvat/send', json={})
    assert cvat_response.status_code == 503
    assert 'OWNER_ACTION_REQUIRED' in cvat_response.json()['detail']


def test_api_preserves_cvat_review_state_in_remote_mode(monkeypatch):
    calls, handle = _success_handler()
    app = _wire_remote_app(monkeypatch, handle)
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    client = TestClient(app)
    client.post('/v1/infer/global', json={'image_id': FIXTURE_IMAGE.image_id,
                                           'model_id': 'retfound-aptos5'})
    case = client.get(f'/v1/cases/{FIXTURE_IMAGE.image_id}').json()
    review = client.post(f'/v1/cases/{FIXTURE_IMAGE.image_id}/review',
                         json={'revision': case['revision'], 'action': 'ACCEPT',
                               'reviewer': 'Remote fixture'})
    assert review.status_code == 200
    assert review.json()['state'] == 'REVIEWED'
