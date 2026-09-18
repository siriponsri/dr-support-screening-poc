import pytest
from fastapi.testclient import TestClient
from dr_support.contracts import GlobalResult, Lesion
from dr_support.api import create_app


def test_gateway_contracts():
    client = TestClient(create_app())
    assert client.get('/health').status_code == 200
    assert len(client.get('/v1/models').json()) >= 2
    response = client.post('/v1/infer/global', json={'image_id': 'SYNTH_001', 'model_id': 'mock-global'})
    assert response.status_code == 200
    result = GlobalResult.model_validate(response.json())
    assert result.grade == 2 and 'SYNTHETIC' in result.warnings[0]
    assert client.post('/v1/infer/global', json={'image_id': 'PRIVATE', 'model_id': 'mock-global'}).status_code == 404
    assert client.post('/v1/infer/global', json={'image_id': 'SYNTH_001', 'model_id': 'missing'}).status_code == 404
    assert client.post('/v1/infer/global', json={'image_id': 'SYNTH_001', 'model_id': 'mock-global',
                                              'modality': 'UWF'}).status_code == 422
    assert client.post('/v1/infer/lesion-roi', json={'image_id': 'SYNTH_001', 'model_id': 'mock-lesion'}).status_code == 200


def test_reject_geometry_and_wrong_mapping():
    with pytest.raises(ValueError):
        Lesion(source_label='MA', canonical_label='HEMORRHAGE', rectangle=(0, 0, 3, 4), score=.5)
    with pytest.raises(ValueError):
        Lesion(source_label='MA', canonical_label='MICROANEURYSM', rectangle=(3, 0, 1, 4), score=.5)


def test_online_secret_and_redirect_safety(monkeypatch):
    import httpx
    from dr_support.cvat import CVATOnline, OnlineError
    monkeypatch.delenv('CVAT_TOKEN', raising=False)
    with pytest.raises(OnlineError, match='OWNER_ACTION_REQUIRED'):
        CVATOnline().inspect()
    monkeypatch.setenv('CVAT_TOKEN', 'synthetic-test-secret')
    calls = []
    def handle(request):
        calls.append(request)
        assert request.headers['Authorization'] == 'Bearer synthetic-test-secret'
        return httpx.Response(302, headers={'Location': 'https://other.invalid'})
    with pytest.raises(OnlineError, match='302') as error:
        CVATOnline(httpx.MockTransport(handle)).inspect()
    assert 'synthetic-test-secret' not in str(error.value) and len(calls) == 1


def test_online_conversion_and_scope(monkeypatch):
    import httpx
    from dr_support.cvat import CVATOnline, OnlineError, rectangles, reviewed_shapes
    from dr_support.contracts import LesionResult
    client = TestClient(create_app())
    prediction = LesionResult.model_validate(client.post('/v1/infer/lesion-roi', json={
        'image_id': 'SYNTH_001', 'model_id': 'mock-lesion'}).json())
    payload = rectangles(prediction, {'MICROANEURYSM': 42})
    assert payload['shapes'][0]['points'] == [250, 160, 264, 176]
    assert reviewed_shapes(payload, {'MICROANEURYSM': 42}, 640, 480)[0]['state'] == 'IMPORTED_REQUIRES_REVIEW'
    monkeypatch.setenv('CVAT_TOKEN', 'fixture')
    remote = CVATOnline(httpx.MockTransport(lambda r: httpx.Response(200, json={'project_id': 123})))
    with pytest.raises(OnlineError, match='outside'):
        remote.push(99, payload)


def test_weight_hash_and_unavailable_model(tmp_path, monkeypatch):
    from dr_support.providers.assets import verify_weight
    p = tmp_path / 'weight'; p.write_bytes(b'corrupt')
    with pytest.raises(RuntimeError, match='SHA256'):
        verify_weight(p, '0' * 64)
    monkeypatch.delenv('RETFOUND_SOURCE', raising=False)
    model = create_app().state.providers['retfound-aptos5']
    assert model.metadata()['status'] == 'ASSET_REQUIRED'


def test_review_filter_preserves_raw_output(monkeypatch):
    from dr_support.contracts import LesionResult, Provenance
    from dr_support.presentation import lesion_review_view
    lesions = [
        Lesion(source_label='MA', canonical_label='MICROANEURYSM', rectangle=(1,1,2,2), score=.95),
        Lesion(source_label='MA', canonical_label='MICROANEURYSM', rectangle=(3,3,4,4), score=.85),
        Lesion(source_label='MA', canonical_label='MICROANEURYSM', rectangle=(5,5,6,6), score=.60),
        Lesion(source_label='HE', canonical_label='HEMORRHAGE', rectangle=(7,7,8,8), score=.90),
    ]
    raw = LesionResult(model_id='fixture', model_version='v1', modality='CFP', width=20, height=20,
        lesions=lesions, provenance=Provenance(image_sha256='a'*64, source_type='SYNTHETIC',
        preprocessing='none', source_revision='v1')).model_dump(mode='json')
    monkeypatch.setenv('REVIEW_THRESHOLDS', '{"MA":0.8}')
    monkeypatch.setenv('REVIEW_MAX_PER_CLASS', '1')
    monkeypatch.setenv('REVIEW_MAX_TOTAL', '2')
    view = lesion_review_view(raw)
    assert len(raw['lesions']) == 4  # raw inference remains intact
    assert view['raw_count'] == 4 and view['suggestion_count'] == 2 and view['filtered_count'] == 2
    assert [x['source_label'] for x in view['lesions']] == ['MA', 'HE']
    assert view['policy']['thresholds'] == {'MA': .8}


def test_mask_sync_fails_explicitly():
    from dr_support.cvat import reviewed_shapes
    payload = {'shapes':[{'id':1,'frame':0,'label_id':42,'type':'mask','points':[1,2,3,4]}]}
    with pytest.raises(ValueError, match='Mask sync is not supported'):
        reviewed_shapes(payload, {'MICROANEURYSM':42}, 100, 100)
