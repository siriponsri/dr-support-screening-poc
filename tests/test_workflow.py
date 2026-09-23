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


def test_confirm_image_is_one_audited_context_milestone(tmp_path):
    client = TestClient(create_app(tmp_path/'state.sqlite', include_samples=False))
    base = '/v1/cases/SYNTH_001'
    case = client.get(base).json()
    response = client.post(base + '/confirm-image', json={
        'revision': case['revision'],
        'reviewer': 'Image reviewer',
        'patient_key': 'PAT0007',
        'laterality': 'RIGHT',
        'note': 'Context checked against the synthetic worklist record.',
    })
    assert response.status_code == 200
    body = response.json()
    assert body['patient_key'] == 'PAT0007'
    assert body['laterality'] == 'RIGHT'
    assert body['admission']['reviewed_by'] == 'Image reviewer'
    assert body['admission']['reviewed_at']
    assert body['events'][-1]['action'] == 'CONFIRM_IMAGE'
    assert body['events'][-1]['identity_assurance'] == 'LOCAL_POC_SELF_DECLARED'


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
    (tmp_path/'docs/SAMPLE_SOURCE_MANIFEST.json').write_text(json.dumps([{
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


def test_human_annotations_and_clinician_review_roundtrip(tmp_path):
    path = tmp_path / 'state.sqlite'
    client = TestClient(create_app(path, include_samples=False))
    base = '/v1/cases/SYNTH_001'
    initial = client.get(base).json()
    payload = {
        'revision': initial['revision'],
        'reviewer': 'Demo clinician',
        'annotations': [
            {'type': 'rectangle', 'label': 'MICROANEURYSM',
             'geometry': {'x': 10, 'y': 20, 'width': 30, 'height': 25}, 'locked': False},
            {'type': 'polygon', 'label': 'HEMORRHAGE',
             'geometry': {'points': [[50, 50], [80, 50], [70, 90]]}},
            {'type': 'point', 'label': 'HARD_EXUDATE', 'geometry': {'x': 100, 'y': 120}},
            {'type': 'circle', 'label': 'SOFT_EXUDATE',
             'geometry': {'cx': 160, 'cy': 140, 'radius': 12}},
        ],
    }
    saved = client.put(base + '/annotations', json=payload)
    assert saved.status_code == 200
    body = saved.json()
    assert len(body['human_annotations']) == 4
    assert {shape['source'] for shape in body['human_annotations']} == {'HUMAN'}
    assert body['human_annotations'][0]['geometry']['x'] == 10.0
    assert body['human_annotations'][0]['locked'] is False
    assert all(shape['locked'] is True for shape in body['human_annotations'][1:])
    assert client.put(base + '/annotations', json=payload).status_code == 409

    restored = TestClient(create_app(path, include_samples=False)).get(base).json()
    assert len(restored['human_annotations']) == 4
    review = client.post(base + '/review', json={
        'revision': restored['revision'],
        'action': 'CORRECT_GRADE',
        'reviewer': 'Demo clinician',
        'grade': 2,
        'comment': 'Human review completed for demo.',
    })
    assert review.status_code == 200
    reviewed = review.json()
    assert reviewed['clinician_review']['final_grade'] == 2
    assert reviewed['clinician_review']['remark'] == 'Human review completed for demo.'
    assert reviewed['review_history'][-1]['review_action'] == 'CORRECT_GRADE'


def test_review_evidence_keeps_ai_scores_and_human_provenance_separate(tmp_path):
    client = TestClient(create_app(tmp_path / 'state.sqlite', include_samples=False))
    base = '/v1/cases/SYNTH_001'
    assert client.post('/v1/infer/lesion-roi', json={
        'image_id': 'SYNTH_001', 'model_id': 'mock-lesion',
    }).status_code == 200

    initial = client.get(base).json()
    evidence = initial['review_evidence']
    ai_item = next(item for item in evidence['items'] if item['source'] == 'AI')
    original_score = initial['lesion']['lesions'][0]['score']
    assert ai_item['status'] == 'AI_SUGGESTED'
    assert ai_item['score'] == original_score
    assert evidence['unresolved_count'] == 1

    confirmed = client.post(base + '/lesion-review', json={
        'revision': initial['revision'],
        'reviewer': 'Evidence clinician',
        'detection_id': ai_item['annotation_id'],
        'action': 'CONFIRM',
    })
    assert confirmed.status_code == 200
    confirmed_body = confirmed.json()
    assert confirmed_body['review_evidence']['summary']['confirmed'] == 1
    assert confirmed_body['lesion']['lesions'][0]['score'] == original_score

    corrected = client.post(base + '/lesion-review', json={
        'revision': confirmed_body['revision'],
        'reviewer': 'Evidence clinician',
        'detection_id': ai_item['annotation_id'],
        'action': 'CORRECT',
        'label': 'HEMORRHAGE',
        'rectangle': [250, 160, 270, 180],
    })
    assert corrected.status_code == 200
    corrected_body = corrected.json()
    assert corrected_body['review_evidence']['summary']['corrected'] == 1
    assert corrected_body['review_evidence']['items'][0]['original_score'] == original_score
    assert corrected_body['lesion']['lesions'][0]['canonical_label'] == 'MICROANEURYSM'
    assert corrected_body['lesion']['lesions'][0]['score'] == original_score

    annotation = client.put(base + '/annotations', json={
        'revision': corrected_body['revision'],
        'reviewer': 'Evidence clinician',
        'annotations': [{
            'type': 'rectangle', 'label': 'SOFT_EXUDATE',
            'geometry': {'x': 20, 'y': 20, 'width': 10, 'height': 10},
        }],
    })
    assert annotation.status_code == 200
    body = annotation.json()
    assert body['review_evidence']['summary']['added'] == 1
    assert body['human_annotations'][0]['source'] == 'HUMAN'


def test_clinician_signoff_does_not_require_ai_lesion_actions(tmp_path):
    client = TestClient(create_app(tmp_path / 'state.sqlite', include_samples=False))
    base = '/v1/cases/SYNTH_001'
    assert client.post('/v1/infer/global', json={
        'image_id': 'SYNTH_001', 'model_id': 'mock-global',
    }).status_code == 200
    assert client.post('/v1/infer/lesion-roi', json={
        'image_id': 'SYNTH_001', 'model_id': 'mock-lesion',
    }).status_code == 200

    initial = client.get(base).json()
    assert initial['review_evidence']['unresolved_count'] == 1
    saved = client.post(base + '/review', json={
        'revision': initial['revision'],
        'action': 'ACCEPT',
        'reviewer': 'Signoff clinician',
    })

    assert saved.status_code == 200
    assert saved.json()['clinician_review']['review_action'] == 'ACCEPT'
    assert saved.json()['review_evidence']['unresolved_count'] == 1
