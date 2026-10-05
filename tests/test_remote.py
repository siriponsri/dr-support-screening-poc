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
    RemoteNotConfiguredError,
    RemoteSchemaError,
    RemoteTimeoutError,
)
from dr_support.services.admission import legacy_admission


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
    app.state.model_gateway_transport = transport
    for provider in app.state.providers.values():
        if isinstance(provider, RemoteModelProvider):
            provider._transport = transport
            provider._client_timeout = 5.0
    return app


def _success_handler(global_body=None, lesion_body=None):
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        calls.append(request)
        if request.url.path == '/v1/models':
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
    # No inference yet — metadata should fall back to the /v1/models advertisement.
    info = provider.metadata()
    assert info['runtime'] == 'remote'
    assert info['revision'] == 'remote-rev-aaaa'
    assert info['checkpoint_sha256'] == {'retfound-remote': 'a' * 64}
    assert info['status'] == 'LOADED'
    assert any('remote-rev-aaaa' in w or 'remote' in w.lower() for w in info['warnings'])
    assert provider.last_metadata_ms is not None
    assert any(call.url.path == '/v1/models' for call in calls)


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


def test_remote_provider_reports_missing_url_without_startup_failure(monkeypatch):
    monkeypatch.delenv('REMOTE_MODEL_URL', raising=False)
    provider = RemoteGlobalProvider()
    info = provider.metadata()
    assert info['status'] == 'REMOTE_NOT_CONFIGURED'
    assert info['remote_url'] == ''
    assert any('AI analysis is not available' in warning for warning in info['warnings'])
    with pytest.raises(RemoteNotConfiguredError):
        provider.infer(InferenceRequest(image_id=FIXTURE_IMAGE.image_id, model_id=provider.model_id), FIXTURE_IMAGE)


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


def test_api_rejects_explicitly_not_ready_generic_capability_at_inference(monkeypatch):
    predict_calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        if request.url.path == '/v1/models':
            return httpx.Response(200, json=[{
                'model_id': 'generic-uwf-grader',
                'task': 'global',
                'modalities': ['UWF'],
                'status': 'LOADED',
                'capability_id': 'uwf-grade',
                'revision': 'r1',
                'preprocessing': 'uwf-v1',
                'ready': False,
            }])
        predict_calls.append(request.url.path)
        return httpx.Response(200, json=SAMPLE_GLOBAL_BODY)

    app = _wire_remote_app(monkeypatch, handle)
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    app.state.admissions[FIXTURE_IMAGE.image_id] = {
        **legacy_admission(FIXTURE_IMAGE),
        'retinal_modality': 'UWF',
    }
    client = TestClient(app)

    saved = client.put('/v1/model-connection', json={'name': 'Remote', 'url': 'https://remote.test'})
    assert saved.status_code == 200
    advertised = client.get('/v1/models').json()
    generic = next(item for item in advertised if item['model_id'] == 'generic-uwf-grader')
    assert generic['ready'] is False
    response = client.post('/v1/infer/global', json={
        'image_id': FIXTURE_IMAGE.image_id,
        'model_id': 'generic-uwf-grader',
        'modality': 'UWF',
    })
    assert response.status_code == 409
    assert 'capability is not ready' in response.json()['detail']
    assert predict_calls == []


def test_api_routes_qualified_generic_capability_with_preprocessing_alias(monkeypatch):
    predict_calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        if request.url.path == '/v1/models':
            return httpx.Response(200, json=[{
                'model_id': 'generic-uwf-grader',
                'task': 'global',
                'modalities': ['UWF'],
                'status': 'LOADED',
                'capability_id': 'uwf-grade',
                'revision': 'r1',
                'preprocessing_version': 'uwf-v1',
                'release_status': 'QUALIFIED',
                'ready': True,
            }])
        predict_calls.append(request.url.path)
        payload = json.loads(request.read())
        result = json.loads(json.dumps(SAMPLE_GLOBAL_BODY))
        result.update(model_id='generic-uwf-grader', modality='UWF')
        result['provenance']['image_sha256'] = payload['image_sha256']
        return httpx.Response(200, json=result)

    app = _wire_remote_app(monkeypatch, handle)
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    app.state.admissions[FIXTURE_IMAGE.image_id] = {
        **legacy_admission(FIXTURE_IMAGE),
        'retinal_modality': 'UWF',
    }
    client = TestClient(app)

    saved = client.put('/v1/model-connection', json={'name': 'Remote', 'url': 'https://remote.test'})
    assert saved.status_code == 200
    assert 'generic-uwf-grader' in app.state.providers
    assert saved.json()['models'][0]['ready'] is True
    response = client.post('/v1/infer/global', json={
        'image_id': FIXTURE_IMAGE.image_id,
        'model_id': 'generic-uwf-grader',
        'modality': 'UWF',
    })
    assert response.status_code == 200
    assert predict_calls == ['/v1/predict/dr']


def test_api_rechecks_remote_health_before_inference(monkeypatch):
    state = {'assets_verified': True}
    predict_calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/health':
            return httpx.Response(200, json={
                'status': 'PASS_WITH_WARNINGS',
                'assets_verified': state['assets_verified'],
            })
        if request.url.path == '/v1/models':
            return httpx.Response(200, json=[{
                'model_id': 'retfound-aptos5',
                'task': 'global',
                'modalities': ['CFP'],
                'status': 'LOADED',
            }])
        predict_calls.append(request.url.path)
        return httpx.Response(200, json=SAMPLE_GLOBAL_BODY)

    app = _wire_remote_app(monkeypatch, handle)
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    client = TestClient(app)

    saved = client.put('/v1/model-connection', json={'name': 'Remote', 'url': 'https://remote.test'})
    assert saved.status_code == 200
    state['assets_verified'] = False

    displayed = client.get('/v1/models').json()
    assert next(item for item in displayed if item['model_id'] == 'retfound-aptos5')['ready'] is False

    response = client.post('/v1/infer/global', json={
        'image_id': FIXTURE_IMAGE.image_id,
        'model_id': 'retfound-aptos5',
        'modality': 'CFP',
    })

    assert response.status_code == 503
    assert predict_calls == []


def test_api_does_not_promote_registry_disabled_uwf_identity(monkeypatch):
    predict_calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        if request.url.path == '/v1/models':
            return httpx.Response(200, json=[{
                'model_id': 'uspec-uwf-grading',
                'task': 'global',
                'modalities': ['UWF'],
                'status': 'LOADED',
                'capability_id': 'dr_grade',
                'revision': 'r1',
                'preprocessing': 'uwf-v1',
                'release_status': 'QUALIFIED',
            }])
        predict_calls.append(request.url.path)
        return httpx.Response(200, json=SAMPLE_GLOBAL_BODY)

    app = _wire_remote_app(monkeypatch, handle)
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    app.state.admissions[FIXTURE_IMAGE.image_id] = {
        **legacy_admission(FIXTURE_IMAGE),
        'retinal_modality': 'UWF',
    }
    client = TestClient(app)

    saved = client.put('/v1/model-connection', json={'name': 'Remote', 'url': 'https://remote.test'})
    assert saved.status_code == 200
    advertised = next(item for item in client.get('/v1/models').json() if item['model_id'] == 'uspec-uwf-grading')
    assert advertised['release_status'] == 'DISABLED'
    assert advertised['ready'] is False

    response = client.post('/v1/infer/global', json={
        'image_id': FIXTURE_IMAGE.image_id,
        'model_id': 'uspec-uwf-grading',
        'modality': 'UWF',
    })
    assert response.status_code == 409
    assert 'manual review remains available' in response.json()['detail']
    assert predict_calls == []


def test_api_rejects_non_boolean_ready_advertisement(monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        if request.url.path == '/v1/models':
            return httpx.Response(200, json=[{
                'model_id': 'generic-uwf-grader',
                'task': 'global',
                'modalities': ['UWF'],
                'status': 'LOADED',
                'capability_id': 'uwf-grade',
                'revision': 'r1',
                'preprocessing': 'uwf-v1',
                'ready': 'false',
            }])
        return httpx.Response(404)

    app = _wire_remote_app(monkeypatch, handle)
    response = TestClient(app).put(
        '/v1/model-connection',
        json={'name': 'Remote', 'url': 'https://remote.test'},
    )

    assert response.status_code == 502
    assert 'capabilities did not match' in response.json()['detail']


def test_api_returns_504_when_remote_times_out(monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        if request.url.path == '/v1/models':
            return httpx.Response(200, json=[{
                'model_id': 'retfound-aptos5',
                'task': 'global',
                'modalities': ['CFP'],
                'status': 'LOADED',
            }])
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
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        if request.url.path == '/v1/models':
            return httpx.Response(200, json=[{
                'model_id': 'retfound-aptos5',
                'task': 'global',
                'modalities': ['CFP'],
                'status': 'LOADED',
            }])
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
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        if request.url.path == '/v1/models':
            return httpx.Response(200, json=[{
                'model_id': 'retfound-aptos5',
                'task': 'global',
                'modalities': ['CFP'],
                'status': 'LOADED',
            }])
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


def test_api_starts_without_remote_url_and_keeps_inference_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_PROFILE', 'review')
    monkeypatch.setenv('MODEL_RUNTIME', 'remote')
    monkeypatch.delenv('REMOTE_MODEL_URL', raising=False)
    monkeypatch.delenv('REMOTE_MODEL_TOKEN', raising=False)
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    app = create_app(include_samples=False)
    client = TestClient(app)
    models = client.get('/v1/models')
    assert models.status_code == 200
    descriptors = {item['model_id']: item for item in models.json()}
    assert descriptors['retfound-aptos5']['status'] == 'REMOTE_NOT_CONFIGURED'
    assert descriptors['prism-dr-5fold']['status'] == 'REMOTE_NOT_CONFIGURED'
    inference = client.post('/v1/infer/global', json={
        'image_id': FIXTURE_IMAGE.image_id,
        'model_id': 'retfound-aptos5',
        'modality': 'CFP',
    })
    assert inference.status_code == 503
    assert inference.json()['detail'] == 'AI analysis is not available; manual review remains available.'
    assert 'RemoteNotConfiguredError' not in inference.text
    assert client.get('/v1/workspaces').status_code == 200
    assert client.get('/v1/workspaces/active').status_code == 200
    assert client.post('/v1/admissions/scan').json()['scanned'] is False
    case = client.get(f'/v1/cases/{FIXTURE_IMAGE.image_id}')
    assert case.status_code == 200
    resolved = client.post(f'/v1/cases/{FIXTURE_IMAGE.image_id}/resolver', json={
        'revision': case.json()['revision'],
        'reviewer': 'Offline clinician',
        'patient_action': 'LEAVE_UNLINKED',
        'laterality_action': 'SET',
        'laterality': 'UNKNOWN',
    })
    assert resolved.status_code == 200


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


# ---------------------------------------------------------------------------
# M0.8 — Windows worklist remote-metadata startup regression tests.
#
# These tests pin the contract that the local /v1/models handler must always
# return HTTP 200 + valid JSON even when the remote Model API is:
#   - returning 404 on the wrong path
#   - timing out / unreachable
#   - returning a non-JSON body
#   - returning a malformed schema
#   - raising an unexpected exception
# And that the bearer token never leaks through the degraded descriptor.
# ---------------------------------------------------------------------------


def test_remote_provider_metadata_queries_v1_models_path(monkeypatch):
    """The deployed Model API exposes /v1/models; the proxy must call it."""
    captured = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=[{'model_id': 'retfound-aptos5', 'task': 'global',
                                          'revision': 'remote-rev-aaaa',
                                          'modalities': ['CFP'], 'status': 'LOADED'}])

    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    provider = RemoteGlobalProvider(transport=httpx.MockTransport(handle), timeout=5.0)
    info = provider.metadata()
    assert info['status'] == 'LOADED'
    paths = [req.url.path for req in captured]
    assert '/v1/models' in paths
    # Defensive: the legacy /models path must NOT be called. If a future
    # refactor reintroduces it the UI Worklist would silently miss metadata
    # on the real Lightning deployment.
    assert '/models' not in paths or paths.count('/models') == 0


def test_api_v1_models_200_when_remote_metadata_404(monkeypatch):
    """A 404 on the remote metadata route must not crash local /v1/models."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        if request.url.path == '/v1/models':
            return httpx.Response(404, text='not found', headers={'content-type': 'text/plain'})
        # Inference path: keep returning a valid payload so unrelated tests
        # would not be affected if a future change wires this handler in.
        return httpx.Response(200, json=SAMPLE_GLOBAL_BODY)

    app = _wire_remote_app(monkeypatch, handle)
    client = TestClient(app)
    response = client.get('/v1/models')
    assert response.status_code == 200
    assert response.headers.get('content-type', '').startswith('application/json')
    body = response.json()
    # 4 descriptors expected: 2 synthetic + 2 remote (one per provider).
    assert len(body) == 4
    descriptors = {m['model_id']: m for m in body}
    for mid in ('retfound-aptos5', 'prism-dr-5fold'):
        assert descriptors[mid]['runtime'] == 'remote'
        assert descriptors[mid]['status'].startswith('REMOTE_HTTP_404')
        assert any('/v1/models' in w for w in descriptors[mid]['warnings'])


def test_api_v1_models_200_when_remote_metadata_times_out(monkeypatch):
    """A metadata timeout must not crash local /v1/models."""

    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('simulated metadata timeout', request=request)

    app = _wire_remote_app(monkeypatch, handle)
    client = TestClient(app)
    response = client.get('/v1/models')
    assert response.status_code == 200
    assert response.headers.get('content-type', '').startswith('application/json')
    descriptors = {m['model_id']: m for m in response.json()}
    for mid in ('retfound-aptos5', 'prism-dr-5fold'):
        assert descriptors[mid]['status'] == 'REMOTE_UNREACHABLE'


def test_api_v1_models_200_when_remote_metadata_unreachable(monkeypatch):
    """A connection error must not crash local /v1/models."""

    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('simulated offline', request=request)

    app = _wire_remote_app(monkeypatch, handle)
    client = TestClient(app)
    response = client.get('/v1/models')
    assert response.status_code == 200
    assert response.headers.get('content-type', '').startswith('application/json')
    descriptors = {m['model_id']: m for m in response.json()}
    assert descriptors['retfound-aptos5']['status'] == 'REMOTE_UNREACHABLE'
    assert descriptors['prism-dr-5fold']['status'] == 'REMOTE_UNREACHABLE'


def test_api_v1_models_200_when_remote_metadata_non_json(monkeypatch):
    """A text/plain metadata body must not crash local /v1/models."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        if request.url.path == '/v1/models':
            return httpx.Response(200, text='Internal Server Error',
                                  headers={'content-type': 'text/plain'})
        return httpx.Response(200, json=SAMPLE_GLOBAL_BODY)

    app = _wire_remote_app(monkeypatch, handle)
    client = TestClient(app)
    response = client.get('/v1/models')
    assert response.status_code == 200
    assert response.headers.get('content-type', '').startswith('application/json')
    descriptors = {m['model_id']: m for m in response.json()}
    for mid in ('retfound-aptos5', 'prism-dr-5fold'):
        assert descriptors[mid]['status'] == 'REMOTE_INVALID_JSON'


def test_api_v1_models_200_when_remote_metadata_wrong_schema(monkeypatch):
    """A metadata body that is not a JSON array must not crash local /v1/models."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        if request.url.path == '/v1/models':
            return httpx.Response(200, json={'oops': 'not an array'})
        return httpx.Response(200, json=SAMPLE_GLOBAL_BODY)

    app = _wire_remote_app(monkeypatch, handle)
    client = TestClient(app)
    response = client.get('/v1/models')
    assert response.status_code == 200
    descriptors = {m['model_id']: m for m in response.json()}
    for mid in ('retfound-aptos5', 'prism-dr-5fold'):
        assert descriptors[mid]['status'] == 'REMOTE_INVALID_SCHEMA'


def test_api_v1_models_200_when_remote_metadata_unexpected_exception(monkeypatch):
    """An unexpected exception inside metadata() must not crash local /v1/models."""

    class BoomProvider(RemoteGlobalProvider):
        def metadata(self):  # type: ignore[override]
            raise RuntimeError('simulated metadata bug')

    monkeypatch.setenv('MODEL_RUNTIME', 'remote')
    monkeypatch.delenv('REMOTE_MODEL_URL', raising=False)
    monkeypatch.delenv('REMOTE_MODEL_TOKEN', raising=False)
    app = create_app(include_samples=False)
    # Replace one provider with a faulty one to exercise the api/_factory
    # belt-and-suspenders guard.
    for mid, provider in list(app.state.providers.items()):
        if isinstance(provider, RemoteGlobalProvider):
            app.state.providers[mid] = BoomProvider(base_url='https://remote.test',
                                                    token='synthetic-remote-secret',
                                                    transport=provider._transport)
    client = TestClient(app)
    response = client.get('/v1/models')
    assert response.status_code == 200
    descriptors = {m['model_id']: m for m in response.json()}
    assert descriptors['retfound-aptos5']['status'] == 'REMOTE_INVALID_SCHEMA'
    assert any('simulated metadata bug' in w or 'Provider metadata failed' in w
               for w in descriptors['retfound-aptos5']['warnings'])


def test_api_v1_models_uses_one_shared_remote_probe_for_all_providers(monkeypatch):
    calls = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        if request.url.path == '/v1/models':
            return httpx.Response(200, json=[
                {'model_id': 'retfound-aptos5', 'task': 'global',
                 'modalities': ['CFP'], 'status': 'LOADED'},
                {'model_id': 'prism-dr-5fold', 'task': 'lesion-roi',
                 'modalities': ['CFP'], 'status': 'LOADED'},
            ])
        return httpx.Response(404)

    app = _wire_remote_app(monkeypatch, handle)
    response = TestClient(app).get('/v1/models')

    assert response.status_code == 200
    assert calls.count('/health') == 1
    assert calls.count('/v1/models') == 1


def test_api_refresh_replaces_provider_when_advertised_task_changes(monkeypatch):
    state = {'task': 'global'}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS', 'assets_verified': True})
        if request.url.path == '/v1/models':
            return httpx.Response(200, json=[{
                'model_id': 'generic-capability',
                'task': state['task'],
                'modalities': ['CFP'],
                'status': 'LOADED',
                'capability_id': 'review-capability',
                'revision': 'r1',
                'preprocessing': 'cfp-v1',
                'release_status': 'QUALIFIED',
            }])
        if request.url.path == '/v1/predict/lesions':
            result = json.loads(json.dumps(SAMPLE_LESION_BODY))
            payload = json.loads(request.read())
            result['provenance']['image_sha256'] = payload['image_sha256']
            return httpx.Response(200, json=result)
        return httpx.Response(404)

    app = _wire_remote_app(monkeypatch, handle)
    app.state.images[FIXTURE_IMAGE.image_id] = FIXTURE_IMAGE
    client = TestClient(app)

    saved = client.put('/v1/model-connection', json={'name': 'Remote', 'url': 'https://remote.test'})
    assert saved.status_code == 200
    assert app.state.providers['generic-capability'].task == 'global'

    state['task'] = 'lesion-roi'
    refreshed = client.get('/v1/models')
    assert refreshed.status_code == 200
    assert app.state.providers['generic-capability'].task == 'lesion-roi'

    response = client.post('/v1/infer/lesion-roi', json={
        'image_id': FIXTURE_IMAGE.image_id,
        'model_id': 'generic-capability',
        'modality': 'CFP',
    })
    assert response.status_code == 200


def test_api_v1_models_never_leaks_token_in_metadata_failures(monkeypatch, caplog):
    """The bearer token must not appear in /v1/models output or log output,
    even when the remote returns garbage."""

    secret = 'super-secret-deploy-token-do-not-leak'

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/v1/models':
            return httpx.Response(500, text=f'upstream; bearer={secret}',
                                  headers={'content-type': 'text/plain'})
        return httpx.Response(200, json=SAMPLE_GLOBAL_BODY)

    app = _wire_remote_app(monkeypatch, handle, token=secret)
    client = TestClient(app)
    import logging
    caplog.set_level(logging.DEBUG)
    with caplog.at_level(logging.DEBUG):
        response = client.get('/v1/models')
    assert response.status_code == 200
    assert secret not in response.text
    log_text = '\n'.join(record.getMessage() for record in caplog.records)
    assert secret not in log_text


def test_remote_provider_metadata_degraded_message_mentions_v1_models(monkeypatch):
    """The degraded descriptor warning should advertise the corrected path
    so operators can immediately see whether the proxy is hitting the
    deployed Model API contract."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text='not found',
                              headers={'content-type': 'text/plain'})

    monkeypatch.setenv('REMOTE_MODEL_URL', 'https://remote.test')
    provider = RemoteGlobalProvider(transport=httpx.MockTransport(handle), timeout=5.0)
    info = provider.metadata()
    assert info['status'].startswith('REMOTE_HTTP_404')
    # The warning text must reference the v1 path (not the legacy /models).
    assert any('/v1/models' in w for w in info['warnings'])
    assert not any('GET /models ' in w or 'GET /models returned' in w for w in info['warnings'])
