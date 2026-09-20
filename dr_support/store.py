"""Single-runtime durable Bridge records and optimistic review revisions."""
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
                return case
            return {'image_id': image_id, 'revision': 0, 'state': 'PENDING',
                    'events': [], 'global': None, 'lesion': None, 'cvat': None,
                    'reviewed_grade': None, 'grade_review_source': None,
                    'lesion_review_state': None, 'annotations': None,
                    'human_annotations': [], 'clinician_review': None,
                    'review_history': [], 'admission': None, 'admission_history': []}

    def put(self, case):
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO cases VALUES (?, ?)',
                            (case['image_id'], json.dumps(case, allow_nan=False)))
            self.db.commit()
