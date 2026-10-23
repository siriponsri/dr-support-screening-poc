"""Real durable ledger/budget with fake clock/owned child; no GPU or service."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import importlib
from types import SimpleNamespace

import pytest

from scripts.qa.worker_supervisor import ChildIdentity, Observation, Policy, WorkerSupervisor
from test_m1_accounting_continuation import (
    rig as _accounting_rig, upstream_seed as _upstream_seed, activate, owned,
    BatchBudget, M1_GPU0, M1_SERVER,
)

accounting_rig = _accounting_rig
upstream_seed = _upstream_seed
module = importlib.import_module('m1_admission')


class Child:
    atomic_identity_signals = True

    def __init__(self, clock):
        self.clock, self.signals = clock, []
        self.identity = ChildIdentity(2345, 1234, 'synthetic_birth_marker_0001',
            'hospital_m1_synthetic_worker', 'd' * 64, 'prism-dr-5fold')

    def observe(self):
        return Observation(self.identity, True, self.clock(), 0, M1_GPU0, 100, 1024, 1024,
                           gpu_observed_at=self.clock())

    def signal_verified(self, expected, *, force):
        assert expected == self.identity
        self.signals.append(force)  # No actual signal/PID operation.


@pytest.fixture
def rig(accounting_rig):
    source = accounting_rig
    ledger = owned(source)
    activate(source, ledger)
    budget = BatchBudget(ledger, session_id=M1_SERVER, clock_origin=source.origin,
                         clock=lambda: source.now[0], utc=lambda: source.utc[0])
    budget.reserve_worker('synthetic_owned_lease')
    child = Child(lambda: source.now[0])
    supervisor = WorkerSupervisor(Policy('prism-dr-5fold', 1234, child.identity.owner_scope,
        child.identity.command_sha256, M1_GPU0, max_jobs=18, max_seconds=2400, monitor_seconds=1),
        child, clock=lambda: source.now[0])
    consumer = module.M1AdmissionConsumer(ledger, budget, supervisor, child=child,
                                         lease_id='synthetic_owned_lease')
    jobs = [row for row in ledger.jobs.values() if row['window_id'] == M1_SERVER]
    return SimpleNamespace(source=source, ledger=ledger, budget=budget, child=child,
        supervisor=supervisor, consumer=consumer, jobs=jobs)


def admit(rig, job=None, **changes):
    job = job or rig.jobs[0]
    values = dict(request_id='synthetic_request_0001', request_sha256='f' * 64,
                  facts={key: job[key] for key in module.FACTS}, identity=rig.child.identity)
    return rig.consumer.admit(job['job_id'], **(values | changes))


def test_durable_intent_precedes_native_admission_and_same_id_is_used(rig, monkeypatch):
    original = rig.supervisor.admit
    observed = []

    def native(admission_id):
        assert rig.ledger.states[rig.jobs[0]['job_id']] == 'ATTEMPT_INTENT'
        assert admission_id.encode() in (rig.ledger.directory / 'LEDGER.jsonl').read_bytes()
        rig.ledger.assert_owner()  # Valid high-water receipt already persisted.
        observed.append(admission_id)
        original(admission_id)

    monkeypatch.setattr(rig.supervisor, 'admit', native)
    proof = admit(rig)
    assert observed == [proof['admission_id']]
    assert proof['global_used'] == 526 and rig.supervisor.jobs_started == 1
    assert rig.consumer.status()['counter_source'] == 'EXISTING_BATCH_LEDGER'
    assert rig.budget.body['lease_count'] == 1 and rig.budget.body['charged_gpu_seconds'] == 10800
    assert all(path.read_bytes() == rig.source.originals[key] for key, path in rig.source.paths.items())


@pytest.mark.parametrize('field', sorted(module.FACTS))
def test_changed_prepared_operation_fact_never_charges_or_admits(rig, field):
    facts = {key: rig.jobs[0][key] for key in module.FACTS}
    facts[field] = 'unapproved-change'
    with pytest.raises(RuntimeError, match='OUTSIDE_FROZEN_OPERATION'):
        admit(rig, facts=facts)
    assert rig.ledger.attempts == 0 and rig.supervisor.jobs_started == 0


def test_other_child_identity_is_rejected_before_intent(rig):
    with pytest.raises(RuntimeError, match='OWNED_CHILD_IDENTITY'):
        admit(rig, identity=replace(rig.child.identity, birth_marker='different_birth_marker'))
    assert rig.ledger.attempts == 0


def test_concurrent_calls_only_one_durable_intent_and_native_admission(rig):
    def attempt(index):
        try:
            return admit(rig, rig.jobs[index], request_id=f'synthetic_request_{index}')
        except RuntimeError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (0, 1)))
    assert sum(result is not None for result in results) == 1
    assert rig.ledger.attempts == rig.supervisor.jobs_started == 1


def test_intent_io_failure_does_not_authorize_native_dispatch(rig, monkeypatch):
    def fail(*_):
        raise OSError('synthetic fsync failure')

    monkeypatch.setattr(rig.ledger, '_write_head', fail)
    with pytest.raises(OSError):
        admit(rig)
    assert rig.supervisor.jobs_started == 0 and rig.ledger.poisoned
    status = rig.consumer.status()
    assert status['global_used'] is None and status['usage_status'] == 'UNCERTAIN'
    assert status['global_used_at_least'] == 525
    assert b'ATTEMPT_INTENT' in (rig.ledger.directory / 'LEDGER.jsonl').read_bytes()


def test_native_admission_failure_consumes_without_replay(rig, monkeypatch):
    def fail(*_):
        raise RuntimeError('synthetic native supervisor refusal')

    monkeypatch.setattr(rig.supervisor, 'admit', fail)
    with pytest.raises(RuntimeError, match='native supervisor refusal'):
        admit(rig)
    assert rig.ledger.attempts == 1 and rig.consumer.poisoned
    assert rig.ledger.states[rig.jobs[0]['job_id']] == 'SENT_OR_UNCERTAIN'
    with pytest.raises(RuntimeError):
        admit(rig, rig.jobs[1])


def test_model_response_waits_for_independent_readback_and_terminal_id_never_replays(rig):
    proof = admit(rig)
    result = rig.consumer.record_response(proof['admission_id'], response_sha256='a' * 64, success=True)
    assert result == dict(inference='MODEL_COMPLETE', accounting='PASS', supervision='PASS', persistence='PENDING')
    assert rig.ledger.states[rig.jobs[0]['job_id']] == 'RESPONSE_RETAINED'
    with pytest.raises(RuntimeError):
        admit(rig, rig.jobs[1])
    saved = rig.consumer.acknowledge_readback(proof['admission_id'], readback_sha256='b' * 64, matches=True)
    assert saved['persistence'] == 'PASS' and rig.ledger.states[rig.jobs[0]['job_id']] == 'PASS_READBACK'
    with pytest.raises(RuntimeError):
        admit(rig)
    assert rig.ledger.attempts == 1


def test_persistence_failure_is_distinct_from_successful_inference(rig):
    proof = admit(rig)
    rig.consumer.record_response(proof['admission_id'], response_sha256='a' * 64, success=True)
    saved = rig.consumer.acknowledge_readback(proof['admission_id'], readback_sha256='b' * 64, matches=False)
    assert saved['inference'] == 'MODEL_COMPLETE' and saved['persistence'] == 'FAILED'
    assert rig.ledger.states[rig.jobs[0]['job_id']] == 'FAILED_PERSISTENCE'
    assert rig.ledger.attempts == 1 and rig.child.signals == []


@pytest.mark.parametrize('stage', ['response', 'readback'])
def test_logging_failure_preserves_actual_model_or_db_outcome_and_closes_admission(rig, monkeypatch, stage):
    proof = admit(rig)
    actual_result = {'synthetic_model_result': 'preserve actual returned value'}
    before = deepcopy(actual_result)
    if stage == 'readback':
        rig.consumer.record_response(proof['admission_id'], response_sha256='a' * 64, success=True)

    def fail(*a, **k):
        raise OSError('synthetic accounting receipt failure')

    monkeypatch.setattr(rig.ledger, 'append', fail)
    outcome = (rig.consumer.record_response(proof['admission_id'], response_sha256='a' * 64, success=True)
               if stage == 'response' else
               rig.consumer.acknowledge_readback(proof['admission_id'], readback_sha256='b' * 64, matches=True))
    assert outcome['inference'] == 'MODEL_COMPLETE' and outcome['accounting'] == 'BLOCKED'
    assert stage != 'readback' or outcome['persistence'] == 'PASS'
    assert actual_result == before and rig.consumer.poisoned and rig.ledger.attempts == 1
    with pytest.raises(RuntimeError):
        admit(rig, rig.jobs[1])


def test_uncertain_ack_retains_consumed_intent_and_blocks_all_new_calls(rig):
    proof = admit(rig)
    rig.consumer.ack_failed(proof['admission_id'])
    assert rig.ledger.states[rig.jobs[0]['job_id']] == 'SENT_OR_UNCERTAIN'
    with pytest.raises(RuntimeError):
        admit(rig, rig.jobs[1])
    assert rig.ledger.attempts == 1


@pytest.mark.parametrize('matches', [True, False])
def test_response_log_failure_still_reports_subsequent_actual_readback(rig, monkeypatch, matches):
    proof = admit(rig)
    calls = []

    def fail(*a, **k):
        calls.append(a)
        raise OSError('synthetic response log failure')

    monkeypatch.setattr(rig.ledger, 'append', fail)
    received = rig.consumer.record_response(proof['admission_id'], response_sha256='a' * 64, success=True)
    assert received['accounting'] == 'BLOCKED'
    readback = rig.consumer.acknowledge_readback(proof['admission_id'], readback_sha256='b' * 64, matches=matches)
    assert readback == dict(inference='MODEL_COMPLETE', persistence='PASS' if matches else 'FAILED',
                           accounting='BLOCKED', automatic_retries=0)
    assert len(calls) == 1  # Never invent a missing retained-response transition.
    assert rig.consumer.poisoned and rig.ledger.attempts == 1
    with pytest.raises(RuntimeError):
        admit(rig, rig.jobs[1])
