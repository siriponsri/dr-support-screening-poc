"""Synthetic HTTP/DB ports only: no native model, network or login proof."""
from copy import deepcopy
import json
from types import SimpleNamespace

import httpx
import pytest

from dr_support.images import synthetic_image
from dr_support.providers.prism_remote_bound import ExplicitHttpChannel, RemoteBoundTransportCandidate, RemoteExecutionUncertain
from dr_support.providers.prism_workspace_remote import WorkspaceRemotePRISM, WorkspaceStatusReader
from dr_support.services import prism_workspace_authority as core
from dr_support.services.capability_routing import capability_is_qualified, route_capability
from dr_support.services.prism_preview import PreviewSnapshot, PrismPreviewService, preparation_context
from dr_support.services.prism_remote_transport import BASE, PROTOCOL, TRANSPORT, TransportError, canonical, sha


def pins():
    return dict(model_id='prism-dr-5fold', source_revision='synthetic-reviewed-revision',
                preprocessing='synthetic-reviewed-preprocessing', config_sha256='a' * 64,
                checkpoint_sha256={'fold-0': 'b' * 64})


def capabilities():
    return dict(transport=TRANSPORT, binding_protocol=PROTOCOL, epoch='synthetic-epoch', pins=pins(),
                workspace_runtime=dict(profile='HOSPITAL_M1', modalities=['CFP', 'UWF'],
                    authorized_source_origins=['PUBLIC', 'SYNTHETIC'], native_entry_protocol=PROTOCOL,
                    load_state='LOADED'))


class SyntheticDatabase:
    """In-memory fence port; not PostgreSQL qualification."""
    def __init__(self, reader):
        self.reader, self.binding, self.acquisitions = reader, None, 0

    def read(self):
        return deepcopy(self.binding)

    def acquire(self, **kwargs):
        assert self.binding is None
        self.binding = deepcopy(kwargs['binding'])
        self.acquisitions += 1
        return SyntheticPermit(self)

    def recover(self):
        if self.binding is not None:
            SyntheticPermit(self).release(None)


class SyntheticPermit:
    def __init__(self, database):
        self.database, self.fence_id = database, database.binding['fence_id']

    def release(self, proof):
        status = self.database.reader(self.database.binding)
        assert status['forward_started'] or status['terminal']
        self.database.binding = None

    def quarantine(self, reason):
        pass  # Retain the synthetic durable binding.


@pytest.fixture
def rig(tmp_path, monkeypatch):
    # Tests never mutate permissions or claim privacy qualification.
    monkeypatch.setattr(core, 'private_hospital_root', lambda *a, **k: True)
    value = SimpleNamespace(caps=capabilities(), loaded=dict(state='LOADED', pins=pins(), epoch='synthetic-epoch'),
                            requests=[], status=None, context=None, fault=None, calls=[], result_change=None)

    def endpoint(request):
        value.requests.append((request.method, request.url.path, request.headers.get('X-Prism-Epoch')))
        assert request.headers['Authorization'] == 'Bearer SYNTHETIC_CONTROL_ONLY'
        if value.fault == 'offline':
            raise httpx.ReadError('Synthetic offline')
        path = request.url.path
        if path == BASE + '/capabilities':
            return httpx.Response(200, json=value.caps)
        if path == BASE + '/readiness':
            return httpx.Response(200, json=value.loaded)
        if path == BASE + '/prepare':
            return httpx.Response(200, json=dict(ticket_id='synthetic-ticket', pins=pins(), epoch='synthetic-epoch',
                external_fov_status='NOT_APPLICABLE', external_fov_reason_code=None,
                mask_b64=None, mask_sha256=None, mask_png_sha256=None, mask_version=None))
        if path == BASE + '/execute':
            value.calls.append('execute')
            body = json.loads(request.content)
            value.status = dict(epoch='synthetic-epoch', job_id='synthetic-job', ticket_id='synthetic-ticket',
                plan_sha256=body['plan_sha256'], pins=pins(), challenge_id='synthetic-challenge',
                state='WAITING_SOURCE_FENCE', forward_started=False, terminal=False, error=None, result=None)
            if value.fault == 'drop_execute':
                raise httpx.ReadError('Synthetic lost execute acknowledgement')
            return httpx.Response(202, json={'job_id': 'synthetic-job'})
        if path.endswith('/grant'):
            value.calls.append('grant')
            if value.fault == 'drop_grant':
                value.fault = 'offline'
                raise httpx.ReadError('Synthetic lost grant acknowledgement')
            value.status.update(state='COMPLETE', forward_started=True, terminal=True, result=value.result)
            return httpx.Response(200, json={'accepted': True})
        if path.endswith('/cancel'):
            value.status.update(state='ABORTED', terminal=True)
            return httpx.Response(200, json={'accepted': True})
        if path.startswith(BASE + '/jobs/'):
            if value.status is None:
                return httpx.Response(404, json={'error': 'SYNTHETIC_UNKNOWN_OLD_JOB'})
            return httpx.Response(200, json=value.status)
        pytest.fail('Unexpected protocol route: ' + path)

    value.channel = ExplicitHttpChannel('http://127.0.0.1:48765', transport=httpx.MockTransport(endpoint),
        auth_headers=lambda *_: {'Authorization': 'Bearer SYNTHETIC_CONTROL_ONLY'})
    value.reader = WorkspaceStatusReader(value.channel)
    value.database = SyntheticDatabase(value.reader)
    value.authority = core.WorkspaceAuthority(tmp_path / 'synthetic-private-authority',
        context_reader=lambda image_id: {**deepcopy({key: item for key, item in value.context.items() if key != 'objects'}),
                                        'objects': value.context['objects']},
        database_fence=value.database, authenticated_status_reader=value.reader)
    value.client = WorkspaceRemotePRISM(value.channel, source_authority=value.authority, expected_pins=pins(),
                                        wait_seconds=.05, poll_seconds=.001)
    value.image = synthetic_image()
    admission = dict(source_origin='SYNTHETIC', source_sha256=value.image.sha256, retinal_modality='CFP',
                     modality_admission='FUNDUS_ACCEPTED', quality_state='NOT_EVALUATED', integrity_status='OK')
    case = dict(image_id=value.image.image_id, revision=2, source_sha256=value.image.sha256,
                image_sha256=value.image.sha256, admission=deepcopy(admission))
    value.context = dict(workspace_id='synthetic-workspace', image_id=value.image.image_id, case=case,
        workspace={'workspace_id': 'synthetic-workspace', 'name': 'Synthetic fixture'}, admission=admission,
        source_sha256=value.image.sha256, preparation_context=preparation_context(case), model_pins=pins(),
        runtime_context={'database': 'synthetic-port', 'route': 'synthetic-loopback'},
        objects=(object(), value.client, object(), object()))
    yield value
    value.authority.close()
    value.channel.close()


def prepare_plan(rig):
    rig.client.negotiate()
    width, height = rig.image.size
    recorded = dict(case_source_sha256=rig.image.sha256, admission_source_sha256=rig.image.sha256,
        image_recorded_sha256=rig.image.sha256, integrity_status='OK', source_origin='SYNTHETIC',
        case_revision=2, admission_sha256=sha(canonical(rig.context['admission'])))
    snapshot = PreviewSnapshot(scope='synthetic-scope', image_id=rig.image.image_id, revision=2,
        source=rig.image.data, wire=rig.image.data, wire_media_type=rig.image.media_type, modality='CFP',
        model_version=pins()['source_revision'], model_pins=pins(), preparation_context=rig.context['preparation_context'],
        admission=deepcopy(rig.context['admission']), recorded_source_identity=recorded,
        transform=dict(version='synthetic-v1', transform_id='identity', representation_version='synthetic-v1',
            coordinate_mapping={'scale_x': 1.0, 'scale_y': 1.0}, original_width=width, original_height=height,
            input_width=width, input_height=height, original_to_input=[1, 0, 0, 1, 0, 0]),
        external_fov_status='NOT_APPLICABLE', external_fov_reason_code=None, mask=None, mask_version=None,
        runtime=SimpleNamespace(store=rig.context['objects'][0], provider=rig.client))
    frozen, _ = PrismPreviewService._freeze(snapshot)
    keys = ('scope', 'image_id', 'case_revision', 'source_sha256', 'wire_sha256', 'admission_sha256',
            'recorded_source_identity', 'admission', 'preparation_context', 'model_pins')
    rig.authority.authorize_prepare(rig.image, {key: frozen[key] for key in keys}, original_bytes=rig.image.data)
    rig.client.prepare_prism_preview_candidate(rig.image)
    binding = dict(frozen, plan_id='synthetic-plan', generation=0, expires_at='2099-01-01T00:00:00+00:00')
    rig.authority.register_preview_plan(snapshot, binding, sha(canonical(binding)))
    rig.result = dict(preview_receipt=dict(plan_sha256=sha(canonical(binding)), wire_sha256=rig.image.sha256,
        mask_sha256=None, transform_sha256=binding['transform']['sha256']), result=dict(model_id='prism-dr-5fold',
        model_version=pins()['source_revision'], modality='CFP', state='AI_SUGGESTION', width=width, height=height,
        lesions=[], warnings=['SYNTHETIC_PROTOCOL_RESULT_NOT_INFERENCE'], provenance=dict(image_sha256=rig.image.sha256,
            source_type='SYNTHETIC', source_revision=pins()['source_revision'], checkpoint_sha256=pins()['checkpoint_sha256'],
            preprocessing=pins()['preprocessing'])))
    return binding


def run(rig, binding):
    request = SimpleNamespace(image_id=rig.image.image_id, model_id='prism-dr-5fold', modality='CFP')
    return rig.client.infer_bound_prism(request, rig.image, mask_png=None, binding=binding,
        plan_sha256=sha(canonical(binding)), before_forward=lambda: rig.calls.append('revalidate'))


def test_constructor_and_unready_metadata_are_cache_only_and_old_candidate_stays_unqualified(rig):
    assert rig.requests == []
    assert rig.client.metadata()['ready'] is False
    with pytest.raises(TransportError, match='NEGOTIATION_REQUIRED'):
        rig.client.prism_preview_identity()
    assert rig.requests == []
    old = RemoteBoundTransportCandidate(rig.channel)
    old.negotiate()
    assert old.prism_preview_identity()['descriptor']['ready'] is False
    assert old.prism_preview_protocol == TRANSPORT


@pytest.mark.parametrize('change', ['model_id', 'source_revision', 'preprocessing', 'config_sha256',
                                  'checkpoint_sha256', 'extra', 'missing'])
def test_expected_pins_require_exact_nonsecret_schema_before_any_rpc(rig, change):
    candidate = pins()
    if change == 'extra': candidate['extra'] = 'rejected'
    elif change == 'missing': candidate.pop('model_id')
    elif change == 'checkpoint_sha256': candidate[change] = {'fold-0': 'invalid'}
    else: candidate[change] = ''
    with pytest.raises(TransportError, match='REVIEWED_MODEL_PINS_REQUIRED'):
        WorkspaceRemotePRISM(rig.channel, source_authority=rig.authority, expected_pins=candidate)
    assert rig.requests == []


def test_exact_authority_and_channel_are_mandatory(rig):
    with pytest.raises(TransportError, match='EXACT_WORKSPACE_AUTHORITY'):
        WorkspaceRemotePRISM(rig.channel, source_authority=SimpleNamespace(), expected_pins=pins())
    with pytest.raises(TransportError, match='EXACT_EXPLICIT_CHANNEL'):
        WorkspaceRemotePRISM(SimpleNamespace(client=rig.channel.client), source_authority=rig.authority, expected_pins=pins())
    assert rig.requests == []


def test_independent_pins_are_copied_and_metadata_does_not_promote_inference_or_origins(rig):
    expected = pins()
    client = WorkspaceRemotePRISM(rig.channel, source_authority=rig.authority, expected_pins=expected)
    expected['checkpoint_sha256']['fold-0'] = 'c' * 64
    rig.caps['workspace_runtime']['authorized_source_origins'] += ['HOSPITAL_AUTHORIZED', 'UNKNOWN']
    client.negotiate()
    assert rig.requests == [('GET', BASE + '/capabilities', None), ('GET', BASE + '/readiness', 'synthetic-epoch')]
    observed = len(rig.requests)
    identity = client.prism_preview_identity()
    descriptor = client.metadata()
    assert identity['model_pins'] == pins() and len(rig.requests) == observed
    assert descriptor['ready'] and descriptor['status'] == 'LOADED' and capability_is_qualified(descriptor)
    assert descriptor['authorized_source_origins'] == ['HOSPITAL_AUTHORIZED', 'PUBLIC', 'SYNTHETIC']
    assert descriptor['inference_validation'] == 'NOT_RUN'
    assert descriptor['release_status'] == 'RESEARCH_ONLY' and descriptor['production_authorization'] == 'NOT_AUTHORIZED'
    assert descriptor['clinical_validation_status'] == 'NOT_VALIDATED_FOR_UWF' and descriptor['uwf_use'] == 'EXPERIMENTAL'
    route_capability(descriptor, model_id='prism-dr-5fold', task='lesion-roi', modality='UWF')
    identity['model_pins']['checkpoint_sha256']['fold-0'] = 'd' * 64
    assert client.prism_preview_identity()['model_pins'] == pins()


@pytest.mark.parametrize('change', ['transport', 'binding_protocol', 'epoch', 'pins', 'no_runtime',
    'runtime_extra', 'profile', 'modalities', 'native_entry_protocol', 'load_state', 'origins_type', 'origins_duplicate'])
def test_capability_failure_cannot_become_ready_or_send_prepare(rig, change):
    if change in {'transport', 'binding_protocol', 'epoch'}: rig.caps[change] = ''
    elif change == 'pins': rig.caps['pins']['config_sha256'] = 'd' * 64
    elif change == 'no_runtime': rig.caps.pop('workspace_runtime')
    elif change == 'runtime_extra': rig.caps['workspace_runtime']['extra'] = True
    elif change == 'origins_type': rig.caps['workspace_runtime']['authorized_source_origins'] = 'SYNTHETIC'
    elif change == 'origins_duplicate': rig.caps['workspace_runtime']['authorized_source_origins'] = ['SYNTHETIC'] * 2
    else: rig.caps['workspace_runtime'][change] = 'unqualified'
    with pytest.raises(TransportError): rig.client.negotiate()
    assert not rig.client.metadata()['ready']
    with pytest.raises(TransportError): rig.client.prepare_prism_preview_candidate(rig.image)
    assert [method for method, _, _ in rig.requests] == ['GET']


@pytest.mark.parametrize('change', ['state', 'pins', 'epoch', 'extra', 'missing', 'body'])
def test_health_like_or_mismatched_loaded_attestation_is_not_readiness(rig, change):
    if change == 'pins': rig.loaded['pins']['config_sha256'] = 'c' * 64
    elif change == 'extra': rig.loaded['healthy'] = True
    elif change == 'missing': rig.loaded.pop('pins')
    elif change == 'body': rig.loaded = []
    else: rig.loaded[change] = 'unqualified'
    with pytest.raises(TransportError): rig.client.negotiate()
    assert rig.client.capabilities is None and rig.client.tickets == {}
    assert not rig.client.metadata()['ready']
    assert [path for _, path, _ in rig.requests] == [BASE + '/capabilities', BASE + '/readiness']


def test_failed_renegotiation_invalidates_old_identity_and_prepare_tickets(rig):
    prepare_plan(rig)
    assert rig.client.tickets
    rig.loaded['state'] = 'NOT_LOADED'
    with pytest.raises(TransportError): rig.client.negotiate()
    assert rig.client.capabilities is None and rig.client.tickets == {}
    with pytest.raises(TransportError): rig.client.prism_preview_identity()


@pytest.mark.parametrize('change', ['cached_epoch', 'cached_pins', 'cached_origins', 'route', 'authority', 'auth_callback', 'timeout'])
def test_negotiated_evidence_and_ports_cannot_change_silently(rig, change):
    binding = prepare_plan(rig)
    count = len(rig.requests)
    if change == 'cached_epoch': rig.client.capabilities['epoch'] = 'changed'
    elif change == 'cached_pins': rig.client.capabilities['pins']['config_sha256'] = 'c' * 64
    elif change == 'cached_origins': rig.client.capabilities['workspace_runtime']['authorized_source_origins'] += ['HOSPITAL_AUTHORIZED']
    elif change == 'route': rig.channel.client.base_url = 'http://127.0.0.1:48766'
    elif change == 'authority': rig.client.authority = object()
    elif change == 'auth_callback': rig.channel.auth_headers = lambda *_: {}
    else: rig.channel.client.timeout = httpx.Timeout(30)
    with pytest.raises(TransportError): run(rig, binding)
    assert len(rig.requests) == count and rig.client.tickets
    assert rig.database.acquisitions == 0


def test_actual_authority_refuses_unregistered_plan_before_execute_or_ticket_consumption(rig):
    rig.client.negotiate()
    binding = {'synthetic': 'not registered'}
    with pytest.raises(TransportError, match='REGISTERED_WORKSPACE_PLAN_REQUIRED_BEFORE_DISPATCH'):
        run(rig, binding)
    assert rig.calls == [] and rig.database.acquisitions == 0
    assert all(method == 'GET' for method, _, _ in rig.requests)


@pytest.mark.parametrize('change', ['same_revision_case', 'object', 'writer'])
def test_actual_authority_detects_stale_plan_before_any_execute(rig, change):
    binding = prepare_plan(rig)
    before = len(rig.requests)
    if change == 'same_revision_case': rig.context['case']['unprojected_change'] = True
    elif change == 'object': rig.context['objects'] = (object(), *rig.context['objects'][1:])
    else:
        with rig.authority.gate.writer(): pass
    with pytest.raises(TransportError): run(rig, binding)
    assert len(rig.requests) == before and rig.calls == [] and rig.client.tickets


def test_actual_authority_runs_before_single_execute_and_full_lease_receipt_path(rig, monkeypatch):
    binding = prepare_plan(rig)
    original = core.WorkspaceAuthority.authorize_execute
    def authorize(authority, frozen, digest):
        rig.calls.append('authorize_execute')
        return original(authority, frozen, digest)
    monkeypatch.setattr(core.WorkspaceAuthority, 'authorize_execute', authorize)
    result = run(rig, binding)
    assert rig.calls == ['authorize_execute', 'execute', 'revalidate', 'grant']
    assert rig.database.acquisitions == 1 and rig.database.binding is None
    assert rig.authority.gate.snapshot().state == 'OPEN'
    assert result['result']['lesions'] == [] and result['result']['state'] == 'AI_SUGGESTION'
    assert rig.client.metadata()['inference_validation'] == 'NOT_RUN'  # Synthetic output is not clinical/model proof.
    with pytest.raises(TransportError): run(rig, binding)
    assert rig.calls.count('execute') == 1


def test_inherited_result_receipt_and_provenance_checks_remain_mandatory(rig):
    binding = prepare_plan(rig)
    rig.result['result']['provenance']['image_sha256'] = 'e' * 64
    with pytest.raises(TransportError, match='RESULT_PROVENANCE_MISMATCH'): run(rig, binding)
    assert rig.calls.count('execute') == 1
    assert rig.authority.gate.snapshot().state == 'OPEN'


@pytest.mark.parametrize('fault', ['drop_execute', 'drop_grant'])
def test_uncertain_execute_or_grant_never_resubmits_and_unknown_grant_stays_quarantined(rig, fault):
    binding = prepare_plan(rig)
    rig.fault = fault
    with pytest.raises(RemoteExecutionUncertain): run(rig, binding)
    assert rig.calls.count('execute') == 1
    with pytest.raises(TransportError): run(rig, binding)
    assert rig.calls.count('execute') == 1
    if fault == 'drop_grant':
        assert rig.authority.gate.snapshot().state == 'QUARANTINED' and rig.database.binding is not None


def old_binding():
    return dict(epoch='old-epoch', job_id='old-job', ticket_id='old-ticket', plan_sha256='e' * 64,
                pins=pins(), challenge_id='old-challenge')


def test_old_status_reader_does_not_need_provider_or_new_epoch_negotiation(rig):
    binding = old_binding()
    rig.status = dict(binding, state='COMPLETE', forward_started=True, terminal=True)
    proof = rig.reader(binding)
    assert proof == rig.status and proof is not rig.status
    assert rig.client.capabilities is None
    assert rig.requests == [('GET', BASE + '/jobs/old-job', 'old-epoch')]


@pytest.mark.parametrize('field', list(core.STATUS_KEYS))
def test_old_reader_rejects_new_epoch_or_any_other_scope_mismatch(rig, field):
    binding = old_binding()
    rig.status = dict(binding, state='COMPLETE', forward_started=True, terminal=True)
    rig.status[field] = pins() if field == 'pins' else 'changed'
    if field == 'pins': rig.status[field]['config_sha256'] = 'c' * 64
    with pytest.raises(TransportError, match='AUTHENTICATED_OLD_JOB_SCOPE_CHANGED'): rig.reader(binding)
    assert rig.requests[0][2] == 'old-epoch'


@pytest.mark.parametrize('field', ['epoch', 'job_id', 'ticket_id', 'challenge_id', 'plan_sha256', 'pins'])
def test_old_reader_validates_scope_before_sending_and_never_retries(rig, field):
    binding = old_binding()
    binding[field] = '../not-a-job' if field != 'pins' else {}
    with pytest.raises(TransportError): rig.reader(binding)
    assert rig.requests == []


@pytest.mark.parametrize('fault', ['unknown', 'offline'])
def test_unavailable_old_proof_is_refused_without_negotiating_or_load(rig, fault):
    if fault == 'offline': rig.fault = 'offline'
    with pytest.raises((TransportError, httpx.TransportError)): rig.reader(old_binding())
    assert rig.requests == [('GET', BASE + '/jobs/old-job', 'old-epoch')]


def test_status_channel_route_change_cannot_redirect_recovery(rig):
    rig.channel.client.base_url = 'http://127.0.0.1:48766'
    with pytest.raises(TransportError, match='STATUS_CHANNEL_CHANGED'): rig.reader(old_binding())
    assert rig.requests == []
