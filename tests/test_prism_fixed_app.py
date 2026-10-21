"""Actual app factory/preview/workflow/saver; injected memory storage and fake remote host."""
import builtins
from copy import deepcopy
import itertools
from threading import RLock
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from dr_support.images import BridgeImage
from dr_support.store import new_case
from dr_support.providers.prism_remote_bound import ExplicitHttpChannel, FixedSessionRemoteProvider
from dr_support.services.prism_fixed_session import FixedQASession
from dr_support.services.prism_remote_transport import BoundTransportHost, Principal, TransportError
from dr_support.services.workspaces import WorkspaceDatabaseError
from test_prism_remote_transport import FakeExecutor, png


class MemoryStorage:
    def __init__(self, image, admission):
        self.lock = RLock()
        self.case = new_case(image.image_id)
        self.case.update(image_sha256=image.sha256, source_sha256=image.sha256, admission=deepcopy(admission),
                         resolver_state='RESOLVED', patient_key='synthetic-patient', laterality='LEFT')
        self.puts = 0
    def get(self, key): return deepcopy(self.case)
    def put(self, case): self.case = deepcopy(case); self.puts += 1
    def all_cases(self): return [self.get('fixture_image')]


@pytest.fixture
def app_rig(tmp_path, monkeypatch):
    original_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in {'torch', 'cv2'}: pytest.fail('Real model/CV import forbidden')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    import sqlite3
    import psycopg
    monkeypatch.setattr(sqlite3, 'connect', lambda *a, **k: pytest.fail('SQL forbidden'))
    monkeypatch.setattr(psycopg, 'connect', lambda *a, **k: pytest.fail('SQL forbidden'))
    monkeypatch.setenv('WORKERS', '1'); monkeypatch.setenv('WEB_CONCURRENCY', '1')
    from dr_support.api import _factory
    monkeypatch.setattr(_factory, '_build_case_store', lambda *a, **k: pytest.fail('Persistence construction forbidden'))
    executor, ids = FakeExecutor(), itertools.count()
    def authenticate(headers):
        if headers.get('authorization') == 'Bearer FIXTURE_SERVICE':
            return Principal('fixed-qa-test-service', frozenset({'review-client', 'prepare-source', 'forward-authority'}))
        return None
    host = BoundTransportHost(executor, authenticate=authenticate,
                              issue_id=lambda: f'qa_id_{next(ids):06d}', epoch='qa_epoch_0001')
    lost = {'grant_ack': False}
    calls = []
    def endpoint(request):
        calls.append((request.method, request.url.path))
        status, body = host.handle(request.method, request.url.path, request.headers, request.content)
        if lost['grant_ack'] and request.url.path.endswith('/grant'):
            lost['after_grant'] = True
            raise httpx.ReadError('synthetic lost grant ACK')
        if lost.get('after_grant') and '/jobs/' in request.url.path and request.method == 'GET':
            raise httpx.ReadError('synthetic lost terminal status')
        return httpx.Response(status, json=body)
    channel = ExplicitHttpChannel('https://fixed-qa.invalid', transport=httpx.MockTransport(endpoint),
                                  auth_headers=lambda authority=False: {'Authorization': 'Bearer FIXTURE_SERVICE'})
    provider = FixedSessionRemoteProvider(channel, wait_seconds=.4, poll_seconds=.002)
    provider.negotiate()
    image = BridgeImage('fixture_image', png(Image.new('RGB', (12, 8), (80, 40, 20))), 'SYNTHETIC', 'fixture',
                        modality='UWF', media_type='image/png', source_origin='SYNTHETIC')
    admission = dict(image_id=image.image_id, source_origin='SYNTHETIC', source_sha256=image.sha256,
        integrity_status='OK', retinal_modality='UWF', modality_admission='FUNDUS_ACCEPTED', quality_state='GRADABLE',
        admission_method='MANUAL', admission_reason_code='FIXTURE', created_at='2026-10-21T00:00:00Z')
    storage = MemoryStorage(image, admission)
    session = FixedQASession(tmp_path / 'journal', store=storage, images={image.image_id: image},
        admissions={image.image_id: admission}, provider=provider,
        authenticated_status_reader=lambda fence: channel.request('GET', '/v1/prism-bound/jobs/' + fence['job_id'], epoch=fence['epoch']))
    app = _factory.create_app(include_samples=False, include_demo_fixtures=False, qa_fixed_session=session)
    value = SimpleNamespace(app=app, client=TestClient(app), session=session, storage=storage, executor=executor,
                            host=host, provider=provider, image=image, calls=calls, lost=lost, tmp_path=tmp_path)
    yield value
    for job in host.jobs.values():
        executor.allow_load.set(); executor.allow_entry.set()
        if job.thread: job.thread.join(timeout=2); assert not job.thread.is_alive()
    channel.close(); session.close()


def prepare(rig):
    case = rig.client.get('/v1/cases/fixture_image').json()
    response = rig.client.post('/v1/cases/fixture_image/prism-input-preview', json={'revision': case['revision']})
    assert response.status_code == 200, response.text
    return response.json()


def submit(rig, plan):
    return rig.client.post(f"/v1/cases/fixture_image/prism-input-preview/{plan['plan_id']}/infer", json={
        'revision': plan['case_revision'], 'source_sha256': plan['source_sha256'], 'wire_sha256': plan['wire_sha256'],
        'plan_sha256': plan['plan_sha256'], 'mask_sha256': plan['mask']['sha256'],
        'transform_sha256': plan['transform']['sha256'], 'model_version': plan['model_version']})


def test_actual_factory_preview_register_submit_and_original_saver(app_rig):
    rig = app_rig
    plan = prepare(rig)
    assert rig.executor.prepares == 1 and rig.executor.loads == rig.executor.roi == 0
    assert rig.session._plan[0] == plan['plan_sha256']
    assert rig.client.get(plan['input_preview']['url']).status_code == 200
    response = submit(rig, plan)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'APPLIED'
    assert rig.executor.loads == rig.executor.roi == 1 and rig.executor.prepares == 1
    assert rig.storage.case['inference_history'][-1]['preview_binding']['plan_sha256'] == plan['plan_sha256']
    assert rig.storage.case['lesion']['state'] == 'AI_SUGGESTION'
    assert submit(rig, plan).status_code == 409


@pytest.mark.parametrize('method,path', [
    ('POST', '/v1/admissions/scan'), ('POST', '/v1/workspaces'), ('PUT', '/v1/workspaces/x'),
    ('POST', '/v1/workspaces/x/open'), ('DELETE', '/v1/workspaces/x'),
    ('PUT', '/v1/model-connection'), ('POST', '/v1/model-connection/test'),
    ('POST', '/v1/cases/fixture_image/review'), ('POST', '/v1/cases/fixture_image/admission'),
    ('PUT', '/v1/cases/fixture_image/annotations'), ('POST', '/v1/cases/fixture_image/confirm-image'),
    ('POST', '/v1/infer/global'), ('POST', '/v2/dataset/snapshot'),
    ('GET', '/v1/cases/fixture_image/comparison'), ('GET', '/v1/dataset/export'),
])
def test_actual_app_fixed_session_rejects_mutations_and_uncached_gets(app_rig, method, path):
    before = deepcopy(app_rig.storage.case)
    calls = len(app_rig.calls)
    response = app_rig.client.request(method, path, json={} if method != 'GET' else None)
    assert response.status_code == 423, response.text
    assert app_rig.storage.case == before and len(app_rig.calls) == calls


def test_cached_gets_do_not_hydrate_refresh_or_write(app_rig):
    rig = app_rig
    before = rig.storage.puts
    calls = len(rig.calls)
    for _ in range(2):
        for path in ['/v1/cases', '/v1/cases/fixture_image', '/v1/models', '/v1/capabilities', '/v1/images/fixture_image/display']:
            assert rig.client.get(path).status_code == 200
    assert rig.storage.puts == before and len(rig.calls) == calls
    # Calling the real mutable GET helper directly is also rejected at its
    # admission assignment, rather than silently bypassing middleware policy.
    detail = next(route.endpoint for route in rig.app.routes if getattr(route, 'path', '') == '/v1/cases/{image_id}')
    with pytest.raises(TransportError, match='MUTATION_REJECTED'): detail('fixture_image')
    models = next(route.endpoint for route in rig.app.routes if getattr(route, 'path', '') == '/v1/models')
    models()  # Direct refresh helper returns without contacting the host.
    assert len(rig.calls) == calls and rig.storage.puts == before


def test_direct_store_scan_swap_and_state_replacement_rejected(app_rig):
    rig = app_rig
    with pytest.raises(TransportError): rig.app.state.store.put(rig.storage.case)
    with pytest.raises(HTTPException) as error: rig.app.state.scan_active_workspace()
    assert error.value.status_code == 423
    with pytest.raises(WorkspaceDatabaseError): rig.app.state.workspace_manager._swap_store(object(), object())
    for key in ['store', 'providers', 'workspace_id', 'images', 'admissions']:
        with pytest.raises(TransportError): setattr(rig.app.state, key, object())
        with pytest.raises(TransportError): delattr(rig.app.state, key)
    with pytest.raises(TransportError): rig.app.state.admissions['fixture_image']['integrity_status'] = 'SOURCE_CHANGED'
    with pytest.raises(TransportError): rig.app.state.images.clear()
    with pytest.raises(HTTPException): rig.app.state.infer(None, 'global')


@pytest.mark.parametrize('change', ['revision', 'source', 'integrity'])
def test_backing_drift_before_prepare_sends_no_wire(app_rig, change):
    rig = app_rig
    if change == 'revision': rig.storage.case['revision'] += 1
    elif change == 'source': rig.storage.case['image_sha256'] = 'f' * 64
    else: rig.storage.case['admission']['integrity_status'] = 'SOURCE_CHANGED'
    before = len(rig.calls)
    response = rig.client.post('/v1/cases/fixture_image/prism-input-preview', json={'revision': rig.storage.case['revision']})
    assert response.status_code == 423 and len(rig.calls) == before
    assert rig.executor.prepares == rig.executor.loads == rig.executor.roi == 0


def test_registration_failure_leaves_no_server_plan(app_rig, monkeypatch):
    rig = app_rig
    monkeypatch.setattr(rig.app.state.prism_preview, 'register_plan', lambda *args: (_ for _ in ()).throw(TransportError('FIXTURE_REGISTRATION_FAILURE')))
    revision = rig.storage.case['revision']
    response = rig.client.post('/v1/cases/fixture_image/prism-input-preview', json={'revision': revision})
    assert response.status_code == 409
    assert not rig.app.state.prism_preview.plans and rig.executor.loads == rig.executor.roi == 0


def test_source_changes_during_fake_loading_abort_before_grant(app_rig):
    rig = app_rig
    plan = prepare(rig)
    rig.executor.on_load = lambda: rig.storage.case.update(image_sha256='e' * 64)
    response = submit(rig, plan)
    assert response.status_code == 502
    assert rig.executor.loads == 1 and rig.executor.roi == 0
    assert not any(path.endswith('/grant') for method, path in rig.calls)
    assert not rig.storage.case['inference_history']


def test_lost_grant_ack_quarantines_and_restart_cannot_reopen(app_rig):
    rig = app_rig
    plan = prepare(rig)
    rig.lost['grant_ack'] = True
    response = submit(rig, plan)
    assert response.status_code == 502
    assert rig.session.body['state'] == 'QUARANTINED'
    assert rig.client.get('/v1/cases').status_code == 423
    rig.session.close()
    restarted = FixedQASession(rig.tmp_path / 'journal', store=rig.storage,
        images={'fixture_image': rig.image}, admissions=rig.session.admissions,
        provider=rig.provider, authenticated_status_reader=lambda fence: {})
    try:
        assert restarted.body['state'] == 'QUARANTINED'
        with pytest.raises(TransportError): restarted.bind(rig.app)
        with pytest.raises(TransportError): restarted.recover()
    finally: restarted.close()


def test_original_store_late_saver_preserves_out_of_band_human_edit(app_rig):
    rig = app_rig
    plan = prepare(rig)
    def late_edit():
        rig.storage.case.update(revision=rig.storage.case['revision'] + 1,
                                reviewed_grade=3, human_annotations=[{'synthetic_human': True}])
    rig.executor.after_entry = late_edit
    response = submit(rig, plan)
    assert response.status_code == 200 and response.json()['status'] == 'STALE_RESULT'
    assert rig.storage.case['reviewed_grade'] == 3 and rig.storage.case['human_annotations'] == [{'synthetic_human': True}]
    assert rig.storage.case['lesion'] is None
    assert rig.storage.case['inference_history'][-1]['status'] == 'STALE_RESULT'
    assert rig.client.get('/v1/cases').status_code == 423


def test_fixed_provider_refuses_real_transport_and_profile_stays_disabled():
    from dr_support.services.prism_remote_profile import QUALIFIED, register_isolated_remote_profile
    assert QUALIFIED is False
    with pytest.raises(TransportError, match='MOCK_TRANSPORT_ONLY'):
        FixedSessionRemoteProvider(SimpleNamespace(client=SimpleNamespace(_transport=object())))
    with pytest.raises(RuntimeError): register_isolated_remote_profile()


@pytest.mark.parametrize('digest', [None, '', 'A' * 64, 'f' * 63, 'g' * 64])
def test_invalid_recorded_admission_digest_rejected_before_journal_or_transmission(app_rig, digest):
    rig = app_rig
    admissions = deepcopy(rig.session.admissions)
    admissions['fixture_image']['source_sha256'] = digest
    before = len(rig.calls)
    with pytest.raises(TransportError, match='RECORDED_SOURCE_INVALID'):
        FixedQASession(rig.tmp_path / 'invalid-journal', store=rig.storage,
            images={'fixture_image': rig.image}, admissions=admissions, provider=rig.provider,
            authenticated_status_reader=lambda fence: {})
    assert len(rig.calls) == before and not (rig.tmp_path / 'invalid-journal').exists()


def test_worker_count_change_closes_fixed_session(app_rig, monkeypatch):
    monkeypatch.setenv('WEB_CONCURRENCY', '2')
    assert app_rig.client.get('/v1/cases').status_code == 423
    assert app_rig.executor.loads == app_rig.executor.roi == 0


def test_second_session_cannot_adopt_active_journal_writer(app_rig):
    rig = app_rig
    with pytest.raises(TransportError, match='EXCLUSIVE_WRITER_NOT_ESTABLISHED'):
        FixedQASession(rig.tmp_path / 'journal', store=rig.storage,
            images={'fixture_image': rig.image}, admissions=rig.session.admissions,
            provider=rig.provider, authenticated_status_reader=lambda fence: {})
    assert rig.provider.authority is rig.session
    assert rig.client.get('/v1/cases').status_code == 200


def test_actual_app_writers_remain_excluded_while_forward_fence_held(app_rig):
    rig = app_rig
    plan = prepare(rig)
    observed = []
    def attempt_mutations():
        assert rig.session.body['state'] == 'FENCED'
        with pytest.raises(TransportError):
            rig.app.state.store.put(rig.storage.case)
        observed.append(rig.client.post('/v1/cases/fixture_image/review', json={}).status_code)
        observed.append(rig.client.get('/v1/models').status_code)
    rig.executor.after_gate = attempt_mutations
    response = submit(rig, plan)
    assert response.status_code == 200 and response.json()['status'] == 'APPLIED'
    assert observed == [423, 423]
    assert rig.executor.roi == 1 and rig.session.body['state'] == 'OPEN'
