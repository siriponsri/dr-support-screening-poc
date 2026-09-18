import pytest
from fastapi.testclient import TestClient
from dr_support.api import create_app
from dr_support.contracts import LABELS, GlobalResult


def test_review_roundtrip_persistence_and_stale_write(tmp_path):
    path = tmp_path / 'review.sqlite'
    client = TestClient(create_app(path, include_samples=False))
    base = '/v1/cases/SYNTH_001'
    assert client.post(base+'/review', json={'revision':0,'action':'ACCEPT','reviewer':'Fixture'}).status_code == 409
    result = client.post('/v1/infer/global', json={'image_id':'SYNTH_001','model_id':'mock-global'})
    assert result.status_code == 200
    case = client.get(base).json()
    request = {'revision':case['revision'],'action':'CORRECT_GRADE','reviewer':'Synthetic reviewer','grade':3}
    assert client.post(base+'/review', json=request).json()['reviewed_grade'] == 3
    assert client.post(base+'/review', json=request).status_code == 409
    restored = TestClient(create_app(path, include_samples=False)).get(base).json()
    assert restored['state'] == 'REVIEWED' and restored['reviewed_grade'] == 3
    request.update(revision=restored['revision'],action='MARK_INCORRECT',grade=None)
    result = client.post(base+'/review', json=request).json()
    assert result['state'] == 'NEEDS_CORRECTION' and result['reviewed_grade'] is None


def test_manual_sync_confirmation_invalidation(tmp_path):
    client = TestClient(create_app(tmp_path/'state.sqlite', include_samples=False))
    base = '/v1/cases/SYNTH_001'
    case = client.get(base).json()
    payload = {'revision':0,'image_sha256':case['image_sha256'],
               'label_ids':{label:i for i,label in enumerate(LABELS.values(),1)},
               'annotations':{'version':0,'shapes':[{'id':1,'frame':0,'label_id':1,'type':'rectangle',
                                                    'points':[10,20,30,40],'source':'manual'}]}}
    imported = client.post(base+'/manual-sync',json=payload).json()
    assert imported['lesion_review_state'] == 'IMPORTED_REQUIRES_REVIEW'
    confirmed = client.post(base+'/review', json={'revision':imported['revision'],
                         'action':'CONFIRM_ANNOTATIONS','reviewer':'Fixture'}).json()
    assert confirmed['lesion_review_state'] == 'REVIEWED'
    payload['revision'] = confirmed['revision']
    payload['annotations']['shapes'][0]['points'] = [10,20,50,60]
    changed = client.post(base+'/manual-sync',json=payload).json()
    assert changed['lesion_review_state'] == 'IMPORTED_REQUIRES_REVIEW'
    assert changed['annotation_hash'] != changed['confirmed_annotation_hash']
    payload['revision']=changed['revision'];payload['image_sha256']='0'*64
    assert client.post(base+'/manual-sync',json=payload).status_code == 422


def test_cross_origin_and_missing_token_fail_honestly(tmp_path,monkeypatch):
    monkeypatch.delenv('CVAT_TOKEN',raising=False)
    client=TestClient(create_app(tmp_path/'state.sqlite',include_samples=False))
    assert client.post('/v1/infer/global',json={'image_id':'SYNTH_001','model_id':'mock-global'},
                       headers={'Origin':'https://unrelated.invalid'}).status_code == 403
    client.post('/v1/infer/lesion-roi',json={'image_id':'SYNTH_001','model_id':'mock-lesion'})
    response=client.post('/v1/cases/SYNTH_001/cvat/send',json={})
    assert response.status_code == 503 and 'OWNER_ACTION_REQUIRED' in response.json()['detail']
    assert client.get('/v1/cases/SYNTH_001').json()['cvat'] is None


def test_invalid_grade_and_manual_geometry(tmp_path):
    client=TestClient(create_app(tmp_path/'state.sqlite',include_samples=False))
    base='/v1/cases/SYNTH_001'
    assert client.post(base+'/review',json={'revision':0,'action':'CORRECT_GRADE',
                                          'reviewer':'Fixture','grade':5}).status_code == 422
    image=client.get(base).json()
    for points in [[], ['bad',0,20,30], [-1,0,20,30]]:
        data={'revision':0,'image_sha256':image['image_sha256'],
              'label_ids':{label:i for i,label in enumerate(LABELS.values(),1)},
              'annotations':{'shapes':[{'frame':0,'type':'rectangle','label_id':1,'points':points}]}}
        assert client.post(base+'/manual-sync',json=data).status_code == 422


def test_global_probability_validation():
    data={'model_id':'fixture','model_version':'v1','modality':'CFP','state':'AI_SUGGESTION','grade':2,
          'probabilities':[.5,.1,.2,.1,.1],'confidence':.2,
          'provenance':{'image_sha256':'a'*64,'source_type':'SYNTHETIC','preprocessing':'none','source_revision':'v1'}}
    with pytest.raises(ValueError):
        GlobalResult.model_validate(data)


def test_public_samples_are_verified_and_mock_rejected(tmp_path):
    from dr_support.images import BridgeImage, synthetic_image
    app=create_app(tmp_path/'state.sqlite',include_samples=False)
    fixture=synthetic_image()
    app.state.images['PUBLIC_FIXTURE']=BridgeImage('PUBLIC_FIXTURE',fixture.data,'PUBLIC','test source')
    client=TestClient(app)
    assert client.post('/v1/infer/global',json={'image_id':'PUBLIC_FIXTURE','model_id':'mock-global'}).status_code==422
    assert client.get('/v1/cases/PUBLIC_FIXTURE').json()['global'] is None


def test_reject_wrong_sample_bytes(tmp_path):
    import json
    from dr_support.images import admitted_samples
    (tmp_path/'docs').mkdir(); (tmp_path/'local-state/bridge/samples').mkdir(parents=True)
    (tmp_path/'docs/SAMPLE_MANIFEST.json').write_text(json.dumps([{
        'filename':'01_dr.jpg','image_id':'01_dr','sha256':'0'*64,'source':'test'}]),encoding='utf-8')
    (tmp_path/'local-state/bridge/samples/01_dr.jpg').write_bytes(b'changed bytes')
    with pytest.raises(RuntimeError,match='hash mismatch'):
        admitted_samples(tmp_path)


def test_manual_grade_is_explicit_and_mark_incorrect_requires_ai(tmp_path):
    client = TestClient(create_app(tmp_path/'state.sqlite', include_samples=False))
    base = '/v1/cases/SYNTH_001'
    assert client.post(base+'/review', json={'revision':0,'action':'MARK_INCORRECT','reviewer':'Fixture'}).status_code == 409
    manual = client.post(base+'/review', json={'revision':0,'action':'CORRECT_GRADE','reviewer':'Fixture','grade':1}).json()
    assert manual['state'] == 'REVIEWED'
    assert manual['reviewed_grade'] == 1
    assert manual['grade_review_source'] == 'MANUAL'
    result = client.post('/v1/infer/global', json={'image_id':'SYNTH_001','model_id':'mock-global'}).json()
    after = client.get(base).json()
    assert result['grade'] == 2
    assert after['reviewed_grade'] is None and after['grade_review_source'] is None
