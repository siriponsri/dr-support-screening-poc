"""Synthetic accounting/dispatch tests; no real model, network or GPU calls."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from threading import Event, Thread

import pytest

from scripts.qa.private_gateway_auth import PrivateGatewayAuth


spec = importlib.util.spec_from_file_location(
    'demo_session', Path(__file__).parents[1] / 'scripts/model-server/demo_session.py')
demo = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = demo
spec.loader.exec_module(demo)


def test_receipt_is_invisible_until_complete_and_never_replaces(tmp_path, monkeypatch):
    target = tmp_path / 'request.admitted.json'
    prepared, release = Event(), Event()
    link = demo.os.link
    errors = []

    def paused_link(source, destination):
        # The final name must remain absent while a writer is in progress.
        assert json.loads(Path(source).read_bytes()) == {'request': 'complete'}
        prepared.set()
        assert release.wait(5)
        link(source, destination)

    def publish():
        try:
            demo.new_json(target, {'request': 'complete'})
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(demo.os, 'link', paused_link)
    writer = Thread(target=publish)
    writer.start()
    try:
        assert prepared.wait(5)
        assert not target.exists()
    finally:
        release.set()
        writer.join(5)
    assert not writer.is_alive() and not errors
    assert json.loads(target.read_bytes()) == {'request': 'complete'}
    monkeypatch.setattr(demo.os, 'link', link)
    with pytest.raises(FileExistsError):
        demo.new_json(target, {'request': 'replacement'})
    assert json.loads(target.read_bytes()) == {'request': 'complete'}
    assert not list(tmp_path.glob('*.pending'))


@pytest.fixture
def prior():
    rows, previous = [], '0' * 64
    for job in range(476):
        for state in ('ATTEMPT_INTENT', 'PASS_READBACK'):
            body = {'seq': len(rows) + 1, 'previous': previous, 'state': state, 'job_id': str(job)}
            row = {**body, 'hash': demo.sha(demo.canonical(body))}
            rows.append(row)
            previous = row['hash']
    return b''.join(demo.canonical(row) + b'\n' for row in rows)


def journal(tmp_path, prior):
    return demo.RequestJournal(tmp_path / 'requests.jsonl', prior_raw=prior,
                               expected_prior=demo.sha(prior))


def test_preserves_prior_and_consumes_only_four_before_dispatch(tmp_path, prior):
    original = bytes(prior)
    j = journal(tmp_path, prior)
    assert j.status()['global_used'] == 525
    for i in range(4):
        intent = j.claim('uspec-uwf-grading', f'{i:064x}', b'wire')
        assert intent
        j.terminal(intent, 200, 'a' * 64, complete=True)
    assert not j.claim('prism-dr-5fold', 'f' * 64, b'wire')
    assert j.status()['global_used'] == 529
    assert prior == original
    rows = [json.loads(line) for line in j.path.read_bytes().splitlines()]
    assert [r['global_used'] for r in rows if r['state'] == 'ATTEMPT_INTENT'] == [526, 527, 528, 529]


def test_duplicate_and_restart_do_not_restore_allowance(tmp_path, prior):
    j = journal(tmp_path, prior)
    assert j.claim('retfound-aptos5', 'a' * 64, b'wire')
    assert not j.claim('retfound-aptos5', 'a' * 64, b'wire')
    assert j.used == 526
    with pytest.raises(FileExistsError):
        journal(tmp_path, prior)


def test_tampered_or_incomplete_prior_is_rejected(tmp_path, prior):
    with pytest.raises(ValueError, match='PRIOR_LEDGER_CHANGED'):
        demo.RequestJournal(tmp_path / 'one', prior_raw=prior, expected_prior='0' * 64)
    rows = prior.splitlines()
    rows[-1] = rows[-1].replace(b'PASS_READBACK', b'ATTEMPT_INTENT')
    changed = b'\n'.join(rows) + b'\n'
    with pytest.raises(ValueError, match='CHAIN_INVALID'):
        demo.RequestJournal(tmp_path / 'two', prior_raw=changed, expected_prior=demo.sha(changed))


def dispatch(app, path, *, token='t' * 64, payload=None):
    messages = []
    async def run():
        body = demo.canonical(payload or {})
        async def receive():
            return {'type': 'http.request', 'body': body, 'more_body': False}
        async def send(value):
            messages.append(value)
        await app({'type': 'http', 'path': path, 'method': 'POST',
                   'headers': [(b'authorization', ('Bearer ' + token).encode())]}, receive, send)
    asyncio.run(run())
    return messages[0]['status']


def test_auth_and_duplicate_never_dispatch_and_no_automatic_retry(tmp_path, prior):
    j, calls = journal(tmp_path, prior), []
    async def downstream(scope, receive, send):
        calls.append(await receive())
        await send({'type': 'http.response.start', 'status': 503, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'blocked'})
    app = PrivateGatewayAuth(demo.QuotaApplication(downstream, j, stop=lambda: None,
                                                  metadata=lambda: {}), 't' * 64)
    payload = {'model_id': 'prism-dr-5fold', 'image_sha256': 'a' * 64}
    assert dispatch(app, '/v2/predict/lesions', token='wrong', payload=payload) == 401
    assert j.used == 525
    assert dispatch(app, '/v2/predict/lesions', payload=payload) == 503
    assert dispatch(app, '/v2/predict/lesions', payload=payload) == 409
    assert len(calls) == 1 and j.used == 526


def test_terminal_logging_failure_preserves_model_response_and_quarantines(tmp_path, prior, monkeypatch):
    j = journal(tmp_path, prior)
    real_write = j._write
    def write(stream, value):
        if value['state'] == 'HTTP_RESPONSE':
            raise OSError('simulated log outage')
        real_write(stream, value)
    monkeypatch.setattr(j, '_write', write)
    async def downstream(scope, receive, send):
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'actual returned payload'})
    app = demo.QuotaApplication(downstream, j, stop=lambda: None, metadata=lambda: {})
    payload = {'model_id': 'retfound-aptos5', 'image_sha256': 'b' * 64}
    assert dispatch(app, '/v1/predict/dr', payload=payload) == 200
    assert j.used == 526 and j.status()['logging_blocked']
    assert not j.claim('uspec-uwf-grading', 'c' * 64, b'wire')


def test_terminal_identity_and_incomplete_delivery_are_preserved(tmp_path, prior):
    j = journal(tmp_path, prior)
    intent = j.claim('uspec-uwf-grading', 'c' * 64, b'wire')
    assert not j.claim('retfound-aptos5', 'd' * 64, b'other')
    wrong = demo.Intent('wrong', intent.model_id, intent.image_sha256,
                        intent.request_sha256, intent.global_used)
    with pytest.raises(ValueError, match='NO_MATCHING'):
        j.terminal(wrong, 200, 'e' * 64, complete=True)
    j.terminal(intent, 200, 'e' * 64, complete=False)
    row = json.loads(j.path.read_bytes().splitlines()[-1])
    assert row['id'] == intent.id and row['model_id'] == intent.model_id
    assert row['image_sha256'] == 'c' * 64 and row['global_used'] == 526
    assert not row['response_complete'] and j.poisoned


def test_busy_request_rejected_before_reservation(tmp_path, prior):
    j = journal(tmp_path, prior)
    app = demo.QuotaApplication(None, j, stop=lambda: None, metadata=lambda: {})
    app.busy.acquire()
    try:
        assert dispatch(app, '/v1/predict/dr', payload={}) == 429
    finally:
        app.busy.release()
    assert j.used == 525


def test_absolute_upload_deadline_never_dispatches_or_consumes(tmp_path, prior):
    j, messages = journal(tmp_path, prior), []
    app = demo.QuotaApplication(None, j, stop=lambda: None, metadata=lambda: {}, upload_seconds=.01)
    async def run():
        async def receive():
            await asyncio.sleep(.03)
            return {'type': 'http.request', 'body': b'{}'}
        async def send(message):
            messages.append(message)
        await app({'type': 'http', 'method': 'POST', 'path': '/v1/predict/dr'}, receive, send)
    asyncio.run(run())
    assert messages[0]['status'] == 408 and j.used == 525


def test_no_native_ack_means_no_model_dispatch(tmp_path, prior):
    j = journal(tmp_path, prior)
    app = demo.QuotaApplication(None, j, stop=lambda: None, metadata=lambda: {},
                               admission=demo.WorkerAdmission(tmp_path, seconds=.01))
    payload = {'model_id': 'retfound-aptos5', 'image_sha256': 'e' * 64}
    assert dispatch(app, '/v1/predict/dr', payload=payload) == 503
    assert j.used == 526 and j.poisoned
    assert len(list(tmp_path.glob('*.request.json'))) == 1


def test_parent_admission_engages_existing_native_request_watchdog(tmp_path):
    from scripts.qa.worker_supervisor import ChildIdentity, Observation, Policy, WorkerSupervisor
    now, signals = [100.0], []
    identity = ChildIdentity(os.getpid(), 999, 'boot:1234567890123456',
                             'synthetic_parent_scope', 'a' * 64, 'prism-dr-5fold')
    child = SimpleNamespace(identity=identity, atomic_identity_signals=True)
    child.observe = lambda: Observation(identity, True, now[0], 0, demo.GPU, 1, 1024, 1024)
    child.signal_verified = lambda expected, force: signals.append((expected, force))
    policy = Policy('prism-dr-5fold', 999, identity.owner_scope, 'a' * 64, demo.GPU,
                    max_jobs=4, max_seconds=100, request_seconds=1)
    supervisor = WorkerSupervisor(policy, child, clock=lambda: now[0])
    intent = demo.Intent('req_526_example', 'prism-dr-5fold', 'a' * 64, 'b' * 64, 526)
    demo.new_json(tmp_path / f'{intent.id}.request.json', {**demo.asdict(intent), 'pid': os.getpid()})
    demo.service_admissions(tmp_path, child, supervisor, set(), set())
    assert supervisor.state == 'BUSY' and supervisor.jobs_started == 1
    assert (tmp_path / f'{intent.id}.admitted.json').is_file()
    now[0] += 1.1
    supervisor.tick()
    assert supervisor.reason == 'REQUEST_TIMEOUT' and signals == [(identity, False)]


@pytest.mark.parametrize('failed', ['supervisor_close', 'child_terminal_reap', 'gpu_monitor', 'disk_monitor'])
def test_cleanup_attempts_all_components_after_one_failure(failed):
    attempted = []
    def close(name):
        attempted.append(name)
        if name == failed:
            raise OSError('synthetic failure')
    supervisor = SimpleNamespace(close=lambda: close('supervisor_close'))
    child = SimpleNamespace(inspect=lambda: False, close_confirmed=lambda: close('child_terminal_reap'))
    gpu = SimpleNamespace(close=lambda: close('gpu_monitor'))
    disk = SimpleNamespace(close=lambda: close('disk_monitor'))
    result = demo.cleanup_owned(child, supervisor, gpu, disk)
    assert attempted == ['supervisor_close', 'child_terminal_reap', 'gpu_monitor', 'disk_monitor']
    assert not result[failed]['confirmed']
    assert all(v['confirmed'] for k, v in result.items() if k != failed)
