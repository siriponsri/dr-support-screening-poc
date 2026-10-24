"""Synthetic checks for the read-only local acceptance evidence tool."""
import json

from dr_support.presentation import annotation_set_hash
from scripts.qa import m1_local_acceptance as tool


def synthetic_case():
    case = {
        'grade_status': 'CONFIRMED',
        'clinician_review': {'final_grade': 2, 'review_action': 'CORRECT_GRADE', 'reviewer': 'TEST_ONLY',
                             'timestamp': '2026-01-01T00:00:00+00:00', 'revision': 3, 'remark': 'not recorded'},
        'human_annotations': [{'shape_id': 's1', 'type': 'rectangle', 'label': 'HEMORRHAGE', 'source': 'HUMAN',
                               'reviewer': 'TEST_ONLY', 'geometry': {'x': 1, 'y': 2, 'width': 3, 'height': 4}}],
        'annotation_completeness': {'CORE': {'state': 'REVIEWED_FINDINGS_RECORDED'}},
        'inference_history': [{'model_id': 'synthetic'}],
        'admission': {'quality_state': 'GRADABLE'},
        'patient_key': 'SYNTHETIC-PATIENT',
    }
    case['annotation_confirmation'] = {'reviewer': 'TEST_ONLY', 'timestamp': '2026-01-01T00:00:00+00:00',
                                       'annotation_set_hash': annotation_set_hash(case)}
    return case


def test_record_keeps_clinician_fields_and_checks_the_set_hash():
    record = tool.record_from_payload(4, synthetic_case())
    assert record['fields']['clinician_review']['final_grade'] == 2
    assert 'remark' not in record['fields']['clinician_review']
    assert record['fields']['core_completeness'] == 'REVIEWED_FINDINGS_RECORDED'
    assert record['annotation_set_hash_matches'] is True
    # Patient keys are never part of the printed fields.
    assert 'SYNTHETIC-PATIENT' not in json.dumps(record['fields'])


def test_set_hash_mismatch_is_reported():
    case = synthetic_case()
    case['human_annotations'][0]['geometry']['x'] = 99
    assert tool.record_from_payload(4, case)['annotation_set_hash_matches'] is False


def test_compare_attributes_changes_to_payload_keys(tmp_path, capsys):
    before = tool.record_from_payload(4, synthetic_case())
    changed = synthetic_case()
    changed['admission']['updated_at'] = 'later'
    after = tool.record_from_payload(4, changed)
    (tmp_path / 'a.json').write_text(json.dumps(before))
    (tmp_path / 'b.json').write_text(json.dumps(after))
    tool.main(['compare', str(tmp_path / 'a.json'), str(tmp_path / 'b.json')])
    result = json.loads(capsys.readouterr().out)
    assert result['clinician_review'] is True and result['payload'] is False
    assert result['payload_keys_changed'] == ['admission']


def test_only_database_keys_are_loaded(tmp_path, monkeypatch):
    for key in (*tool.DB_KEYS, 'REMOTE_MODEL_TOKEN'):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / '.env'
    env.write_text('DR_SUPPORT_DATABASE_URL=postgresql://synthetic.invalid/db\nREMOTE_MODEL_TOKEN=secret\n')
    tool.load_database_environment(env)
    import os
    assert os.environ['DR_SUPPORT_DATABASE_URL'] == 'postgresql://synthetic.invalid/db'
    assert 'REMOTE_MODEL_TOKEN' not in os.environ


def test_identity_keys_are_never_hashed_per_key():
    case = synthetic_case()
    case['admission'].update(trusted_patient_key='HOSPITAL-SYNTHETIC', filename='synthetic.jpg')
    case['visit_context'] = {'visit_key': 'V1'}
    keys = tool.record_from_payload(4, case)['payload_key_sha256']
    assert not set(keys) & tool.IDENTITY_KEYS
    stripped = {name: value for name, value in case['admission'].items() if name not in tool.ADMISSION_IDENTITY}
    assert keys['admission'] == tool.digest(stripped)


def test_failure_checks_stop_before_any_request_when_revisions_differ(monkeypatch):
    sent = []
    monkeypatch.setattr(tool, 'read_case', lambda workspace, case: (5, synthetic_case()))
    monkeypatch.setattr(tool, 'http_json', lambda *args, **kwargs: sent.append(args) or {})

    class Reply:
        def __init__(self, body):
            self.body = body

        def read(self):
            return json.dumps(self.body).encode()

    replies = {'/v1/cases/c1': {'revision': 6, 'modality': 'CFP'}, '/v1/models': []}
    monkeypatch.setattr(tool.urlrequest, 'urlopen',
                        lambda url, timeout: Reply(replies[url.removeprefix('http://synthetic.invalid')]))
    import pytest
    with pytest.raises(SystemExit, match='SAME_REVISION'):
        tool.main(['failure-checks', '--workspace-id', 'w', '--case-id', 'c1', '--base-url', 'http://synthetic.invalid'])
    replies['/v1/cases/c1']['revision'] = 5
    replies['/v1/models'] = [{'model_id': 'retfound-aptos5', 'status': 'LOADED', 'ready': True}]
    with pytest.raises(SystemExit, match='MODEL_API_REACHABLE'):
        tool.main(['failure-checks', '--workspace-id', 'w', '--case-id', 'c1', '--base-url', 'http://synthetic.invalid'])
    assert sent == []


def test_unknown_server_detail_is_not_recorded(monkeypatch):
    class Failure(tool.urlerror.HTTPError):
        def __init__(self):
            super().__init__('http://synthetic.invalid', 502, 'bad', {}, None)

        def read(self):
            return json.dumps({'detail': self.detail}).encode()

    for detail in ('upstream said secret-ish text', [{'loc': ['body'], 'msg': 'invalid'}]):
        Failure.detail = detail

        def fail(request, timeout):
            raise Failure()
        monkeypatch.setattr(tool.urlrequest, 'urlopen', fail)
        assert tool.http_json('GET', 'http://synthetic.invalid', None)['detail'] is None
