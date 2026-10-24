"""Recorded source identity amendment, Part B: synthetic rows and a fake database only."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest

from dr_support.persistence import DatabaseUnavailableError
from scripts.qa import m1_recorded_source_projection as projection

WORKSPACE = 'ws_m1_63ed86c7d44f46d59479'
A, B, C, D = 'a' * 64, 'b' * 64, 'c' * 64, 'd' * 64


def payload(digest, **changes):
    value = {'image_id': digest, 'revision': 2, 'filename': 'private-name.png', 'events': [],
             'admission': {'image_id': digest, 'source_sha256': digest, 'integrity_status': 'OK',
                           'admission_method': 'AUTOMATIC',
                           'integrity': {'status': 'OK', 'changed_sources': []},
                           'trusted_patient_key': 'private-key'},
             'inference_history': [{'source_sha256': digest}]}
    value.update(changes)
    return value


class FakeDatabase:
    settings = SimpleNamespace(schema='app')

    def __init__(self, rows):
        self.rows = {case_id: (value['revision'], deepcopy(value)) for case_id, value in rows.items()}
        self.fenced = False
        self.trigger = True
        self.updates = 0
        self.fail_update = None   # 1-based UPDATE number that matches no row.
        self.sessions = 0
        self.fail_session = None  # 1-based session number that cannot connect.
        self.lose_commit = False

    @contextmanager
    def session(self, autocommit=True):
        self.sessions += 1
        if self.sessions == self.fail_session:
            raise DatabaseUnavailableError('synthetic')
        yield FakeConnection(self)


class FakeConnection:
    def __init__(self, database):
        self.database = database

    @contextmanager
    def transaction(self):
        snapshot = deepcopy(self.database.rows)
        try:
            yield
        except BaseException:
            self.database.rows = snapshot  # Rollback.
            raise
        if self.database.lose_commit:
            raise psycopg.OperationalError('synthetic connection lost during COMMIT')

    def execute(self, query, params=None):
        text = repr(query)
        if 'pg_trigger' in text:
            return SimpleNamespace(fetchone=lambda: (1,) if self.database.trigger else None)
        if 'SET revision' in text:
            if self.database.fenced:
                raise psycopg.errors.lookup('55000')('SOURCE_ENTRY_FENCED')
            self.database.updates += 1
            revision, value, _workspace, case_id, expected = params
            current = self.database.rows.get(case_id)
            if current is None or current[0] != expected or self.database.updates == self.database.fail_update:
                return SimpleNamespace(rowcount=0)
            self.database.rows[case_id] = (revision, deepcopy(value.obj))
            return SimpleNamespace(rowcount=1)
        if 'SELECT' in text:
            rows = [(case_id, revision, deepcopy(value)) for case_id, (revision, value)
                    in sorted(self.database.rows.items())]
            return SimpleNamespace(fetchall=lambda: rows)
        return SimpleNamespace()


@pytest.fixture
def rig(monkeypatch, tmp_path):
    database = FakeDatabase({
        A: payload(A),
        B: payload(B, source_sha256=B, image_sha256=B),
        C: payload(C),
        D: payload(D),
    })
    current = {A, B, D}  # C's file is unavailable now.

    @contextmanager
    def environment(**kwargs):
        assert kwargs == {'workspace_id': WORKSPACE}
        yield

    monkeypatch.setattr(projection.launcher, 'session_environment', environment)
    monkeypatch.setattr(projection.launcher, 'port_free', lambda port: True)
    monkeypatch.setattr(projection, '_database', lambda: database)
    monkeypatch.setattr(projection, 'current_source_hashes', lambda: frozenset(current))
    monkeypatch.setattr(projection, 'PRIVATE_DIRECTORY', tmp_path)
    monkeypatch.setattr(projection, 'private_hospital_root', lambda path: True)
    return SimpleNamespace(database=database, current=current, out=tmp_path)


def run_plan(rig, name='plan.json'):
    assert projection.main(['plan', '--workspace-id', WORKSPACE, '--out', str(rig.out / name)]) == 0
    raw = (rig.out / name).read_bytes()
    return json.loads(raw), projection.launcher.sha(raw)


def run_apply(rig, digest, name='applied'):
    receipt = rig.out / 'backup-receipt.json'
    if not receipt.exists():
        receipt.write_text('{"backup":"synthetic"}', encoding='utf-8')
    return projection.main(['apply', '--workspace-id', WORKSPACE, '--plan', str(rig.out / 'plan.json'),
                            '--plan-sha256', digest, '--backup-receipt', str(receipt), '--out', str(rig.out / name)])


@pytest.mark.parametrize('row, expected', [
    (payload(A), ('ELIGIBLE', 'ELIGIBLE')),
    (payload(A, source_sha256=A, image_sha256=A), ('ALREADY_RECORDED', 'RECORDED')),
    (payload(A, image_sha256=A), ('CONFLICT', 'RECORDED_IDENTITY_PARTIAL_OR_DIFFERENT')),
    (payload(A, source_sha256=B, image_sha256=B), ('CONFLICT', 'RECORDED_IDENTITY_PARTIAL_OR_DIFFERENT')),
    (payload(A, inference_history=[{'source_sha256': B}]), ('CONFLICT', 'INFERENCE_SOURCE_MISMATCH')),
    (payload(A, admission=None), ('INELIGIBLE', 'ADMISSION_MISSING')),
    (payload(A, revision=3), ('INELIGIBLE', 'ROW_IDENTITY_INCONSISTENT')),
    (payload(A, admission={**payload(A)['admission'], 'integrity_status': 'SOURCE_MISSING'}),
     ('INELIGIBLE', 'ADMISSION_IDENTITY_UNSOUND')),
    (payload(A, admission={**payload(A)['admission'], 'source_sha256': B}), ('INELIGIBLE', 'ADMISSION_IDENTITY_UNSOUND')),
    (payload(A, admission={**payload(A)['admission'], 'admission_method': 'LEGACY_COMPAT'}),
     ('INELIGIBLE', 'ADMISSION_IDENTITY_UNSOUND')),
])
def test_classification(row, expected):
    assert projection.classify(A, 2, row, frozenset({A})) == expected


def test_current_bytes_only_veto_and_never_supply_the_value():
    assert projection.classify(A, 2, payload(A), frozenset({B})) == (
        'INELIGIBLE', 'SOURCE_FILE_UNAVAILABLE_OR_CHANGED')


def test_plan_is_read_only_and_carries_no_private_fields(rig):
    before = deepcopy(rig.database.rows)
    plan, _ = run_plan(rig)
    assert rig.database.rows == before
    assert plan['counts'] == {'ELIGIBLE': 2, 'ALREADY_RECORDED': 1, 'CONFLICT': 0, 'INELIGIBLE': 1}
    assert [item['case_id'] for item in plan['cases']] == [A, B, C, D]
    text = (rig.out / 'plan.json').read_text(encoding='utf-8')
    assert 'private-name' not in text and 'private-key' not in text and 'admission' not in text


def test_apply_writes_only_the_projection_and_is_one_time(rig):
    before = deepcopy(rig.database.rows)
    _, digest = run_plan(rig)
    assert run_apply(rig, digest) == 0
    for digest_id in (A, D):
        revision, after = rig.database.rows[digest_id]
        assert revision == 3 and after['revision'] == 3
        assert after['source_sha256'] == after['image_sha256'] == digest_id
        event = after['events'][-1]
        assert event == {'action': 'RECORDED_SOURCE_IDENTITY_PROJECTION', 'value_source': 'ADMISSION_RECORD',
                         'sha256': digest_id, 'plan_sha256': digest, 'timestamp': event['timestamp']}
        original = before[digest_id][1]
        assert {key: value for key, value in after.items()
                if key not in {'source_sha256', 'image_sha256', 'revision', 'events'}} == {
            key: value for key, value in original.items() if key not in {'revision', 'events'}}
    assert rig.database.rows[B] == before[B] and rig.database.rows[C] == before[C]
    receipt = json.loads((rig.out / 'applied' / 'RECEIPT.json').read_bytes())
    assert receipt['written'] == 2 and receipt['readback'] == 'PASS' and receipt['plan_sha256'] == digest
    preimage = json.loads((rig.out / 'applied' / 'PREIMAGE.json').read_bytes())
    assert preimage == [{'case_id': A, 'revision': 2, 'payload': before[A][1]},
                        {'case_id': D, 'revision': 2, 'payload': before[D][1]}]
    assert not (rig.out / 'applied' / 'PREIMAGE.pending.json').exists()
    rerun, _ = run_plan(rig, 'rerun.json')
    assert rerun['counts']['ELIGIBLE'] == 0 and rerun['counts']['ALREADY_RECORDED'] == 3


def test_apply_refuses_a_plan_hash_the_owner_did_not_approve(rig, monkeypatch, capsys):
    run_plan(rig)
    monkeypatch.setattr(projection, '_database', lambda: pytest.fail('database touched'))
    assert run_apply(rig, '0' * 64) == 2
    assert 'OWNER_APPROVED_PLAN_HASH_REQUIRED' in capsys.readouterr().err


@pytest.mark.parametrize('change', ['revision', 'payload', 'file'])
def test_any_change_since_the_plan_refuses_the_whole_apply(rig, change, capsys):
    _, digest = run_plan(rig)
    if change == 'revision':
        revision, value = rig.database.rows[D]
        rig.database.rows[D] = (revision + 1, {**value, 'revision': revision + 1})
    elif change == 'payload':
        rig.database.rows[D][1]['filename'] = 'edited.png'
    else:
        rig.current.discard(D)
    before = deepcopy(rig.database.rows)
    assert run_apply(rig, digest) == 2
    assert 'CHANGED_SINCE_PLAN' in capsys.readouterr().err
    assert rig.database.rows == before and rig.database.updates == 0
    assert not (rig.out / 'applied' / 'RECEIPT.json').exists()


def test_a_failed_second_update_leaves_no_partial_write(rig, capsys):
    _, digest = run_plan(rig)
    before = deepcopy(rig.database.rows)
    rig.database.fail_update = 2
    assert run_apply(rig, digest) == 2
    assert 'CHANGED_SINCE_PLAN' in capsys.readouterr().err
    assert rig.database.updates == 2 and rig.database.rows == before
    # The pre-image keeps its pending name: it was never applied.
    assert (rig.out / 'applied' / 'PREIMAGE.pending.json').exists()
    assert not (rig.out / 'applied' / 'PREIMAGE.json').exists()


def test_active_entry_fence_rolls_back_with_no_write(rig, capsys):
    _, digest = run_plan(rig)
    before = deepcopy(rig.database.rows)
    rig.database.fenced = True
    assert run_apply(rig, digest) == 2
    assert 'DATABASE_REFUSED_55000' in capsys.readouterr().err
    assert rig.database.rows == before


def test_missing_entry_fence_trigger_is_refused(rig, capsys):
    rig.database.trigger = False
    assert projection.main(['plan', '--workspace-id', WORKSPACE, '--out', str(rig.out / 'plan.json')]) == 2
    assert 'ENTRY_FENCE_TRIGGER_REQUIRED' in capsys.readouterr().err
    assert not (rig.out / 'plan.json').exists()


def test_connection_lost_during_commit_is_reported_as_unknown_not_refused(rig, capsys):
    _, digest = run_plan(rig)
    rig.database.lose_commit = True
    assert run_apply(rig, digest) == 1
    output = capsys.readouterr()
    assert 'REFUSED' not in output.err
    assert json.loads(output.out.strip().splitlines()[-1])['status'] == 'COMMIT_OUTCOME_UNKNOWN'
    assert (rig.out / 'applied' / 'PREIMAGE.pending.json').exists()


def test_readback_failure_after_commit_is_reported_as_applied(rig, capsys):
    _, digest = run_plan(rig)
    rig.database.fail_session = rig.database.sessions + 2  # The readback session.
    assert run_apply(rig, digest) == 1
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary['status'] == 'APPLIED_READBACK_UNAVAILABLE' and summary['written'] == 2
    assert rig.database.rows[A][0] == 3
    receipt = json.loads((rig.out / 'applied' / 'RECEIPT.json').read_bytes())
    assert receipt['readback'] == 'UNAVAILABLE' and {item['readback'] for item in receipt['cases']} == {'UNAVAILABLE'}


def test_receipt_write_failure_after_commit_still_reports_the_write(rig, monkeypatch, capsys):
    _, digest = run_plan(rig)
    original = projection._write_new

    def failing(path, value):
        if Path(path).name == 'RECEIPT.json':
            raise OSError('synthetic')
        return original(path, value)

    monkeypatch.setattr(projection, '_write_new', failing)
    assert run_apply(rig, digest) == 1
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary['status'] == 'APPLIED_RECEIPT_NOT_WRITTEN' and len(summary['cases']) == 2


def test_scope_and_runtime_state_are_checked_before_private_configuration(rig, monkeypatch, capsys):
    monkeypatch.setattr(projection.launcher, 'session_environment',
                        lambda **kwargs: pytest.fail('private configuration read'))
    assert projection.main(['plan', '--workspace-id', 'ws_other', '--out', str(rig.out / 'x.json')]) == 2
    assert 'OWNER_APPROVED_WORKSPACE_REQUIRED' in capsys.readouterr().err
    monkeypatch.setattr(projection.launcher, 'port_free', lambda port: port != 8010)
    assert projection.main(['plan', '--workspace-id', WORKSPACE, '--out', str(rig.out / 'x.json')]) == 2
    assert 'REVIEW_APP_MUST_BE_STOPPED' in capsys.readouterr().err
    monkeypatch.setattr(projection.launcher, 'port_free', lambda port: port != 47860)
    assert projection.main(['plan', '--workspace-id', WORKSPACE, '--out', str(rig.out / 'x.json')]) == 2
    assert 'MODEL_TUNNEL_MUST_BE_CLOSED' in capsys.readouterr().err


def test_unreachable_database_is_a_clean_refusal_with_no_plan(rig, capsys):
    rig.database.fail_session = 1
    assert projection.main(['plan', '--workspace-id', WORKSPACE, '--out', str(rig.out / 'plan.json')]) == 2
    assert 'DATABASE_UNAVAILABLE' in capsys.readouterr().err
    assert not (rig.out / 'plan.json').exists()


def test_outputs_must_be_new_and_inside_the_private_acl_directory(rig, monkeypatch, tmp_path_factory, capsys):
    elsewhere = tmp_path_factory.mktemp('elsewhere') / 'plan.json'
    assert projection.main(['plan', '--workspace-id', WORKSPACE, '--out', str(elsewhere)]) == 2
    assert 'APPROVED_PRIVATE_OUTPUT_DIRECTORY_REQUIRED' in capsys.readouterr().err
    inside_repo = Path(projection.__file__).resolve().parent / 'plan.json'
    assert projection.main(['plan', '--workspace-id', WORKSPACE, '--out', str(inside_repo)]) == 2
    assert 'APPROVED_PRIVATE_OUTPUT_DIRECTORY_REQUIRED' in capsys.readouterr().err
    run_plan(rig)
    assert projection.main(['plan', '--workspace-id', WORKSPACE, '--out', str(rig.out / 'plan.json')]) == 2
    assert 'NEW_OUTPUT_PATH_REQUIRED' in capsys.readouterr().err
    monkeypatch.setattr(projection, 'private_hospital_root', lambda path: False)
    assert projection.main(['plan', '--workspace-id', WORKSPACE, '--out', str(rig.out / 'other.json')]) == 2
    assert 'PRIVATE_OUTPUT_ACL_REQUIRED' in capsys.readouterr().err
