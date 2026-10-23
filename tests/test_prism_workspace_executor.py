"""Exact native adapter with synthetic model ports; never live inference proof."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import base64
import itertools
import json
from types import SimpleNamespace

import pytest

from dr_support.providers.prism_bound import BoundLocalPRISM, BoundPlanError
from dr_support.services import prism_preview
from dr_support.services.prism_owned_runtime import LoadedPrismExecutor, child_application
from dr_support.services.prism_remote_transport import BASE, TransportError, canonical, sha
from dr_support.services.prism_workspace_executor import (
    LoadedWorkspacePrismExecutor, workspace_child_application,
)
from test_prism_bound_adapter import forbid_real_runtime, rig as _native_rig

# Imported fixture forbids Torch/CV2, sockets, SQLite and PostgreSQL.
assert forbid_real_runtime


@contextmanager
def fake_guard():
    yield SimpleNamespace(forward_attempts=0)


@pytest.fixture
def rig(monkeypatch):
    for key in ('MODEL_HOSPITAL_SCOPE', 'MODEL_ALLOW_AUTHORIZED_HOSPITAL', 'REMOTE_MODEL_TOKEN'):
        monkeypatch.delenv(key, raising=False)
    value = _native_rig.__wrapped__(monkeypatch, prism_preview)
    value.provider.loaded = False
    value.provider._loaded_identity = None
    value.calls['load'] = 0
    value.calls['prepare_images'] = []
    native_prepare = value.provider.prepare_prism_preview_candidate

    def prepare(image):
        value.calls['prepare_images'].append(image)
        return native_prepare(image)

    def load():
        value.calls['load'] += 1
        value.provider.device = 'cpu'
        value.provider.loaded = True
        value.provider._loaded_identity = deepcopy(value.pins)

    monkeypatch.setattr(value.provider, 'prepare_prism_preview_candidate', prepare)
    monkeypatch.setattr(value.provider, 'load', load)
    value.executor = LoadedWorkspacePrismExecutor(value.provider, expected_pins=value.pins, load_guard=fake_guard)
    return value


def load(rig):
    rig.executor.load_until(rig.executor.clock() + 10, lambda: False)


def plan(rig, *, modality='UWF', origin='SYNTHETIC'):
    image = replace(rig.wire, modality=modality, source_type=origin, source_origin=origin)
    candidate = rig.executor.prepare(image.data, image.modality)
    binding, mask = rig.prepare(image)
    assert mask == candidate['mask_png']
    binding['admission']['source_origin'] = origin
    refresh_admission(binding)
    return binding, mask


def refresh_admission(binding):
    binding['admission_sha256'] = sha(canonical(binding['admission']))
    binding['recorded_source_identity']['admission_sha256'] = binding['admission_sha256']
    binding['recorded_source_identity']['source_origin'] = binding['admission']['source_origin']


def execute(rig, binding, mask, *, before=None, entry=None, wire=None):
    return rig.executor.execute(rig.wire.data if wire is None else wire, mask, binding, sha(canonical(binding)),
                                before_forward=before or (lambda: None), on_roi_entry=entry or (lambda: None))


@pytest.mark.parametrize('modality', ['CFP', 'UWF'])
@pytest.mark.parametrize('origin', ['PUBLIC', 'SYNTHETIC', 'HOSPITAL_AUTHORIZED'])
def test_exact_native_loop_preserves_wire_modality_origin_and_mask(rig, monkeypatch, modality, origin):
    if origin == 'HOSPITAL_AUTHORIZED':
        monkeypatch.setenv('MODEL_HOSPITAL_SCOPE', 'PRIVATE_PROJECT_EVALUATION')
        monkeypatch.setenv('MODEL_ALLOW_AUTHORIZED_HOSPITAL', '1')
        monkeypatch.setenv('REMOTE_MODEL_TOKEN', 'synthetic-test-token-not-a-credential')
    load(rig)
    load(rig)
    binding, mask = plan(rig, modality=modality, origin=origin)
    prepared = rig.calls['prepare_images'][0]
    assert prepared.source_type == prepared.source_origin == 'UNKNOWN'
    assert prepared.data is rig.wire.data and prepared.modality == modality
    if modality == 'CFP':
        assert mask is None and binding['external_fov_status'] == 'NOT_APPLICABLE'
        assert rig.calls['detect'] == 0
    seen = []
    native = rig.provider.infer_remote_fenced_prism

    def capture(request, image, **kwargs):
        seen.append(image)
        assert rig.executor.loaded and rig.calls['load'] == 1
        assert kwargs.get('demo_authorization') is None
        return native(request, image, **kwargs)

    monkeypatch.setattr(rig.provider, 'infer_remote_fenced_prism', capture)
    hooks = []
    returned = execute(rig, binding, mask, before=lambda: hooks.append('source'), entry=lambda: hooks.append('native'))
    assert hooks == ['source', 'native']
    assert seen[0].data is rig.wire.data
    assert seen[0].source_type == seen[0].source_origin == origin
    assert seen[0].modality == returned['result']['modality'] == modality
    assert returned['result']['provenance']['source_type'] == origin
    assert returned['preview_receipt']['wire_sha256'] == rig.wire.sha256
    assert returned['preview_receipt']['mask_sha256'] == binding['mask_sha256']
    assert rig.calls['load'] == rig.executor.load_attempts == rig.calls['roi'] == 1
    assert rig.calls['fold'] == 5


@pytest.mark.parametrize('origin', ['UNKNOWN', 'WORKSPACE', 'PRIVATE', 'HOSPITAL_AUTHORIZED'])
def test_unapproved_origin_never_enters_native_or_source_hook(rig, origin):
    load(rig)
    binding, mask = plan(rig, origin=origin)
    with pytest.raises(TransportError, match='SOURCE_OR_ADMISSION'):
        execute(rig, binding, mask, before=lambda: pytest.fail('no source grant'))
    assert rig.calls['roi'] == rig.calls['fold'] == 0 and rig.executor.poisoned


@pytest.mark.parametrize('field,value', [
    ('quality_state', 'NOT_EVALUATED'), ('quality_state', 'UNGRADABLE'),
    ('modality_admission', 'NEEDS_REVIEW'), ('modality_admission', 'NOT_RETINAL'),
    ('retinal_modality', 'CFP'),
])
def test_ordinary_admission_cannot_use_technical_exception(rig, field, value):
    load(rig)
    binding, mask = plan(rig)
    binding['admission'][field] = value
    refresh_admission(binding)
    with pytest.raises(TransportError, match='SOURCE_OR_ADMISSION'):
        execute(rig, binding, mask)
    assert rig.calls['roi'] == rig.calls['fold'] == 0


@pytest.mark.parametrize('missing', ['MODEL_HOSPITAL_SCOPE', 'MODEL_ALLOW_AUTHORIZED_HOSPITAL', 'REMOTE_MODEL_TOKEN'])
def test_hospital_requires_all_existing_server_policy_inputs(rig, monkeypatch, missing):
    for key, value in {'MODEL_HOSPITAL_SCOPE': 'PRIVATE_PROJECT_EVALUATION',
                       'MODEL_ALLOW_AUTHORIZED_HOSPITAL': '1',
                       'REMOTE_MODEL_TOKEN': 'synthetic-test-token-not-a-credential'}.items():
        monkeypatch.setenv(key, value)
    load(rig)
    binding, mask = plan(rig, origin='HOSPITAL_AUTHORIZED')
    monkeypatch.delenv(missing)
    with pytest.raises(TransportError, match='SOURCE_OR_ADMISSION'):
        execute(rig, binding, mask)
    assert rig.calls['roi'] == 0


@pytest.mark.parametrize('modality', ['UNKNOWN', 'OCT', '', None])
def test_prepare_rejects_nonfundus_modalities_without_detector(rig, modality):
    load(rig)
    with pytest.raises(TransportError, match='FUNDUS_MODALITY'):
        rig.executor.prepare(rig.wire.data, modality)
    assert rig.calls['detect'] == rig.calls['roi'] == 0


def test_prepare_requires_loaded_identity_and_immutable_wire(rig):
    with pytest.raises(TransportError, match='NOT_LOADED'):
        rig.executor.prepare(rig.wire.data, 'UWF')
    load(rig)
    with pytest.raises(TransportError, match='IMMUTABLE_WIRE'):
        rig.executor.prepare(bytearray(rig.wire.data), 'UWF')
    assert rig.calls['detect'] == rig.calls['roi'] == 0


@pytest.mark.parametrize('change', ['wire', 'plan_hash', 'recorded_source', 'pins', 'transform', 'mask'])
def test_frozen_native_validation_still_blocks_changes_before_entry(rig, change):
    load(rig)
    binding, mask = plan(rig)
    wire, digest = rig.wire.data, None
    if change == 'wire':
        wire += b'changed'
    elif change == 'plan_hash':
        digest = 'a' * 64
    elif change == 'recorded_source':
        binding['recorded_source_identity']['case_source_sha256'] = 'a' * 64
    elif change == 'pins':
        binding['model_pins']['config_sha256'] = 'a' * 64
    elif change == 'transform':
        binding['transform']['original_width'] += 1
    elif change == 'mask':
        mask = None
    with pytest.raises((TransportError, BoundPlanError)):
        rig.executor.execute(wire, mask, binding, digest or sha(canonical(binding)),
                             before_forward=lambda: pytest.fail('no source hook'),
                             on_roi_entry=lambda: pytest.fail('no native entry'))
    assert rig.calls['roi'] == rig.calls['fold'] == 0 and rig.executor.poisoned


def test_native_replay_remains_consumed_and_worker_never_retries(rig):
    load(rig)
    binding, mask = plan(rig)
    execute(rig, binding, mask)
    with pytest.raises(BoundPlanError, match='REPLAY'):
        execute(rig, binding, mask)
    with pytest.raises(TransportError, match='IDENTITY_CHANGED'):
        execute(rig, binding, mask)
    assert rig.calls['roi'] == 1 and rig.calls['load'] == 1 and rig.executor.poisoned


@pytest.mark.parametrize('hook', ['source', 'entry'])
def test_fatal_hooks_cannot_be_swallowed_as_roi_fallback(rig, hook):
    load(rig)
    binding, mask = plan(rig)

    def fail():
        raise RuntimeError('synthetic fatal authority failure')

    with pytest.raises(RuntimeError, match='fatal authority'):
        execute(rig, binding, mask, before=fail if hook == 'source' else None,
                entry=fail if hook == 'entry' else None)
    assert rig.calls['roi'] == rig.calls['fold'] == 0 and rig.executor.poisoned
    with pytest.raises(TransportError):
        execute(rig, binding, mask)
    assert rig.calls['load'] == 1


@pytest.mark.parametrize('modality', ['CFP', 'UWF'])
def test_recoverable_roi_failure_preserves_native_fallback_not_wrapper_retry(rig, modality):
    load(rig)
    binding, mask = plan(rig, modality=modality)
    rig.calls['roi_fail'] = True
    returned = execute(rig, binding, mask)
    processing = returned['processing_evidence']
    assert processing['native_roi_status'] == 'FAILED'
    assert processing['processing_mode'] == ('FALLBACK' if modality == 'UWF' else 'LEGACY')
    assert not processing['fov_used_for_model_input']
    assert rig.calls['roi'] == 1 and rig.calls['fold'] == 5 and not rig.executor.poisoned


def test_model_identity_change_between_source_grant_and_native_entry_is_fatal(rig):
    load(rig)
    binding, mask = plan(rig)
    with pytest.raises(TransportError, match='IDENTITY_CHANGED'):
        execute(rig, binding, mask, before=lambda: rig.pins.update(config_sha256='a' * 64))
    assert rig.calls['roi'] == rig.calls['fold'] == 0 and rig.executor.poisoned


def test_native_source_policy_revoked_after_grant_blocks_before_roi(rig, monkeypatch):
    monkeypatch.setenv('MODEL_HOSPITAL_SCOPE', 'PRIVATE_PROJECT_EVALUATION')
    monkeypatch.setenv('MODEL_ALLOW_AUTHORIZED_HOSPITAL', '1')
    monkeypatch.setenv('REMOTE_MODEL_TOKEN', 'synthetic-test-token-not-a-credential')
    load(rig)
    binding, mask = plan(rig, origin='HOSPITAL_AUTHORIZED')
    with pytest.raises(ValueError, match='source origin is blocked'):
        execute(rig, binding, mask, before=lambda: monkeypatch.delenv('MODEL_ALLOW_AUTHORIZED_HOSPITAL'))
    assert rig.calls['roi'] == rig.calls['fold'] == 0


def test_wrapper_source_policy_rechecked_at_exact_fatal_entry(rig, monkeypatch):
    monkeypatch.setenv('MODEL_HOSPITAL_SCOPE', 'PRIVATE_PROJECT_EVALUATION')
    monkeypatch.setenv('MODEL_ALLOW_AUTHORIZED_HOSPITAL', '1')
    monkeypatch.setenv('REMOTE_MODEL_TOKEN', 'synthetic-test-token-not-a-credential')
    load(rig)
    binding, mask = plan(rig, origin='HOSPITAL_AUTHORIZED')
    native = rig.provider._infer_loaded

    def revoke_at_entry(request, image, *, _frozen_preparation, _fatal_roi_entry):
        def revoke():
            monkeypatch.delenv('MODEL_ALLOW_AUTHORIZED_HOSPITAL')
            _fatal_roi_entry()
        return native(request, image, _frozen_preparation=_frozen_preparation, _fatal_roi_entry=revoke)

    monkeypatch.setattr(rig.provider, '_infer_loaded', revoke_at_entry)
    with pytest.raises(TransportError, match='SOURCE_OR_ADMISSION'):
        execute(rig, binding, mask)
    assert rig.calls['roi'] == rig.calls['fold'] == 0


@pytest.mark.parametrize('kind', ['duck', 'subclass', 'batch', 'loaded', 'identity_loaded'])
def test_only_fresh_exact_ordinary_bound_provider_is_accepted(rig, kind):
    provider = rig.provider
    if kind == 'duck':
        provider = SimpleNamespace()
    elif kind == 'subclass':
        class OtherProvider(BoundLocalPRISM):
            pass
        provider = OtherProvider()
    elif kind == 'batch':
        provider._batch_authorization = object()
    elif kind == 'loaded':
        provider.loaded = True
    else:
        provider._loaded_identity = deepcopy(rig.pins)
    with pytest.raises(TransportError, match='PROVIDER_REQUIRED'):
        LoadedWorkspacePrismExecutor(provider, expected_pins=rig.pins, load_guard=fake_guard)
    assert rig.calls['load'] == rig.calls['roi'] == 0


@pytest.mark.parametrize('kind', ['swap', 'batch', 'demo'])
def test_in_place_authority_or_provider_replacement_is_refused(rig, kind):
    load(rig)
    binding, mask = plan(rig)
    if kind == 'swap':
        rig.executor.provider = BoundLocalPRISM()
    elif kind == 'batch':
        rig.provider._batch_authorization = object()
    else:
        rig.executor.demo_authorization = object()
    with pytest.raises(TransportError, match='ORDINARY_BOUND_PROVIDER'):
        execute(rig, binding, mask)
    assert rig.calls['roi'] == 0 and rig.executor.poisoned


def test_failed_load_is_poisoned_and_cannot_load_twice(rig, monkeypatch):
    attempts = []

    def fail():
        attempts.append(True)
        raise RuntimeError('synthetic load failure')

    monkeypatch.setattr(rig.provider, 'load', fail)
    with pytest.raises(RuntimeError, match='load failure'):
        load(rig)
    with pytest.raises(TransportError):
        load(rig)
    assert attempts == [True] and rig.executor.poisoned and rig.calls['roi'] == 0


def test_inherited_guard_detects_swallowed_warmup(rig):
    @contextmanager
    def attempted_forward():
        yield SimpleNamespace(forward_attempts=1)

    rig.executor.load_guard = attempted_forward
    with pytest.raises(TransportError, match='DURING_LOAD'):
        load(rig)
    assert rig.executor.poisoned and rig.executor.load_attempts == 1 and rig.calls['roi'] == 0


def child(rig, **options):
    ids = itertools.count()
    return workspace_child_application(rig.executor, token='x' * 64,
        issue_id=lambda: f'workspace_fixture_{next(ids):08d}', epoch='workspace_fixture_epoch', **options)


@pytest.mark.parametrize('seconds', [0, -1, 120.01, float('inf'), float('nan'), True, '120'])
def test_child_job_deadline_is_finite_and_bounded_before_bootstrap(rig, seconds):
    with pytest.raises(ValueError, match='BOUNDED_WORKSPACE_JOB'):
        child(rig, job_seconds=seconds)
    assert rig.calls['load'] == 0


def finish(coroutine):
    # Awaited fixture operations are immediate; no Windows event-loop/socketpair.
    with pytest.raises(StopIteration):
        coroutine.send(None)


def test_wrapper_missing_parent_bootstrap_fails_closed(rig, monkeypatch):
    monkeypatch.setattr('dr_support.services.prism_workspace_executor.child_application',
                        lambda *a, **k: (object(), SimpleNamespace()))
    with pytest.raises(TransportError, match='HOST_BOOTSTRAP_REQUIRED'):
        child(rig)
    assert rig.calls['load'] == 0


@pytest.mark.parametrize('headers', [[], [(b'authorization', b'Bearer invalid')],
    [(b'authorization', b'Bearer ' + b'x' * 64)] * 2])
@pytest.mark.parametrize('path', ['/execute', '/capabilities'])
def test_wrapper_reuses_auth_before_body_and_model_load(rig, headers, path):
    app, host = child(rig)
    assert host.allowed_origins == frozenset({'PUBLIC', 'SYNTHETIC'}) and host.job_seconds == 120

    async def run():
        sent = []

        async def forbidden():
            pytest.fail('unauthorized body read')

        async def send(event):
            sent.append(event)

        await app({'type': 'http', 'method': 'POST', 'path': BASE + path, 'headers': headers}, forbidden, send)
        assert sent[0]['status'] == 401

    finish(run())
    assert rig.calls['load'] == rig.calls['roi'] == 0


def test_bootstrap_snapshots_existing_policy_without_promoting_loaded_readiness(rig, monkeypatch):
    monkeypatch.setenv('MODEL_HOSPITAL_SCOPE', 'PRIVATE_PROJECT_EVALUATION')
    monkeypatch.setenv('MODEL_ALLOW_AUTHORIZED_HOSPITAL', '1')
    monkeypatch.setenv('REMOTE_MODEL_TOKEN', 'synthetic-test-token-not-a-credential')
    _, host = child(rig, job_seconds=25)
    assert host.allowed_origins == frozenset({'PUBLIC', 'SYNTHETIC', 'HOSPITAL_AUTHORIZED'})
    assert host.job_seconds == 25 and not rig.executor.loaded
    assert rig.calls['load'] == rig.calls['roi'] == 0


def test_child_lifespan_loads_once_and_readiness_is_actual_loaded_pins_only(rig, monkeypatch):
    app, _ = child(rig)

    async def immediate_wait(coroutine, timeout):
        return await coroutine

    async def immediate_thread(function, *args):
        return function(*args)

    monkeypatch.setattr('dr_support.services.prism_owned_runtime.asyncio',
        SimpleNamespace(wait_for=immediate_wait, to_thread=immediate_thread, TimeoutError=TimeoutError))

    async def run():
        events, sent = [], []

        async def send(value):
            events.append(value)

        async def receive():
            return {'type': 'http.request', 'body': b''}

        async def capture(value):
            sent.append(value)

        async def lifecycle():
            if not events:
                return {'type': 'lifespan.startup'}
            assert events[0]['type'] == 'lifespan.startup.complete'
            await app({'type': 'http', 'method': 'GET', 'path': BASE + '/readiness', 'query_string': b'',
                       'headers': [(b'authorization', b'Bearer ' + b'x' * 64)]}, receive, capture)
            return {'type': 'lifespan.shutdown'}

        await app({'type': 'lifespan'}, lifecycle, send)
        assert sent[0]['status'] == 200
        assert json.loads(sent[1]['body']) == {'state': 'LOADED', 'pins': rig.pins, 'epoch': 'workspace_fixture_epoch'}

    finish(run())
    assert rig.calls['load'] == 1 and rig.calls['roi'] == 0


def test_workspace_capabilities_require_actual_loaded_pins_without_forward(rig):
    _, host = child(rig)
    status, error = host.handle('GET', BASE + '/capabilities', {}, b'')
    assert status == 503 and error['error'] == 'OWNED_MODEL_NOT_LOADED_WITH_PINS'
    assert rig.calls['load'] == rig.calls['roi'] == 0
    load(rig)
    status, caps = host.handle('GET', BASE + '/capabilities', {}, b'')
    assert status == 200 and caps['pins'] == rig.pins and caps['runtime_registered'] is False
    assert caps['workspace_runtime'] == {
        'profile': 'HOSPITAL_M1', 'modalities': ['CFP', 'UWF'],
        'authorized_source_origins': ['PUBLIC', 'SYNTHETIC'],
        'native_entry_protocol': caps['binding_protocol'], 'load_state': 'LOADED',
    }
    assert rig.calls['load'] == 1 and rig.calls['roi'] == 0
    rig.provider._loaded_identity['config_sha256'] = 'a' * 64
    status, error = host.handle('GET', BASE + '/capabilities', {}, b'')
    assert status == 503 and error['error'] == 'OWNED_MODEL_NOT_LOADED_WITH_PINS'
    assert rig.calls['load'] == 1 and rig.calls['roi'] == 0


def test_capabilities_recheck_hospital_policy_and_do_not_expand_bootstrap_scope(rig, monkeypatch):
    for key, value in {'MODEL_HOSPITAL_SCOPE': 'PRIVATE_PROJECT_EVALUATION',
                       'MODEL_ALLOW_AUTHORIZED_HOSPITAL': '1',
                       'REMOTE_MODEL_TOKEN': 'synthetic-test-token-not-a-credential'}.items():
        monkeypatch.setenv(key, value)
    _, host = child(rig)
    load(rig)
    status, caps = host.handle('GET', BASE + '/capabilities', {}, b'')
    assert status == 200
    assert caps['workspace_runtime']['authorized_source_origins'] == ['HOSPITAL_AUTHORIZED', 'PUBLIC', 'SYNTHETIC']
    monkeypatch.delenv('MODEL_ALLOW_AUTHORIZED_HOSPITAL')
    status, caps = host.handle('GET', BASE + '/capabilities', {}, b'')
    assert status == 200 and caps['workspace_runtime']['authorized_source_origins'] == ['PUBLIC', 'SYNTHETIC']
    host.allowed_origins = frozenset({'WORKSPACE'})
    status, error = host.handle('GET', BASE + '/capabilities', {}, b'')
    assert status == 503 and error['error'] == 'WORKSPACE_LOADED_PINS_OR_SOURCE_SCOPE_CHANGED'
    assert rig.calls['roi'] == 0


@pytest.mark.parametrize('modality', ['CFP', 'UWF'])
def test_workspace_host_optin_accepts_ordinary_preparation_and_replay_remains_blocked(rig, modality):
    _, host = child(rig)
    load(rig)
    value = {'wire_b64': base64.b64encode(rig.wire.data).decode(), 'wire_sha256': rig.wire.sha256,
             'wire_media_type': 'image/png', 'modality': modality}
    headers = {'x-prism-epoch': host.epoch}
    status, prepared = host.handle('POST', BASE + '/prepare', headers, canonical(value))
    assert status == 200, prepared
    binding, mask = plan(rig, modality=modality)
    assert prepared['external_fov_status'] == binding['external_fov_status']
    request = {'ticket_id': prepared['ticket_id'], 'binding': binding, 'plan_sha256': sha(canonical(binding))}
    status, job = host.handle('POST', BASE + '/execute', headers, canonical(request))
    assert status == 202, job
    running = host.jobs[job['job_id']]
    try:
        with running.condition:
            assert running.condition.wait_for(lambda: running.state == 'WAITING_SOURCE_FENCE', timeout=2)
            grant = {'challenge_id': running.challenge, 'plan_sha256': request['plan_sha256'],
                     'fence_id': 'synthetic_workspace_fence'}
        assert host.handle('POST', BASE + '/jobs/' + job['job_id'] + '/grant', headers, canonical(grant))[0] == 200
        host.join_for_test()
        assert running.state == 'COMPLETE', running.error
        status, replay = host.handle('POST', BASE + '/execute', headers, canonical(request))
        assert status == 409 and replay['error'] == 'REPLAY'
        assert rig.calls['roi'] == 1 and rig.calls['load'] == 1
    finally:
        with running.condition:
            running.cancelled = True
            running.condition.notify_all()
        host.join_for_test()


def test_default_child_remains_synthetic_uwf_only(rig):
    legacy = LoadedPrismExecutor(rig.provider, expected_pins=rig.pins, load_guard=fake_guard)
    _, host = child_application(legacy, token='x' * 64, issue_id=lambda: 'legacy_fixture_id', epoch='legacy_epoch')
    assert host.allowed_origins == frozenset({'SYNTHETIC'}) and host.job_seconds == 30
    status, caps = host.handle('GET', BASE + '/capabilities', {}, b'')
    assert status == 200 and 'workspace_runtime' not in caps
    value = {'wire_b64': base64.b64encode(rig.wire.data).decode(), 'wire_sha256': rig.wire.sha256,
             'wire_media_type': 'image/png', 'modality': 'CFP'}
    status, result = host.handle('POST', BASE + '/prepare', {'x-prism-epoch': host.epoch}, canonical(value))
    assert status == 422 and result['error'] == 'WIRE_CONTEXT'
    assert rig.calls['load'] == rig.calls['roi'] == 0
