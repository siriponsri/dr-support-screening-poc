"""Single-runtime durable review records and optimistic revisions."""
import json
import sqlite3
from pathlib import Path
from threading import RLock


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        self.db.commit()
        self.lock = RLock()

    def get(self, image_id):
        with self.lock:
            row = self.db.execute('SELECT data FROM cases WHERE id=?', (image_id,)).fetchone()
            if row:
                case = json.loads(row[0])
                # S2A1 is an additive JSON migration so old S2 databases remain
                # readable without a destructive table rewrite.
                case.setdefault('admission', None)
                case.setdefault('admission_history', [])
                case.setdefault('analysis_derivative', None)
                case.setdefault('analysis_preparation', None)
                case.setdefault('superseded_model_results', [])
                case.setdefault('ai_annotation_reviews', [])
                case.setdefault('annotation_confirmation', None)
                case.setdefault('queue_state', 'INCLUDED')
                case.setdefault('queue_history', [])
                _set_resolver_defaults(case)
                return case
            case = {'image_id': image_id, 'revision': 0, 'state': 'PENDING',
                    'events': [], 'global': None, 'lesion': None, 'cvat': None,
                    'reviewed_grade': None, 'grade_review_source': None,
                    'lesion_review_state': None, 'annotations': None,
                    'human_annotations': [], 'clinician_review': None,
                    'review_history': [], 'admission': None, 'admission_history': [],
                    'analysis_derivative': None,
                    'analysis_preparation': None, 'superseded_model_results': [],
                    'ai_annotation_reviews': [],
                    'annotation_confirmation': None,
                    'queue_state': 'INCLUDED', 'queue_history': []}
            _set_resolver_defaults(case)
            return case

    def all_cases(self):
        """Return durable cases for non-destructive source reconciliation."""
        with self.lock:
            rows = self.db.execute('SELECT data FROM cases ORDER BY id').fetchall()
            cases = []
            for (data,) in rows:
                case = json.loads(data)
                case.setdefault('admission', None)
                case.setdefault('admission_history', [])
                case.setdefault('analysis_derivative', None)
                case.setdefault('analysis_preparation', None)
                case.setdefault('superseded_model_results', [])
                case.setdefault('ai_annotation_reviews', [])
                case.setdefault('annotation_confirmation', None)
                case.setdefault('queue_state', 'INCLUDED')
                case.setdefault('queue_history', [])
                _set_resolver_defaults(case)
                cases.append(case)
            return cases

    def put(self, case):
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO cases VALUES (?, ?)',
                            (case['image_id'], json.dumps(case, allow_nan=False)))
            self.db.commit()


def _set_resolver_defaults(case):
    """Keep identity fields additive so legacy JSON case records remain readable."""
    defaults = {
        'patient_key': None,
        'patient_resolution_state': 'UNLINKED',
        'patient_resolution_method': 'NONE',
        'patient_reason_code': 'NO_PATIENT_EVIDENCE',
        'patient_candidate': None,
        'patient_confidence_or_strength': None,
        'laterality': 'UNKNOWN',
        'laterality_resolution_state': 'UNLINKED',
        'laterality_resolution_method': 'NONE',
        'laterality_reason_code': 'NO_LATERALITY_EVIDENCE',
        'laterality_candidate': None,
        'resolver_state': 'UNLINKED',
        'resolver_evidence': None,
        'resolution_history': [],
    }
    for key, value in defaults.items():
        case.setdefault(key, value.copy() if isinstance(value, list) else value)
