"""Synthetic accounting/dispatch tests; no real model, network or GPU calls."""
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from scripts.qa.private_gateway_auth import PrivateGatewayAuth


spec = importlib.util.spec_from_file_location(
    'demo_session', Path(__file__).parents[1] / 'scripts/model-server/demo_session.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


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
        assert j.claim('uspec-uwf-grading', f'{i:064x}', b'wire')
    assert not j.claim('prism-dr-5fold', 'f' * 64, b'wire')
    assert j.status()['global_used'] == 529
    assert prior == original
    rows = [json.loads(line) for line in j.path.read_bytes().splitlines()]
    assert [r['global_used'] for r in rows[1:]] == [526, 527, 528, 529]


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
