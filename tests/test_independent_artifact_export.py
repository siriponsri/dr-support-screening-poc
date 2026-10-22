import pytest
from test_artifact_roi_assist import fixture as fixture, client, BASE
from dr_support.services import artifact_roi_assist as module

@pytest.mark.parametrize('change',['recorded_hash_conflict','source_changed'])
def test_export_retains_all_for_same_source_conflicts_as_live_view(fixture,change):  # noqa: F811
    app,case,image,provider=fixture
    response=client(fixture).post(BASE+'/prepare',json={'revision':0})
    assert response.status_code==200
    stored=app.state.store.get(case['image_id'])
    if change=='recorded_hash_conflict':stored['image_sha256']='b'*64
    else:stored['admission']['integrity_status']='SOURCE_CHANGED'
    live=module.project(stored,image,provider,scope=module.scope_for_app(app,app.state.store))
    assert live['suppressed_ids']==[]
    exported=module.export_rows([stored])[0]['state']
    assert exported['status']=='STALE_RETAIN_ALL'
    assert exported['suppressed_ids']==[]

def test_actual_snapshot_sidecar_rejects_recorded_hash_conflict(fixture,tmp_path):  # noqa: F811
    import json
    from test_artifact_roi_assist import export_workspace
    c,output=export_workspace(fixture,tmp_path)
    assert c.post(BASE+'/prepare',json={'revision':0}).status_code==200
    app,case,_,_=fixture
    stored=app.state.store.get(case['image_id']);stored['image_sha256']='b'*64;app.state.store.put(stored)
    assert c.get('/v1/cases/SYNTH_001').json()['artifact_roi_assist']['suppressed_ids']==[]
    response=c.post('/v2/dataset/snapshot');assert response.status_code==200,response.text
    state=json.loads((output/response.json()['directory_name']/'artifact_roi_assist.json').read_bytes())['cases'][0]['state']
    assert state['status']=='STALE_RETAIN_ALL' and state['suppressed_ids']==[]
