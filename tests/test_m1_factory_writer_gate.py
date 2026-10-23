"""Synthetic app writer coordination; no inference or native entry qualification."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from dr_support.api import _factory as factory
from dr_support.contracts import GlobalResult, InferenceRequest
from dr_support.services.model_gateway import ModelConnection
from dr_support.services.source_mutation_gate import MutationFenced, SourceMutationGate


def _app(tmp_path, monkeypatch, gate=None):
    monkeypatch.delenv('DR_SUPPORT_DEPLOYMENT_PROFILE', raising=False)
    monkeypatch.delenv('REMOTE_MODEL_URL', raising=False)
    monkeypatch.delenv('DR_DEMO_FOLDER', raising=False)
    monkeypatch.setenv('MODEL_RUNTIME', 'remote')
    monkeypatch.setenv('DR_SUPPORT_WORKSPACE_CATALOG', str(tmp_path / 'catalog.sqlite'))
    return factory.create_app(tmp_path / 'fallback.sqlite', include_samples=False,
                              source_mutation_gate=gate)


def _payload(tmp_path, name):
    source = tmp_path / f'{name}-input'
    output = tmp_path / f'{name}-output'
    source.mkdir()
    output.mkdir()
    Image.new('RGB', (192, 128), (40, 80, 50)).save(source / 'synthetic.jpg')
    return {'name': name, 'input_folder': str(source), 'output_folder': str(output),
            'database_path': str(tmp_path / f'{name}.sqlite')}


def _fence(gate):
    # Synthetic control only; no grant, model call or authenticated entry proof.
    return gate.begin_entry(expected_generation=gate.snapshot().generation)


@pytest.mark.parametrize('invalid', ['object', 'subclass', 'quarantined', 'fenced'])
def test_invalid_private_injection_is_rejected_before_database_construction(monkeypatch, invalid):
    class Subclass(SourceMutationGate):
        pass
    gate = {'object': object(), 'subclass': Subclass(),
            'quarantined': SourceMutationGate(quarantined=True), 'fenced': SourceMutationGate()}[invalid]
    if invalid == 'fenced':
        _fence(gate)
    monkeypatch.setattr(factory, '_build_case_store', lambda *a: pytest.fail('Database construction forbidden'))
    with pytest.raises(ValueError, match='open source mutation gate'):
        factory.create_app(source_mutation_gate=gate)


@pytest.mark.parametrize('isolated', ['qa_fixed_session', 'qa_batch_profile'])
def test_mutable_writer_gate_cannot_be_combined_with_frozen_qa(monkeypatch, isolated):
    monkeypatch.setattr(factory, '_build_case_store', lambda *a: pytest.fail('Database construction forbidden'))
    with pytest.raises(ValueError, match='isolated QA sessions'):
        factory.create_app(source_mutation_gate=SourceMutationGate(), **{isolated: object()})


def test_gate_is_bound_to_state_manager_and_store_and_legacy_none_remains_usable(tmp_path, monkeypatch):
    gate = SourceMutationGate()
    app = _app(tmp_path, monkeypatch, gate)
    assert app.state.source_mutation_gate is gate
    assert app.state.workspace_manager.source_mutation_gate is gate
    assert app.state.store.source_mutation_gate is gate
    assert TestClient(app).get('/health').status_code == 200
    legacy = _app(tmp_path, monkeypatch)
    assert legacy.state.source_mutation_gate is None
    assert TestClient(legacy).post('/v1/admissions/scan').status_code == 200


@pytest.mark.parametrize('operation', ['create', 'update', 'open'])
def test_workspace_transition_stays_a_writer_through_the_subsequent_scan(tmp_path, monkeypatch, operation):
    gate = SourceMutationGate()
    app = _app(tmp_path, monkeypatch, gate)
    client = TestClient(app)
    payload = _payload(tmp_path, 'first')
    if operation != 'create':
        seeded = client.post('/v1/workspaces', json=payload)
        assert seeded.status_code == 200
        workspace_id = seeded.json()['workspace']['id']
    if operation == 'update':
        payload = {**payload, 'note': 'Uncommitted physician draft'}
    entered, release = Event(), Event()
    real_scan = app.state.scan_active_workspace

    def scan_gap():
        entered.set()
        assert release.wait(5), 'Controller did not release the synthetic scan barrier'
        return real_scan()

    monkeypatch.setattr(app.state, 'scan_active_workspace', scan_gap)

    def submit():
        if operation == 'create':
            return client.post('/v1/workspaces', json=payload)
        if operation == 'update':
            return client.put(f'/v1/workspaces/{workspace_id}', json=payload)
        return client.post(f'/v1/workspaces/{workspace_id}/open')

    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(submit)
        try:
            assert entered.wait(5), 'Workspace transition did not reach scan'
            snapshot = gate.snapshot()
            assert snapshot.writers > 0 and snapshot.state == 'OPEN'
            with pytest.raises(MutationFenced):
                gate.begin_entry(expected_generation=snapshot.generation)
        finally:
            release.set()
        response = request.result(timeout=5)
    assert response.status_code == 200, response.text
    assert gate.snapshot().writers == 0
    assert app.state.store.source_mutation_gate is gate
    permit = _fence(gate)
    permit._release_after_verified_authority()


@pytest.mark.parametrize('operation', ['create', 'update', 'open', 'delete', 'scan'])
def test_fenced_workspace_operations_leave_catalog_store_and_draft_unchanged(tmp_path, monkeypatch, operation):
    gate = SourceMutationGate()
    app = _app(tmp_path, monkeypatch, gate)
    client = TestClient(app)
    payload = _payload(tmp_path, 'saved')
    created = client.post('/v1/workspaces', json=payload)
    assert created.status_code == 200
    workspace_id = created.json()['workspace']['id']
    draft = {**payload, 'note': 'Keep this unsaved physician draft'}
    before = deepcopy(app.state.workspace_manager.active_payload())
    store = app.state.store
    admissions, images = deepcopy(app.state.admissions), dict(app.state.images)
    permit = _fence(gate)
    if operation == 'create':
        response = client.post('/v1/workspaces', json=draft)
    elif operation == 'update':
        response = client.put(f'/v1/workspaces/{workspace_id}', json=draft)
    elif operation == 'open':
        response = client.post(f'/v1/workspaces/{workspace_id}/open')
    elif operation == 'delete':
        response = client.delete(f'/v1/workspaces/{workspace_id}')
    else:
        response = client.post('/v1/admissions/scan')
    assert response.status_code == 409
    assert 'Keep your unsaved work' in response.json()['detail']
    assert 'SOURCE_' not in response.text
    assert app.state.store is store and app.state.admissions == admissions and app.state.images == images
    assert app.state.workspace_manager.active_payload() == before
    assert draft['note'] == 'Keep this unsaved physician draft'
    permit._release_after_verified_authority()


@pytest.mark.parametrize('path', ['/v1/models', '/v1/capabilities', '/v1/model-connection'])
def test_fenced_provider_refresh_never_probes_or_replaces_state(tmp_path, monkeypatch, path):
    gate = SourceMutationGate()
    app = _app(tmp_path, monkeypatch, gate)
    app.state.model_connection = ModelConnection('Synthetic control', 'http://127.0.0.1:12345')
    before = app.state.providers, app.state.model_connection, app.state.model_connection_probe
    monkeypatch.setattr(factory, 'probe_model_connection', lambda *a, **k: pytest.fail('Probe while fenced'))
    permit = _fence(gate)
    response = TestClient(app).get(path)
    assert response.status_code == 409
    assert (app.state.providers, app.state.model_connection, app.state.model_connection_probe) == before
    permit._release_after_verified_authority()


def test_fenced_model_connection_save_rejects_before_probe_and_preserves_selection(tmp_path, monkeypatch):
    gate = SourceMutationGate()
    app = _app(tmp_path, monkeypatch, gate)
    original = ModelConnection('Saved control', 'http://127.0.0.1:12345')
    app.state.model_connection = original
    providers = app.state.providers
    monkeypatch.setattr(factory, 'probe_model_connection', lambda *a, **k: pytest.fail('Unapproved probe'))
    permit = _fence(gate)
    response = TestClient(app).put('/v1/model-connection', json={
        'name': 'Unsaved draft', 'url': 'http://127.0.0.1:12346'})
    assert response.status_code == 409
    assert app.state.model_connection is original and app.state.providers is providers
    permit._release_after_verified_authority()


def test_fenced_result_saver_preserves_returned_result_and_saved_case(tmp_path, monkeypatch):
    gate = SourceMutationGate()
    app = _app(tmp_path, monkeypatch, gate)
    runtime = app.state.prism_preview.execute.__self__
    request = InferenceRequest(image_id='SYNTH_001', model_id='mock-global', modality='CFP')
    result = GlobalResult(model_id='mock-global', model_version='synthetic-control-v1', modality='CFP',
        state='AI_SUGGESTION', grade=2, probabilities=[0, 0, 1, 0, 0], confidence=1,
        provenance={'image_sha256': 'a' * 64, 'source_type': 'SYNTHETIC',
                    'preprocessing': 'synthetic-control', 'source_revision': 'v1'})
    before, returned = deepcopy(app.state.store.get('SYNTH_001')), result.model_dump()
    permit = _fence(gate)
    with pytest.raises(MutationFenced):
        runtime.save_result(request, 'global', result)
    assert result.model_dump() == returned
    permit._release_after_verified_authority()
    assert app.state.store.get('SYNTH_001') == before


def test_direct_scan_is_guarded_outside_http_and_plain_reads_are_available(tmp_path, monkeypatch):
    gate = SourceMutationGate()
    app = _app(tmp_path, monkeypatch, gate)
    before = deepcopy(app.state.admissions)
    permit = _fence(gate)
    with pytest.raises(MutationFenced):
        app.state.scan_active_workspace()
    assert TestClient(app).get('/v1/workspaces/active').status_code == 200
    assert app.state.admissions == before
    permit._release_after_verified_authority()


def test_inference_admission_repair_is_guarded_before_any_dispatch(tmp_path, monkeypatch):
    gate = SourceMutationGate()
    app = _app(tmp_path, monkeypatch, gate)
    app.state.admissions.pop('SYNTH_001')
    original = app.state.images['SYNTH_001'].data
    monkeypatch.setattr(factory, 'infer_mock', lambda *a: pytest.fail('No inference dispatch permitted'))
    permit = _fence(gate)
    response = TestClient(app).post('/v1/infer/global', json={
        'image_id': 'SYNTH_001', 'model_id': 'mock-global', 'modality': 'CFP'})
    assert response.status_code == 409 and 'Keep your unsaved work' in response.json()['detail']
    assert 'SYNTH_001' not in app.state.admissions
    assert app.state.images['SYNTH_001'].data == original
    permit._release_after_verified_authority()
