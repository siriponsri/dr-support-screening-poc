"""Global-grade provenance regressions: direct routes/in-memory metadata, no DB or inference."""
import copy
import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from dr_support import workflow

SHA = 'a' * 64


def global_result():
    return {'model_id': 'mock-global', 'model_version': 'fixture-v1', 'modality': 'CFP', 'state': 'AI_SUGGESTION', 'grade': 2,
            'probabilities': [0.05, 0.05, 0.8, 0.05, 0.05], 'confidence': 0.8,
            'provenance': {'image_sha256': SHA, 'source_type': 'SYNTHETIC', 'preprocessing': 'fixture', 'source_revision': 'fixture-code'}}


def fixture():
    return {'image_id': 'synthetic-grade', 'revision': 1, 'global': global_result(), 'lesion': None,
            'state': 'PENDING', 'human_annotations': [], 'annotations': [], 'resolver_evidence': {},
            'admission': {'source_sha256': SHA, 'source_origin': 'SYNTHETIC', 'retinal_modality': 'CFP', 'modality_admission': 'FUNDUS_ACCEPTED', 'quality_state': 'GRADABLE'}}


def applied(case):
    return {'task': 'global', 'status': 'APPLIED', 'model_id': 'mock-global', 'model_version': 'fixture-v1',
            'source_sha256': SHA, 'analysis_sha256': SHA, 'transform_id': 'IDENTITY', 'representation_version': 'ORIGINAL',
            'case_revision': 0, 'result': copy.deepcopy(case['global'])}


def routes_for(case, monkeypatch):
    state = copy.deepcopy(case)
    writes = []

    class Store:
        lock = threading.RLock()

        def get(self, _):
            return copy.deepcopy(state)

        def put(self, value):
            state.clear()
            state.update(copy.deepcopy(value))
            writes.append(copy.deepcopy(value))

    class Routes:
        def __init__(self):
            image = SimpleNamespace(sha256=SHA, size=(800, 600), source_type='SYNTHETIC', source_origin='SYNTHETIC', filename='synthetic.png', source='fixture')
            self.state = SimpleNamespace(images={case['image_id']: image}, resolver=SimpleNamespace(resolve=lambda *_: {}))
            self.routes = {}

        def register(self, path):
            def decorator(function):
                self.routes[path] = function
                return function
            return decorator
        get = post = put = register

    monkeypatch.setattr(workflow, 'CVATOnline', lambda: SimpleNamespace())
    monkeypatch.setattr(workflow, 'automatic_resolution_needs_refresh', lambda *_: False)
    monkeypatch.setattr(workflow, 'hospital_patient_label', lambda _, case, **__: (case, None))
    app = Routes()
    workflow.install_workflow(app, Store())
    return app.routes, writes


def corrupt(case, kind):
    if kind == 'source-hash':
        case['global']['provenance']['image_sha256'] = 'f' * 64
    elif kind == 'missing-hash':
        case['global']['provenance'].pop('image_sha256')
    elif kind == 'origin':
        case['global']['provenance']['source_type'] = 'PUBLIC'
    elif kind == 'superseded-version':
        entry = applied(case)
        entry['model_version'] = entry['result']['model_version'] = 'fixture-v2'
        case['inference_history'] = [entry]
    elif kind == 'stale-only':
        entry = applied(case)
        entry['status'] = 'STALE_RESULT'
        case['inference_history'] = [entry]
    elif kind == 'history-source':
        entry = applied(case)
        entry['source_sha256'] = 'f' * 64
        case['inference_history'] = [entry]
    elif kind == 'result-disagreement':
        entry = applied(case)
        case['global']['provenance']['source_revision'] = 'different-code'
        case['inference_history'] = [entry]
    elif kind == 'wrong-model':
        case['global']['model_id'] = 'uspec-uwf-grading'
    elif kind == 'malformed-score':
        case['global']['confidence'] = 0.1
    elif kind == 'missing-version':
        case['global']['model_version'] = ''
    elif kind == 'future-history-revision':
        entry = applied(case)
        entry['case_revision'] = 10
        case['inference_history'] = [entry]
    else:
        raise AssertionError(kind)


@pytest.mark.parametrize('kind', ['source-hash', 'missing-hash', 'origin', 'superseded-version', 'stale-only', 'history-source', 'future-history-revision', 'result-disagreement', 'wrong-model', 'malformed-score', 'missing-version'])
def test_global_accept_rejects_stale_provenance_before_writing(kind, monkeypatch):
    case = fixture()
    corrupt(case, kind)
    routes, writes = routes_for(case, monkeypatch)
    request = workflow.Review(revision=1, action='ACCEPT', reviewer='Synthetic reviewer')
    with pytest.raises(HTTPException) as blocked:
        routes['/v1/cases/{image_id}/review'](case['image_id'], request)
    assert blocked.value.status_code == 409
    assert writes == []


@pytest.mark.parametrize('kind', ['source-hash', 'superseded-version', 'stale-only'])
def test_stale_global_is_hidden_but_manual_grading_remains_available(kind, monkeypatch):
    case = fixture()
    corrupt(case, kind)
    routes, writes = routes_for(case, monkeypatch)
    assert routes['/v1/cases/{image_id}'](case['image_id'])['global'] is None
    request = workflow.Review(revision=1, action='CORRECT_GRADE', reviewer='Synthetic reviewer', grade=3)
    response = routes['/v1/cases/{image_id}/review'](case['image_id'], request)
    assert response['reviewed_grade'] == 3
    assert response['grade_review_source'] == 'MANUAL'
    assert response['clinician_review']['source_sha256'] == SHA
    assert len(writes) == 1


@pytest.mark.parametrize('history', [False, True])
def test_matching_direct_global_suggestion_can_still_be_accepted(history, monkeypatch):
    case = fixture()
    if history:
        case['inference_history'] = [applied(case)]
    routes, writes = routes_for(case, monkeypatch)
    response = routes['/v1/cases/{image_id}/review'](case['image_id'], workflow.Review(revision=1, action='ACCEPT', reviewer='Synthetic reviewer'))
    assert response['reviewed_grade'] == 2
    assert response['grade_review_source'] == 'AI_ACCEPTED'
    assert len(writes) == 1


@pytest.mark.parametrize('failure', [None, 'source', 'analysis', 'lineage', 'transform', 'history'])
def test_prepared_global_is_bound_to_current_source_analysis_and_history(failure, monkeypatch):
    case = fixture()
    analysis = 'b' * 64
    transform = workflow.ANALYSIS_SOURCE_TRANSFORM
    representation = workflow.ANALYSIS_REPRESENTATION_VERSION
    case['global']['provenance']['image_sha256'] = analysis
    case['analysis_derivative'] = {
        'source_sha256': SHA, 'source_origin': 'SYNTHETIC', 'analysis_sha256': analysis,
        'derivative_sha256': analysis, 'transform_id': transform, 'representation_version': representation,
        'lineage': {'purpose': 'ANALYSIS', 'source_sha256': SHA, 'derivative_sha256': analysis, 'transform_id': transform},
    }
    entry = applied(case)
    entry.update(analysis_sha256=analysis, transform_id=transform, representation_version=representation)
    case['inference_history'] = [entry]
    if failure == 'source':
        case['analysis_derivative']['source_sha256'] = 'f' * 64
    elif failure == 'analysis':
        case['global']['provenance']['image_sha256'] = 'f' * 64
    elif failure == 'lineage':
        case['analysis_derivative']['lineage']['source_sha256'] = 'f' * 64
    elif failure == 'transform':
        case['analysis_derivative']['transform_id'] = 'unsupported-transform'
    elif failure == 'history':
        case['inference_history'][0]['analysis_sha256'] = 'f' * 64
    routes, writes = routes_for(case, monkeypatch)
    request = workflow.Review(revision=1, action='ACCEPT', reviewer='Synthetic reviewer')
    if failure:
        with pytest.raises(HTTPException) as blocked:
            routes['/v1/cases/{image_id}/review'](case['image_id'], request)
        assert blocked.value.status_code == 409
        assert writes == []
    else:
        assert routes['/v1/cases/{image_id}/review'](case['image_id'], request)['reviewed_grade'] == 2
        assert len(writes) == 1


def test_later_stale_attempt_does_not_invalidate_latest_applied_global(monkeypatch):
    case = fixture()
    latest = applied(case)
    stale = applied(case)
    stale['status'] = 'STALE_RESULT'
    stale['result']['model_version'] = stale['model_version'] = 'unused-version'
    case['inference_history'] = [latest, stale]
    routes, _ = routes_for(case, monkeypatch)
    response = routes['/v1/cases/{image_id}/review'](case['image_id'], workflow.Review(revision=1, action='ACCEPT', reviewer='Synthetic reviewer'))
    assert response['reviewed_grade'] == 2
