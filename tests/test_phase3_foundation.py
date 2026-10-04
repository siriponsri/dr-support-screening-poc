"""Contract and safety tests for the Phase 3 foundation."""

import base64
import hashlib

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from dr_support.api import create_app as create_review_app
from dr_support.app import create_app
from dr_support.contracts import (
    GlobalResult,
    Phase3Explanation,
    Phase3PredictRequest,
)
from dr_support.phase3_registry import capability_descriptors, descriptor_for
from dr_support.services.model_gateway import probe_model_connection


def _encoded_fixture() -> tuple[bytes, str]:
    output = __import__('io').BytesIO()
    Image.new('RGB', (32, 24), '#777777').save(output, format='PNG')
    raw = output.getvalue()
    return raw, hashlib.sha256(raw).hexdigest()


def test_bridge_v1_remains_strict_and_phase3_context_binds_analysis_bytes():
    raw, digest = _encoded_fixture()
    request = Phase3PredictRequest(
        invocation_id='invoke-12345678',
        capability_id='dr_grade',
        task='global',
        model_id='uspec-uwf-grading',
        model_version='grading_state.pt-candidate',
        image_id='synthetic-1',
        modality='UWF',
        image_b64=base64.b64encode(raw).decode('ascii'),
        image_sha256=digest,
        source_sha256='a' * 64,
        source_origin='SYNTHETIC',
        analysis_sha256=digest,
        representation_version='phase2-uwf-v1',
        transform_id='analysis-uwf-v1',
        request_case_revision=4,
        width=32,
        height=24,
    )
    assert request.analysis_sha256 == digest
    with pytest.raises(ValueError, match='analysis_sha256'):
        Phase3PredictRequest(
            **request.model_dump(exclude={'analysis_sha256'}),
            analysis_sha256='b' * 64,
        )
    with pytest.raises(ValueError, match='Available explanation'):
        Phase3Explanation(
            status='AVAILABLE',
            invocation_id='invoke-12345678',
            model_id='uspec-uwf-grading',
            source_sha256='a' * 64,
            analysis_sha256=digest,
        )

    legacy = GlobalResult(
        model_id='legacy',
        model_version='v1',
        modality='CFP',
        state='AI_SUGGESTION',
        grade=2,
        probabilities=[0.0, 0.0, 1.0, 0.0, 0.0],
        confidence=1.0,
        provenance={
            'image_sha256': 'a' * 64,
            'source_type': 'SYNTHETIC',
            'preprocessing': 'fixture',
            'source_revision': 'v1',
        },
    )
    assert GlobalResult.model_validate(legacy.model_dump()).schema_version == 'bridge.v1'


def test_registry_keeps_uspec_blocked_and_does_not_promote_release_by_runtime():
    entries = capability_descriptors([{
        'model_id': 'uspec-uwf-grading',
        'task': 'global',
        'status': 'LOADED',
        'revision': 'runtime-revision',
        'modalities': ['UWF'],
    }])
    uspec = next(item for item in entries if item['model_id'] == 'uspec-uwf-grading')
    assert uspec['runtime_status'] == 'LOADED'
    assert uspec['release_status'] == 'DISABLED'
    assert any(item['model_id'] == 'native-uwf-lesion-localizer'
               and item['status'] == 'DEFERRED_NO_QUALIFIED_CANDIDATE' for item in entries)
    assert descriptor_for('uspec-uwf-grading')['artifact_digest'] == '8f07eb11859f638faee368a56c7c532ca946fee320f92f030a0cf25c63b769ac'


def test_model_gateway_accepts_capability_or_legacy_discovery():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/health':
            return httpx.Response(200, json={'status': 'PASS'})
        return httpx.Response(200, json=[{
            'model_id': 'uspec-uwf-grading',
            'capability_id': 'dr_grade',
            'task': 'global',
            'status': 'BLOCKED_ARTIFACT',
            'modalities': ['UWF'],
        }])

    probe = probe_model_connection(
        'https://model-api.test',
        transport=httpx.MockTransport(handler),
    )
    assert probe.verified is True
    assert probe.models[0]['capability_id'] == 'dr_grade'


def test_model_api_v2_blocks_workspace_origin_and_reports_unenabled_uspec(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_PROFILE', 'model_api')
    monkeypatch.setenv('MODEL_RUNTIME', 'local')
    monkeypatch.setenv('DR_SUPPORT_STATE', str(tmp_path / 'state.sqlite'))
    app = create_app()
    client = TestClient(app)
    raw, digest = _encoded_fixture()
    body = {
        'invocation_id': 'invoke-12345678',
        'capability_id': 'dr_grade',
        'task': 'global',
        'model_id': 'uspec-uwf-grading',
        'model_version': 'grading_state.pt-candidate',
        'image_id': 'synthetic-1',
        'modality': 'UWF',
        'image_b64': base64.b64encode(raw).decode('ascii'),
        'image_sha256': digest,
        'source_sha256': 'a' * 64,
        'source_origin': 'SYNTHETIC',
        'analysis_sha256': digest,
        'representation_version': 'phase2-uwf-v1',
        'transform_id': 'analysis-uwf-v1',
        'request_case_revision': 0,
        'width': 32,
        'height': 24,
    }
    response = client.post('/v2/predict/dr', json=body)
    assert response.status_code == 200
    assert response.json()['status'] == 'BLOCKED'
    body['source_origin'] = 'WORKSPACE'
    assert client.post('/v2/predict/dr', json=body).status_code == 409


def test_inference_history_preserves_confirmed_human_grade_and_stale_duplicate_runs(tmp_path):
    app = create_review_app(
        state_path=tmp_path / 'state.sqlite',
        include_samples=True,
        include_demo_fixtures=True,
    )
    client = TestClient(app)
    initial = client.get('/v1/cases/SYNTH_001').json()
    inferred = client.post('/v1/infer/global', json={
        'image_id': 'SYNTH_001', 'model_id': 'mock-global', 'modality': 'CFP',
    })
    assert inferred.status_code == 200
    after_ai = client.get('/v1/cases/SYNTH_001').json()
    confirmed = client.post('/v1/cases/SYNTH_001/review', json={
        'revision': after_ai['revision'],
        'action': 'ACCEPT',
        'reviewer': 'Dr Test',
    })
    assert confirmed.status_code == 200
    confirmed_body = confirmed.json()
    assert confirmed_body['grade_status'] == 'CONFIRMED'
    confirmed_grade = confirmed_body['reviewed_grade']

    repeated = client.post('/v1/infer/global', json={
        'image_id': 'SYNTH_001', 'model_id': 'mock-global', 'modality': 'CFP',
    })
    assert repeated.status_code == 200
    preserved = client.get('/v1/cases/SYNTH_001').json()
    assert preserved['grade_status'] == 'CONFIRMED'
    assert preserved['reviewed_grade'] == confirmed_grade
    assert len(preserved['inference_history']) == 2

    stale_request = {
        'invocation_id': 'stale-12345678',
        'capability_id': 'dr_grade',
        'model_id': 'mock-global',
        'model_version': 'synthetic-v1',
        'image_id': 'SYNTH_001',
        'modality': 'CFP',
        'request_case_revision': initial['revision'],
    }
    stale = client.post('/v2/infer/global', json=stale_request)
    assert stale.status_code == 200
    assert stale.json()['status'] == 'STALE_RESULT'
    after_stale = client.get('/v1/cases/SYNTH_001').json()
    assert after_stale['grade_status'] == 'CONFIRMED'
    assert after_stale['reviewed_grade'] == confirmed_grade
    assert len(after_stale['inference_history']) == 3

    duplicate = client.post('/v2/infer/global', json=stale_request)
    assert duplicate.status_code == 200
    assert duplicate.json()['status'] == 'STALE_RESULT'
    assert len(client.get('/v1/cases/SYNTH_001').json()['inference_history']) == 3
