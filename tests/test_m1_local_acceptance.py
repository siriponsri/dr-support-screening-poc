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
