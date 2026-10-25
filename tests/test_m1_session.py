"""M1 host session controls with the real ledger/consumer and fake child/apps.

No GPU, model, listener, SSH or network. Live dr-train qualification is separate.
"""
import asyncio
import base64
import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/model-server'))
operations = importlib.import_module('m1_operations')
session = importlib.import_module('m1_session')
from test_m1_native_admission import (  # noqa: E402
    rig as _admission_rig, accounting_rig as _accounting_rig, upstream_seed as _upstream_seed,
)

admission_rig = _admission_rig
accounting_rig = _accounting_rig
upstream_seed = _upstream_seed


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------- operations

def test_copied_route_constants_match_the_transport_module():
    from dr_support.services.prism_remote_transport import BASE, PROTOCOL
    assert operations.PRISM_ROUTE == BASE + '/execute' == session.PRISM_ROUTE
    assert operations.PRISM_PROTOCOL == PROTOCOL and session.BASE == BASE


def reviewed(monkeypatch, *, raw_out=None):
    pins = {
        'retfound-aptos5': dict(model_id='retfound-aptos5', source_revision='r' * 40,
            checkpoint_sha256={'aptos5': 'a' * 64}, preprocessing='RGB resize', provider_source_sha256='b' * 64),
        'uspec-uwf-grading': dict(model_id='uspec-uwf-grading', source_revision='u' * 64,
            checkpoint_sha256={'grading_state.pt': 'c' * 64}, preprocessing='letterbox', provider_source_sha256='d' * 64),
    }
    checkpoints = {f'Final Models/fold {index}/weights/best.pt': f'{index:064x}' for index in range(21)}
    expected = {name: {'pins': value, 'capability_id': 'dr_grade', 'model_version': 'x'} for name, value in pins.items()}
    expected['prism-dr-5fold'] = {'pins': dict(model_id='prism-dr-5fold', source_revision='p' * 40,
        checkpoint_sha256=checkpoints, preprocessing='batch', config_sha256='e' * 64),
        'capability_id': 'core_lesion_localization', 'configuration': {}, 'model_version': 'p'}
    raw = json.dumps(expected).encode()
    monkeypatch.setattr(operations, 'EXPECTED_MODELS_SHA256', sha(raw))
    prism = dict(model_id='prism-dr-5fold', source_revision='p' * 40, checkpoint_sha256=checkpoints,
                 preprocessing='workspace; bound_config=f', config_sha256='f' * 64)
    if raw_out is not None:
        raw_out.append(raw)
    return operations.reviewed_models(raw, prism)


def test_reviewed_models_reject_changed_bytes_and_unrelated_prism_weights(monkeypatch):
    raws = []
    models = reviewed(monkeypatch, raw_out=raws)
    assert set(models) == {'retfound-aptos5', 'uspec-uwf-grading', 'prism-dr-5fold'}
    prism = models['prism-dr-5fold']['pins']
    with pytest.raises(operations.OperationError, match='REVIEWED_MODEL_PINS_CHANGED'):
        operations.reviewed_models(raws[0] + b' ', prism)
    for changed in (dict(prism, checkpoint_sha256={'other.pt': '0' * 64}),
                    dict(prism, source_revision='q' * 40), dict(prism, extra='field')):
        with pytest.raises(operations.OperationError, match='PRISM_WORKSPACE_PINS_REQUIRED'):
            operations.reviewed_models(raws[0], changed)


def test_facts_bind_model_modality_pins_route_and_operation_hash(monkeypatch):
    models = reviewed(monkeypatch)
    one = operations.facts(models, source_sha256='1' * 64, model_id='uspec-uwf-grading', modality='UWF')
    assert set(one) == set(operations.FACT_KEYS)
    assert one['model_pins_sha256'] == sha(operations.canonical(models['uspec-uwf-grading']['pins']))
    prism = operations.facts(models, source_sha256='1' * 64, model_id='prism-dr-5fold', modality='CFP')
    assert prism['parameters_sha256'] != one['parameters_sha256']
    for model_id, modality in [('uspec-uwf-grading', 'CFP'), ('retfound-aptos5', 'UWF'), ('unknown', 'CFP')]:
        with pytest.raises(operations.OperationError):
            operations.facts(models, source_sha256='1' * 64, model_id=model_id, modality=modality)
    op = operations.operation(models, operation_id='server-fresh-uspec', purpose='server_acceptance',
                              window_id='W', source_sha256='1' * 64, model_id='uspec-uwf-grading', modality='UWF')
    assert op['job_id'] == sha(operations.canonical({k: v for k, v in op.items() if k != 'job_id'}))


def test_match_operation_takes_lowest_unattempted_exact_operation_only(monkeypatch):
    models = reviewed(monkeypatch)
    kwargs = dict(purpose='server_acceptance', window_id='W', source_sha256='1' * 64,
                  model_id='retfound-aptos5', modality='CFP')
    first = operations.operation(models, operation_id='a-first', **kwargs)
    second = operations.operation(models, operation_id='b-second', **kwargs)
    jobs = {job['job_id']: job for job in (second, first)}
    observed = {key: first[key] for key in operations.FACT_KEYS}
    assert operations.match_operation(jobs, observed, window_id='W', states={})['operation_id'] == 'a-first'
    states = {first['job_id']: 'PASS_READBACK'}
    assert operations.match_operation(jobs, observed, window_id='W', states=states)['operation_id'] == 'b-second'
    assert operations.match_operation(jobs, observed, window_id='OTHER', states={}) is None
    assert operations.match_operation(jobs, {**observed, 'source_sha256': '2' * 64}, window_id='W', states={}) is None


def test_drafted_plan_has_exact_allocations_unique_identities_and_supported_pairs(monkeypatch):
    from collections import Counter
    proposal = importlib.import_module('m1_proposal')
    models = reviewed(monkeypatch)
    uwf = [f'{index + 100:064x}' for index in range(11)]
    cfp = [f'{index + 200:064x}' for index in range(10)]
    jobs = [operations.operation(models, operation_id=operation_id, purpose=purpose, window_id=window,
                                 source_sha256=source, model_id=model_id, modality=modality)
            for operation_id, purpose, window, source, model_id, modality in proposal.plan(uwf, cfp)]
    assert len(jobs) == 24 and len({job['job_id'] for job in jobs}) == 24
    assert len({job['operation_id'] for job in jobs}) == 24
    assert Counter(job['purpose'] for job in jobs) == {'server_acceptance': 9, 'local_acceptance': 6,
                                                       'post_fix_verification': 9}
    assert all(job['window_id'] == proposal.LOCAL for job in jobs if job['purpose'] == 'local_acceptance')
    assert all(job['window_id'] == proposal.SERVER for job in jobs if job['purpose'] != 'local_acceptance')
    assert all((job['model_id'], job['modality']) in operations.SUPPORTED for job in jobs)
    with pytest.raises(operations.OperationError, match='FIVE_UWF_AND_FIVE_CFP'):
        proposal.plan(uwf[:4], cfp)
    # A post-fix source among the acceptance images is excluded, never shared.
    shared = proposal.POST_FIX[1][1]
    rows = proposal.plan([shared, *uwf], cfp)
    acceptance = [row for row in rows if row[1] != 'post_fix_verification']
    assert shared not in {row[3] for row in acceptance}


def server_app():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    return importlib.import_module('scripts.qa.m1_server_app')


def persisted_global(models, *, status='APPLIED', timestamp='2026-10-23T12:00:10+00:00', grade=2):
    pins = models['retfound-aptos5']['pins']
    return {'model_id': 'retfound-aptos5', 'source_sha256': '1' * 64, 'status': status, 'task': 'global',
            'timestamp': timestamp,
            'result': {'model_id': 'retfound-aptos5', 'model_version': 'v', 'modality': 'CFP', 'state': 'AI_SUGGESTION',
                       'grade': grade, 'probabilities': [.1, .2, .7, 0, 0],
                       'provenance': {'checkpoint_sha256': pins['checkpoint_sha256'],
                                      'source_revision': pins['source_revision'], 'image_sha256': '1' * 64}}}


def admitted_entry(models, result):
    from datetime import datetime
    return {'model_id': 'retfound-aptos5', 'modality': 'CFP', 'source_sha256': '1' * 64, 'correlation': {},
            'admitted_utc': datetime.fromisoformat('2026-10-23T12:00:00+00:00').timestamp(),
            'result_sha256': operations.global_result_digest(result)}


@pytest.mark.parametrize('name, allowed', [('m1-server-20261023-01', True), ('m1-prism-20261024-01', True), ('m1-service-20261025-01', True),
                                           ('m1-other-1', False), ('m1-prism-x;rm', False)])
def test_readback_accepts_only_server_and_prism_window_runs(monkeypatch, name, allowed):
    app = server_app()
    monkeypatch.setattr(app, 'ssh', lambda command, **_: b'{}')
    run = app.REMOTE_PROJECT + '/runs/' + name
    if allowed:
        assert app.remote_status(run) == {}
    else:
        with pytest.raises(app.SessionError, match='APPROVED_REMOTE_RUN_REQUIRED'):
            app.remote_status(run)


def test_readback_finds_the_case_by_its_stored_keys():
    # The case store keys rows by image_id and records the source hash per inference entry.
    app = server_app()
    assert "case_id=%s" in app.CASE_BY_SOURCE and "'inference_history' @>" in app.CASE_BY_SOURCE
    assert "payload->>'source_sha256'" not in app.CASE_BY_SOURCE
    workspace, source, history = app.case_parameters('ws', '1' * 64)
    assert (workspace, source) == ('ws', '1' * 64)
    assert json.loads(history) == [{'source_sha256': '1' * 64}]


def test_trusted_readback_is_bound_to_this_requests_persisted_result(monkeypatch):
    app = server_app()
    models = reviewed(monkeypatch)
    persisted = persisted_global(models)
    entry = admitted_entry(models, persisted['result'])
    assert app.verify_persisted({'inference_history': [persisted]}, entry, models, operations)[1] is True
    changed = json.loads(json.dumps(persisted))
    changed['result']['provenance']['checkpoint_sha256'] = {'aptos5': '0' * 64}
    assert app.verify_persisted({'inference_history': [changed]}, entry, models, operations)[1] is False
    with pytest.raises(app.SessionError, match='PERSISTED_INFERENCE_NOT_FOUND'):
        app.verify_persisted({'inference_history': []}, entry, models, operations)


@pytest.mark.parametrize('scenario', ['earlier_entry_only', 'different_result', 'stale', 'two_entries',
                                      'ai_set_human_shape'])
def test_readback_never_passes_on_other_or_unapplied_evidence(monkeypatch, scenario):
    app = server_app()
    models = reviewed(monkeypatch)
    current = persisted_global(models)
    entry = admitted_entry(models, current['result'])
    case = {'inference_history': [current]}
    if scenario == 'earlier_entry_only':
        # This request was never persisted; only an older entry exists.
        case['inference_history'] = [persisted_global(models, timestamp='2026-10-23T11:00:00+00:00')]
    elif scenario == 'different_result':
        case['inference_history'] = [persisted_global(models, grade=4)]
    elif scenario == 'stale':
        case['inference_history'] = [persisted_global(models, status='STALE_RESULT')]
    elif scenario == 'two_entries':
        case['inference_history'] = [persisted_global(models, timestamp='2026-10-23T11:00:00+00:00'), current]
    else:
        case['human_annotations'] = [{'id': 'x', 'score': .9}]
    assert app.verify_persisted(case, entry, models, operations)[1] is False


@pytest.mark.parametrize('probabilities', [[.1, .2, .7, 0, 0], [1, 0, 0, 0, 0], None])
def test_host_and_persisted_global_digests_agree_through_the_real_contract(probabilities):
    from dr_support.contracts import GlobalResult
    raw = {'model_id': 'retfound-aptos5', 'model_version': 'v', 'modality': 'CFP', 'state': 'UNGRADABLE',
           'grade': None, 'warnings': [], 'provenance': {
               'image_sha256': '1' * 64, 'source_type': 'HOSPITAL_AUTHORIZED', 'preprocessing': 'p',
               'source_revision': 'r', 'checkpoint_sha256': {'aptos5': 'a' * 64}}}
    if probabilities is not None:
        raw.update(state='AI_SUGGESTION', grade=probabilities.index(max(probabilities)),
                   probabilities=probabilities, confidence=max(probabilities))
    # Host hashes the raw HTTP JSON; the app persists the parsed contract.
    persisted = json.loads(json.dumps(GlobalResult.model_validate(raw).model_dump(mode='json')))
    assert operations.global_result_digest(raw) == operations.global_result_digest(persisted)


def test_prism_readback_is_bound_by_the_one_use_plan(monkeypatch):
    app = server_app()
    models = reviewed(monkeypatch)
    pins = models['prism-dr-5fold']['pins']
    entry = {'model_id': 'prism-dr-5fold', 'modality': 'UWF', 'source_sha256': '1' * 64,
             'correlation': {'plan_sha256': '9' * 64}, 'admitted_utc': 0, 'result_sha256': None}
    persisted = {'model_id': 'prism-dr-5fold', 'source_sha256': '1' * 64, 'status': 'APPLIED', 'task': 'lesion-roi',
                 'timestamp': '2026-10-23T12:00:10+00:00', 'preview_binding': {'plan_sha256': '9' * 64,
                                                                              'model_pins': pins},
                 'result': {'model_id': 'prism-dr-5fold', 'modality': 'UWF',
                            'provenance': {'checkpoint_sha256': pins['checkpoint_sha256'],
                                           'source_revision': pins['source_revision']}}}
    assert app.verify_persisted({'inference_history': [persisted]}, entry, models, operations)[1] is True
    persisted['preview_binding']['plan_sha256'] = '8' * 64
    assert app.verify_persisted({'inference_history': [persisted]}, entry, models, operations)[1] is False


def test_pending_status_identifiers_are_validated_before_remote_use():
    app = server_app()
    good = {'state': 'RESPONSE_OBSERVED', 'admission_id': 'a' * 64, 'source_sha256': '1' * 64,
            'correlation': {}, 'admitted_utc': 1.0}
    status = {'requests': {'m1_0001_aaaaaaaaaaaaaaaa': good, 'm1_0002_bbbbbbbbbbbbbbbb': {'state': 'PASS_READBACK'}}}
    assert app.pending_request(status)[0] == 'm1_0001_aaaaaaaaaaaaaaaa'
    for request_id, entry in [('m1_0001_aaaa; rm -rf x', good), ('m1_0001_aaaaaaaaaaaaaaaa',
                                                                  {**good, 'admission_id': '../x'})]:
        with pytest.raises(app.SessionError, match='VALID_PENDING_ADMISSION_REQUIRED'):
            app.pending_request({'requests': {request_id: entry}})


# ------------------------------------------------------------------- parent

@pytest.fixture
def parent(admission_rig, tmp_path):
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'readback').mkdir()
    service = session.ParentAdmissions(run, consumer=admission_rig.consumer, ledger=admission_rig.ledger,
                                       child=admission_rig.child, window_id=admission_rig.jobs[0]['window_id'],
                                       operations=operations, readback_dir=run / 'readback')
    return SimpleNamespace(rig=admission_rig, run=run, service=service)


def finish(parent, request_id, success=True):
    session.new_json(parent.run / f'{request_id}.finished.json', {
        'request_id': request_id, 'pid': parent.rig.child.identity.pid, 'success': success,
        'response_sha256': 'b' * 64})


def trusted_readback(parent, name, **value):
    session.new_json(parent.run / 'readback' / f'{name}.readback.json', value)


def child_request(parent, job, number=1, **changes):
    facts = {key: job[key] for key in operations.FACT_KEYS}
    request_id = f'm1_{number:04d}_{"a" * 16}'
    value = {'request_id': request_id, 'pid': parent.rig.child.identity.pid, 'request_sha256': 'f' * 64,
             'facts': facts, 'correlation': {}}
    value.update(changes)
    session.new_json(parent.run / f'{request_id}.request.json', value)
    return request_id


def receipt(parent, name):
    path = parent.run / name
    return json.loads(path.read_bytes()) if path.exists() else None


def test_exact_request_is_durably_charged_before_admission_receipt(parent):
    job = parent.rig.jobs[0]
    request_id = child_request(parent, job)
    parent.service.service()
    admitted = receipt(parent, f'{request_id}.admitted.json')
    assert admitted['job_id'] == job['job_id'] and admitted['operation_id'] == job['operation_id']
    assert parent.rig.ledger.states[job['job_id']] == 'ATTEMPT_INTENT'
    assert admitted['admission_id'].encode() in (parent.rig.ledger.directory / 'LEDGER.jsonl').read_bytes()
    assert parent.rig.supervisor.state == 'BUSY'


def test_unapproved_or_changed_facts_are_refused_without_any_charge(parent):
    job = parent.rig.jobs[0]
    facts = {key: job[key] for key in operations.FACT_KEYS}
    request_id = child_request(parent, job, facts={**facts, 'source_sha256': '0' * 64})
    parent.service.service()
    assert receipt(parent, f'{request_id}.refused.json')['code'] == 'UNAPPROVED_OR_CONSUMED_OPERATION'
    assert parent.rig.ledger.attempts == 0 and parent.rig.supervisor.jobs_started == 0
    assert parent.service.stop_reason is None


def test_foreign_process_request_stops_the_session_without_charge(parent):
    request_id = child_request(parent, parent.rig.jobs[0], pid=99999)
    parent.service.service()
    assert parent.service.stop_reason == 'REQUEST_IDENTITY_CHANGED'
    assert receipt(parent, f'{request_id}.admitted.json') is None and parent.rig.ledger.attempts == 0


def test_full_cycle_response_then_trusted_readback_then_next_admission(parent):
    first, second = parent.rig.jobs[:2]
    request_id = child_request(parent, first)
    parent.service.service()
    admitted = receipt(parent, f'{request_id}.admitted.json')
    blocked = child_request(parent, second, number=2)
    session.new_json(parent.run / f'{request_id}.finished.json', {
        'request_id': request_id, 'pid': parent.rig.child.identity.pid, 'success': True,
        'response_sha256': 'b' * 64})
    parent.service.service()
    assert parent.rig.ledger.states[first['job_id']] == 'RESPONSE_RETAINED'
    # Readback is still pending: the next operation is refused, never queued.
    assert receipt(parent, f'{blocked}.refused.json')['code'] == 'ADMISSION_BUSY_READBACK_PENDING_OR_CLOSED'
    # A readback receipt in the child-writable run directory is never trusted.
    session.new_json(parent.run / f'{request_id}.readback.json', {
        'request_id': request_id, 'admission_id': admitted['admission_id'], 'readback_sha256': 'c' * 64,
        'matches': True})
    parent.service.service()
    assert parent.rig.ledger.states[first['job_id']] == 'RESPONSE_RETAINED'
    trusted_readback(parent, request_id, request_id=request_id, admission_id=admitted['admission_id'],
                     readback_sha256='c' * 64, matches=True)
    parent.service.service()
    assert parent.rig.ledger.states[first['job_id']] == 'PASS_READBACK'
    third = child_request(parent, second, number=3)
    parent.service.service()
    assert receipt(parent, f'{third}.admitted.json')['job_id'] == second['job_id']
    status = parent.service.status(budget=parent.rig.budget, supervisor=parent.rig.supervisor, started=0)
    assert status['accounting']['global_used'] == 527 and status['automatic_retries'] == 0


def test_failed_response_consumes_once_and_stops_without_retry(parent):
    job = parent.rig.jobs[0]
    request_id = child_request(parent, job)
    parent.service.service()
    session.new_json(parent.run / f'{request_id}.finished.json', {
        'request_id': request_id, 'pid': parent.rig.child.identity.pid, 'success': False,
        'response_sha256': 'b' * 64})
    parent.service.service()
    assert parent.rig.ledger.states[job['job_id']] == 'FAILED_NO_RETRY'
    assert parent.service.stop_reason == 'REQUEST_FAILED_NO_RETRY'
    assert parent.rig.supervisor.state == 'DRAINING'
    again = child_request(parent, job, number=2)
    parent.service.service()
    assert receipt(parent, f'{again}.admitted.json') is None


def test_abandoned_handoff_is_uncertain_consumed_and_closes_admission(parent):
    job = parent.rig.jobs[0]
    request_id = child_request(parent, job)
    parent.service.service()
    session.new_json(parent.run / f'{request_id}.abandoned.json', {'request_id': request_id,
                                                                   'pid': parent.rig.child.identity.pid})
    parent.service.service()
    assert parent.rig.ledger.states[job['job_id']] == 'SENT_OR_UNCERTAIN'
    assert parent.service.stop_reason == 'ADMISSION_HANDOFF_UNCERTAIN' and parent.rig.consumer.poisoned


def test_readback_for_another_admission_is_rejected(parent):
    job = parent.rig.jobs[0]
    request_id = child_request(parent, job)
    parent.service.service()
    session.new_json(parent.run / f'{request_id}.finished.json', {
        'request_id': request_id, 'pid': parent.rig.child.identity.pid, 'success': True,
        'response_sha256': 'b' * 64})
    parent.service.service()
    trusted_readback(parent, request_id, request_id=request_id, admission_id='0' * 64,
                     readback_sha256='c' * 64, matches=True)
    parent.service.service()
    assert parent.service.stop_reason == 'READBACK_IDENTITY_CHANGED'
    assert parent.rig.ledger.states[job['job_id']] == 'RESPONSE_RETAINED'


@pytest.mark.parametrize('bad', [{'matches': 'yes'}, {'readback_sha256': 'not-a-digest'}, {'extra': 1}])
def test_malformed_trusted_readback_stops_cleanly_without_crashing_the_parent(parent, bad):
    job = parent.rig.jobs[0]
    request_id = child_request(parent, job)
    parent.service.service()
    admitted = receipt(parent, f'{request_id}.admitted.json')
    finish(parent, request_id)
    parent.service.service()
    value = {'request_id': request_id, 'admission_id': admitted['admission_id'], 'readback_sha256': 'c' * 64,
             'matches': True, **bad}
    trusted_readback(parent, request_id, **value)
    parent.service.service()  # Must not raise out of the service loop.
    assert parent.service.stop_reason == 'READBACK_IDENTITY_CHANGED'
    assert parent.rig.ledger.states[job['job_id']] == 'RESPONSE_RETAINED'


def test_uncertain_prism_outcome_is_consumed_as_uncertain_never_as_model_failure(parent):
    job = parent.rig.jobs[0]
    request_id = child_request(parent, job)
    parent.service.service()
    session.new_json(parent.run / f'{request_id}.uncertain.json', {'request_id': request_id,
                                                                   'pid': parent.rig.child.identity.pid})
    parent.service.service()
    assert parent.rig.ledger.states[job['job_id']] == 'SENT_OR_UNCERTAIN'
    assert parent.service.stop_reason == 'MODEL_OUTCOME_UNCERTAIN'


# -------------------------------------------------------------------- child

class FakeApp:
    def __init__(self, status=200, body=b'{"ok":true}'):
        self.calls, self.status, self.body = [], status, body

    async def __call__(self, scope, receive, send):
        message = await receive() if scope['type'] == 'http' else None
        self.calls.append((scope['type'], scope.get('path'), message and message.get('body')))
        if scope['type'] == 'lifespan':
            await send({'type': 'lifespan.startup.complete'})
            return
        await send({'type': 'http.response.start', 'status': self.status, 'headers': []})
        await send({'type': 'http.response.body', 'body': self.body})


class FakeHost:
    def __init__(self, models):
        from threading import RLock
        self.lock, self.models = RLock(), models
        self.tickets = {'ticket_0001': SimpleNamespace(owner=session.PRISM_PRINCIPAL)}
        self.jobs, self.validated = {}, []
        self.consumed_tickets, self.consumed_plans, self.consumed_ids = set(), set(), set()

    def _validate(self, ticket, binding, plan):
        self.validated.append(plan)

    def _status(self, job):
        return {'state': job.state, 'result': {'lesions': []} if job.state == 'COMPLETE' else None, 'error': None}


def call(app, method, path, body=b''):
    sent = []

    async def receive():
        return {'type': 'http.request', 'body': body, 'more_body': False}

    async def send(message):
        sent.append(message)

    async def run():
        await app({'type': 'http', 'method': method, 'path': path, 'headers': []}, receive, send)
        await asyncio.sleep(0)
    asyncio.run(run())
    start = next(message for message in sent if message['type'] == 'http.response.start')
    return start['status'], b''.join(message.get('body', b'') for message in sent
                                     if message['type'] == 'http.response.body')


@pytest.fixture
def child(tmp_path, monkeypatch):
    models = reviewed(monkeypatch)
    run = tmp_path / 'child-run'
    run.mkdir()
    model_app, prism_app = FakeApp(), FakeApp(status=202, body=b'{"job_id":"job_0001"}')
    host = FakeHost(models)
    value = session.ChildAdmission(model_app=model_app, prism_app=prism_app, host=host, models=models,
                                   run=run, operations=operations, ack_seconds=.3, poll_seconds=.005)
    return SimpleNamespace(app=value, run=run, model_app=model_app, prism_app=prism_app, host=host, models=models)


def global_body(models, image=b'synthetic-jpeg-bytes', model_id='retfound-aptos5', modality='CFP'):
    return json.dumps({'model_id': model_id, 'modality': modality, 'image_sha256': sha(image),
                       'image_b64': base64.b64encode(image).decode(), 'image_id': 'img', 'source_type': 'SYNTHETIC',
                       'width': 1, 'height': 1}).encode()


def auto_parent(child, decision='admitted'):
    """Thread standing in for the parent: answers each request receipt once."""
    import threading
    stop = threading.Event()

    def loop():
        answered = set()
        while not stop.is_set():
            for path in child.run.glob('m1_*.request.json'):
                request_id = path.name[:-len('.request.json')]
                if request_id not in answered:
                    value = json.loads(path.read_bytes())
                    payload = {'request_id': request_id, 'pid': value['pid']}
                    if decision == 'admitted':
                        payload.update(admission_id='a' * 64, job_id='j' * 64, operation_id='op')
                    else:
                        payload['code'] = 'UNAPPROVED_OR_CONSUMED_OPERATION'
                    session.new_json(child.run / f'{request_id}.{decision}.json', payload)
                    answered.add(request_id)
            stop.wait(.005)
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return stop


def test_control_and_discovery_routes_pass_without_any_admission(child):
    assert call(child.app, 'GET', '/v1/models')[0] == 200
    assert call(child.app, 'POST', '/v1/prism-bound/prepare', b'{}')[0] == 202
    assert call(child.app, 'POST', '/v1/prism-bound/jobs/job_0001234/grant', b'{}')[0] == 202
    assert not list(child.run.iterdir())


@pytest.mark.parametrize('path', ['/v1/predict/lesions', '/v2/predict/dr', '/v2/predict/lesions', '/admin'])
def test_routes_outside_the_session_scope_are_refused(child, path):
    assert call(child.app, 'POST', path, b'{}')[0] == 405
    assert not child.model_app.calls and not list(child.run.iterdir())


def test_global_request_dispatches_only_after_parent_admission(child):
    stop = auto_parent(child)
    try:
        status, _ = call(child.app, 'POST', '/v1/predict/dr', global_body(child.models))
    finally:
        stop.set()
    assert status == 200 and len(child.model_app.calls) == 1
    request = json.loads(next(child.run.glob('*.request.json')).read_bytes())
    assert request['facts'] == operations.facts(child.models, source_sha256=sha(b'synthetic-jpeg-bytes'),
                                                model_id='retfound-aptos5', modality='CFP')
    finished = json.loads(next(child.run.glob('*.finished.json')).read_bytes())
    assert finished['success'] is True and not child.app.busy


def test_parent_refusal_never_dispatches(child):
    stop = auto_parent(child, decision='refused')
    try:
        status, body = call(child.app, 'POST', '/v1/predict/dr', global_body(child.models))
    finally:
        stop.set()
    assert status == 409 and b'UNAPPROVED_OR_CONSUMED_OPERATION' in body
    assert not child.model_app.calls and not list(child.run.glob('*.finished.json'))


def test_missing_parent_ack_marks_uncertain_handoff_and_never_dispatches(child):
    status, body = call(child.app, 'POST', '/v1/predict/dr', global_body(child.models))
    assert status == 409 and b'NO_PARENT_ADMISSION_NO_DISPATCH' in body
    assert list(child.run.glob('*.abandoned.json')) and not child.model_app.calls


@pytest.mark.parametrize('change', ['hash', 'model', 'modality'])
def test_invalid_global_envelope_is_refused_before_admission(child, change):
    body = json.loads(global_body(child.models))
    if change == 'hash': body['image_sha256'] = '0' * 64
    elif change == 'model': body['model_id'] = 'prism-dr-5fold'
    else: body['modality'] = 'UWF'
    status, _ = call(child.app, 'POST', '/v1/predict/dr', json.dumps(body).encode())
    assert status == 409 and not list(child.run.iterdir()) and not child.model_app.calls


def prism_body(child, **binding_changes):
    binding = {'source_sha256': '3' * 64, 'modality': 'UWF', 'scope': 'scope', 'image_id': 'image',
               'plan_id': 'plan_0001', 'model_pins': child.models['prism-dr-5fold']['pins'], **binding_changes}
    return json.dumps({'ticket_id': 'ticket_0001', 'binding': binding, 'plan_sha256': '9' * 64}).encode()


@pytest.mark.parametrize('terminal', ['COMPLETE', 'FAILED'])
def test_prism_execute_is_validated_admitted_and_finished_at_terminal_state(child, terminal):
    job = SimpleNamespace(state='WAITING_SOURCE_FENCE', deadline=10 ** 9)
    original = child.prism_app

    async def execute(scope, receive, send):
        # The real host registers the job while answering execute with 202.
        child.host.jobs['job_0001'] = job
        await original(scope, receive, send)
    child.app.prism_app = execute
    observed = {}

    async def scenario():
        sent = []

        async def receive():
            return {'type': 'http.request', 'body': prism_body(child), 'more_body': False}

        async def send(message):
            sent.append(message)
        await child.app({'type': 'http', 'method': 'POST', 'path': '/v1/prism-bound/execute', 'headers': []},
                        receive, send)
        observed['status'] = sent[0]['status']
        await asyncio.sleep(.05)
        observed['finished_after_202'] = list(child.run.glob('*.finished.json'))
        observed['busy_after_202'] = child.app.busy
        job.state = terminal
        for _ in range(200):
            if not child.app.busy:
                break
            await asyncio.sleep(.01)
    stop = auto_parent(child)
    try:
        asyncio.run(scenario())
    finally:
        stop.set()
    assert observed == {'status': 202, 'finished_after_202': [], 'busy_after_202': True}
    value = json.loads(next(child.run.glob('*.finished.json')).read_bytes())
    assert value['success'] is (terminal == 'COMPLETE') and child.host.validated == ['9' * 64]
    assert not child.app.busy


def test_prism_with_unreviewed_pins_or_busy_host_is_refused_before_admission(child):
    status, body = call(child.app, 'POST', '/v1/prism-bound/execute',
                        prism_body(child, model_pins={'model_id': 'prism-dr-5fold'}))
    assert status == 409 and b'PRISM_REVIEWED_PINS_REQUIRED' in body
    child.host.jobs['job_live'] = SimpleNamespace(state='FORWARD_STARTED')
    status, body = call(child.app, 'POST', '/v1/prism-bound/execute', prism_body(child))
    assert status == 409 and b'PRISM_TICKET_OR_IDLE_HOST_REQUIRED' in body
    assert not list(child.run.iterdir()) and not child.prism_app.calls


@pytest.mark.parametrize('drift', ['consumed_ticket', 'consumed_plan', 'consumed_id', 'foreign_owner'])
def test_replayed_or_foreign_prism_plan_is_refused_before_any_charge(child, drift):
    if drift == 'consumed_ticket': child.host.consumed_tickets.add('ticket_0001')
    elif drift == 'consumed_plan': child.host.consumed_plans.add('9' * 64)
    elif drift == 'consumed_id': child.host.consumed_ids.add(('scope', 'image', 'plan_0001'))
    else: child.host.tickets['ticket_0001'].owner = 'other-principal'
    status, _ = call(child.app, 'POST', '/v1/prism-bound/execute', prism_body(child))
    assert status == 409 and not list(child.run.iterdir()) and not child.prism_app.calls


def test_prism_job_still_running_after_deadline_is_uncertain_and_keeps_admission_closed(child):
    child.app.clock = lambda: 10.0 ** 9  # Already past the job deadline.
    job = SimpleNamespace(state='FORWARD_STARTED', deadline=0)
    original = child.prism_app

    async def execute(scope, receive, send):
        child.host.jobs['job_0001'] = job
        await original(scope, receive, send)
    child.app.prism_app = execute
    child.app.ack_seconds = 10.0 ** 10  # Fake clock: rely on the auto parent, not the deadline.
    stop = auto_parent(child)

    async def scenario():
        async def receive():
            return {'type': 'http.request', 'body': prism_body(child), 'more_body': False}

        async def send(message):
            pass
        await child.app({'type': 'http', 'method': 'POST', 'path': '/v1/prism-bound/execute', 'headers': []},
                        receive, send)
        for _ in range(100):
            if list(child.run.glob('*.uncertain.json')):
                break
            await asyncio.sleep(.01)
    try:
        asyncio.run(scenario())
    finally:
        stop.set()
    assert list(child.run.glob('*.uncertain.json')) and not list(child.run.glob('*.finished.json'))
    assert child.app.busy  # Possibly still forwarding: no further admission from this child.


def test_second_charged_request_while_busy_is_rejected_without_receipt(child):
    child.app.busy = True
    status, _ = call(child.app, 'POST', '/v1/predict/dr', global_body(child.models))
    assert status == 429 and not list(child.run.iterdir())


def test_lifespan_ready_callback_follows_actual_prism_startup(child):
    ready = []
    child.app.ready_callback = lambda: ready.append(True)

    async def run():
        async def receive():
            return {'type': 'lifespan.startup'}

        async def send(message):
            assert ready == [True]
        await child.app({'type': 'lifespan'}, receive, send)
    asyncio.run(run())
    assert ready == [True]
