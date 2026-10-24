"""Recorded source identity amendment, Part B: synthetic rows and a fake database only."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest

from scripts.qa import m1_recorded_source_projection as projection

WORKSPACE = 'ws_m1_63ed86c7d44f46d59479'
A, B, C = 'a' * 64, 'b' * 64, 'c' * 64


def payload(digest, **changes):
    value = {'image_id': digest, 'revision': 2, 'filename': 'private-name.png', 'events': [],
             'admission': {'image_id': digest, 'source_sha256': digest, 'integrity_status': 'OK',
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

    @contextmanager
    def session(self, autocommit=True):
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

    def execute(self, query, params=None):
        text = repr(query)
        if 'SET revision' in text:
            if self.database.fenced:
                raise psycopg.errors.lookup('55000')('SOURCE_ENTRY_FENCED')
            revision, value, _workspace, case_id, expected = params
            current = self.database.rows.get(case_id)
            if current is None or current[0] != expected:
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
    })
    current = {A, B}  # C's file is unavailable now.

    @contextmanager
    def environment(**kwargs):
        assert kwargs == {'workspace_id': WORKSPACE}
        yield

    monkeypatch.setattr(projection.launcher, 'session_environment', environment)
    monkeypatch.setattr(projection.launcher, 'port_free', lambda port: True)
    monkeypatch.setattr(projection, '_database', lambda: database)
    monkeypatch.setattr(projection, 'current_source_hashes', lambda: frozenset(current))
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
    assert plan['counts'] == {'ELIGIBLE': 1, 'ALREADY_RECORDED': 1, 'CONFLICT': 0, 'INELIGIBLE': 1}
    assert [item['case_id'] for item in plan['cases']] == [A, B, C]
    text = (rig.out / 'plan.json').read_text(encoding='utf-8')
    assert 'private-name' not in text and 'private-key' not in text and 'admission' not in text


def test_apply_writes_only_the_projection_and_is_one_time(rig):
    before = deepcopy(rig.database.rows)
    _, digest = run_plan(rig)
    assert run_apply(rig, digest) == 0
    revision, after = rig.database.rows[A]
    assert revision == 3 and after['revision'] == 3
    assert after['source_sha256'] == after['image_sha256'] == A
    event = after['events'][-1]
    assert event['action'] == 'RECORDED_SOURCE_IDENTITY_PROJECTION' and event['plan_sha256'] == digest
    assert event['value_source'] == 'ADMISSION_RECORD' and event['sha256'] == A
    original = before[A][1]
    assert {key: value for key, value in after.items()
            if key not in {'source_sha256', 'image_sha256', 'revision', 'events'}} == {
        key: value for key, value in original.items() if key not in {'revision', 'events'}}
    assert rig.database.rows[B] == before[B] and rig.database.rows[C] == before[C]
    receipt = json.loads((rig.out / 'applied' / 'RECEIPT.json').read_bytes())
    assert receipt['written'] == 1 and receipt['readback'] == 'PASS' and receipt['plan_sha256'] == digest
    preimage = json.loads((rig.out / 'applied' / 'PREIMAGE.json').read_bytes())
    assert preimage == [{'case_id': A, 'revision': 2, 'payload': original}]
    rerun, _ = run_plan(rig, 'rerun.json')
    assert rerun['counts']['ELIGIBLE'] == 0 and rerun['counts']['ALREADY_RECORDED'] == 2


def test_apply_refuses_a_plan_hash_the_owner_did_not_approve(rig, monkeypatch, capsys):
    run_plan(rig)
    monkeypatch.setattr(projection, '_database', lambda: pytest.fail('database touched'))
    assert run_apply(rig, '0' * 64) == 2
    assert 'OWNER_APPROVED_PLAN_HASH_REQUIRED' in capsys.readouterr().err


@pytest.mark.parametrize('change', ['revision', 'payload', 'file'])
def test_any_change_since_the_plan_refuses_the_whole_apply(rig, change, capsys):
    _, digest = run_plan(rig)
    if change == 'revision':
        revision, value = rig.database.rows[A]
        rig.database.rows[A] = (revision + 1, {**value, 'revision': revision + 1})
    elif change == 'payload':
        rig.database.rows[A][1]['filename'] = 'edited.png'
    else:
        rig.current.discard(A)
    before = deepcopy(rig.database.rows)
    assert run_apply(rig, digest) == 2
    assert 'CHANGED_SINCE_PLAN' in capsys.readouterr().err
    assert rig.database.rows == before and not (rig.out / 'applied' / 'RECEIPT.json').exists()


def test_active_entry_fence_rolls_back_with_no_write(rig, capsys):
    _, digest = run_plan(rig)
    before = deepcopy(rig.database.rows)
    rig.database.fenced = True
    assert run_apply(rig, digest) == 2
    assert 'DATABASE_REFUSED_55000' in capsys.readouterr().err
    assert rig.database.rows == before


def test_scope_and_app_state_are_checked_before_private_configuration(rig, monkeypatch, capsys):
    monkeypatch.setattr(projection.launcher, 'session_environment',
                        lambda **kwargs: pytest.fail('private configuration read'))
    assert projection.main(['plan', '--workspace-id', 'ws_other', '--out', str(rig.out / 'x.json')]) == 2
    assert 'OWNER_APPROVED_WORKSPACE_REQUIRED' in capsys.readouterr().err
    monkeypatch.setattr(projection.launcher, 'port_free', lambda port: port != 8010)
    assert projection.main(['plan', '--workspace-id', WORKSPACE, '--out', str(rig.out / 'x.json')]) == 2
    assert 'REVIEW_APP_MUST_BE_STOPPED' in capsys.readouterr().err


def test_outputs_must_be_private_and_new(rig, capsys):
    inside = Path(projection.__file__).resolve().parent / 'plan.json'
    assert projection.main(['plan', '--workspace-id', WORKSPACE, '--out', str(inside)]) == 2
    assert 'PRIVATE_OUTPUT_OUTSIDE_REPOSITORY_REQUIRED' in capsys.readouterr().err
    run_plan(rig)
    assert projection.main(['plan', '--workspace-id', WORKSPACE, '--out', str(rig.out / 'plan.json')]) == 2
    assert 'NEW_OUTPUT_PATH_REQUIRED' in capsys.readouterr().err
