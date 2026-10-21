"""Real store/helper with injected SQL transport; no app startup or live DB."""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from threading import RLock
from types import SimpleNamespace

import pytest

from dr_support.images import BridgeImage
from dr_support.persistence.cases import CaseConflictError, PostgresCaseStore
from dr_support.services import case16_snapshot as module
from dr_support.services.case16_qualification import CLINICAL_FIELDS, SOURCE_SHA256


class Database:
    def __init__(self, row):
        self.settings = SimpleNamespace(schema="isolated_fixture")
        self.row, self.calls, self.transaction_open = row, [], False
        self.on_select = None

    @contextmanager
    def session(self, *, autocommit):
        assert autocommit is False
        self.calls.append("session")
        try:
            yield self
        finally:
            self.calls.append("close")

    @contextmanager
    def transaction(self):
        self.transaction_open = True
        self.calls.append("begin")
        try:
            yield
        finally:
            self.transaction_open = False
            self.calls.append("end")

    def execute(self, query, params=None):
        assert self.transaction_open
        text = query if isinstance(query, str) else query.as_string()
        self.calls.append((text, params))
        if text.startswith("SELECT"):
            assert self.calls[-2][0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            assert params[0] == "ws_fixture"
            if self.on_select:
                self.on_select()
        return SimpleNamespace(fetchone=lambda: deepcopy(self.row))


@pytest.fixture
def fixture(monkeypatch):
    monkeypatch.setenv("WORKERS", "1")
    data = b"synthetic snapshot fixture, not a patient image"
    digest = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(module, "SOURCE_SHA256", digest)  # Test scope only.
    admission = dict(image_id=digest, source_sha256=digest, source_origin="PUBLIC",
                     retinal_modality="UWF", modality_admission="NEEDS_REVIEW",
                     quality_state="UNKNOWN", integrity_status="SOURCE_CHANGED",
                     integrity={"status": "SOURCE_CHANGED", "changed_sources": ["fixture"]},
                     source_metadata={"source_sha256": digest, "unknown": None})
    case = dict(image_id=digest, revision=7, source_sha256=digest, image_sha256=digest,
                admission=deepcopy(admission), events=[{"fixture": "kept"}],
                inference_history=[{"fixture": True}], analysis_preparation=None,
                analysis_derivative={"fixture": [1, 2]}, unknown_future_field={"keep": None})
    for i, key in enumerate(CLINICAL_FIELDS):
        if i % 3 == 0:
            case[key] = None
        elif i % 3 == 1:
            case[key] = {"original": [key]}
        # Remaining fields intentionally absent, must stay absent.
    db = Database((7, case))
    store = PostgresCaseStore(db, "ws_fixture")
    image = BridgeImage(digest, data, "PUBLIC", "fixture reference", modality="UWF",
                        media_type="image/png", source_origin="PUBLIC")
    state = SimpleNamespace(store=store, workspace_id="ws_fixture",
                            images={digest: image}, admissions={digest: deepcopy(admission)},
                            workspace_manager=SimpleNamespace(store=store, lock=RLock()))
    app = SimpleNamespace(state=state)
    return app, db, case, admission, digest


def export(app, **changes):
    args = dict(workspace_id="ws_fixture", database_schema="isolated_fixture", revision=7)
    args.update(changes)
    return module.case16_metadata_json(app, **args)


def test_complete_original_snapshot_no_defaults_or_clinical_changes(fixture):
    app, db, case, admission, digest = fixture
    original = deepcopy((case, admission, app.state.admissions))
    result = json.loads(export(app))
    assert set(result) == {"case", "admission", "image"}
    assert result["case"] == case
    assert result["admission"] == admission  # SOURCE_CHANGED/uncertainty retained, not promoted.
    assert set(result["case"]) == set(case)
    for key in CLINICAL_FIELDS:
        assert (key in result["case"]) == (key in case)
    assert (case, admission, app.state.admissions) == original
    assert app.state.store._observed == app.state.store._observed_revision == {}
    assert result["image"] == dict(source_type="PUBLIC", source_origin="PUBLIC",
                                   source="fixture reference", modality="UWF", media_type="image/png")
    assert "data" not in result["image"] and "filename" not in result["image"]
    queries = [item for item in db.calls if isinstance(item, tuple)]
    assert len(queries) == 2
    assert '"isolated_fixture".review_cases' in queries[1][0]
    assert queries[1][1] == ("ws_fixture", digest)
    assert db.calls[-2:] == ["end", "close"]


def test_returned_objects_are_detached(fixture):
    app, db, case, _, _ = fixture
    result = module.case16_metadata_snapshot(app, workspace_id="ws_fixture",
                                            database_schema="isolated_fixture", revision=7)
    result["case"]["events"].clear()
    result["admission"]["integrity"].clear()
    assert case["events"] and db.row[1]["admission"]["integrity"]


@pytest.mark.parametrize("change", [dict(revision=6), dict(revision=True),
                                   dict(workspace_id="other"), dict(database_schema="original")])
def test_scope_and_revision_reject(fixture, change):
    app, _, _, _, _ = fixture
    with pytest.raises(module.Case16SnapshotError):
        export(app, **change)


def test_missing_row_never_creates_or_defaults(fixture):
    app, db, _, _, _ = fixture
    db.row = None
    with pytest.raises(module.Case16SnapshotError, match="ORIGINAL_CASE"):
        export(app)


@pytest.mark.parametrize("field", ["revision", "image_id"])
def test_row_document_mismatch(fixture, field):
    app, db, _, _, _ = fixture
    db.row[1][field] = 8 if field == "revision" else "other"
    with pytest.raises(CaseConflictError):
        app.state.store.read_original_case(module.SOURCE_SHA256)


@pytest.mark.parametrize("field", ["source_sha256", "image_sha256"])
def test_recorded_source_mismatch_or_missing_never_repaired(fixture, field):
    app, db, _, _, _ = fixture
    del db.row[1][field]
    with pytest.raises(module.Case16SnapshotError, match="SOURCE_IDENTITY"):
        export(app)
    db.row[1][field] = "f" * 64
    with pytest.raises(module.Case16SnapshotError, match="SOURCE_IDENTITY"):
        export(app)


def test_missing_metadata_rejects(fixture):
    app, _, _, _, digest = fixture
    del app.state.admissions[digest]["integrity_status"]
    with pytest.raises(module.Case16SnapshotError, match="INCOMPLETE"):
        export(app)


def test_missing_image_metadata_rejects(fixture):
    app, _, _, _, digest = fixture
    from dataclasses import replace
    app.state.images[digest] = replace(app.state.images[digest], media_type="")
    with pytest.raises(module.Case16SnapshotError, match="INCOMPLETE"):
        export(app)


def test_admission_projection_mismatch_rejects(fixture):
    app, _, _, _, digest = fixture
    app.state.admissions[digest]["quality_state"] = "GRADABLE"
    with pytest.raises(module.Case16SnapshotError, match="PROJECTION_MISMATCH"):
        export(app)


def test_projection_change_during_read_rejects(fixture):
    app, db, _, _, digest = fixture
    db.on_select = lambda: app.state.images.pop(digest)
    with pytest.raises(module.Case16SnapshotError, match="PROJECTION_CHANGED"):
        export(app)


def test_sql_failure_closes_transaction_without_writes(fixture):
    app, db, _, _, _ = fixture
    def fail():
        raise PermissionError("fixture denied")
    db.on_select = fail
    with pytest.raises(PermissionError):
        export(app)
    assert db.calls[-2:] == ["end", "close"]
    assert app.state.store._observed == {}


def test_production_pin_is_unchanged():
    assert SOURCE_SHA256 == "07bc59b885de06bdd0260c771aabde195c26125e824269a691eb566a61a5cd19"


def test_multiple_workers_rejected_before_sql(fixture, monkeypatch):
    app, db, _, _, _ = fixture
    monkeypatch.setenv("WORKERS", "2")
    with pytest.raises(module.Case16SnapshotError, match="SINGLE_WORKER"):
        export(app)
    assert db.calls == []


def test_loaded_image_bytes_mismatch_rejected(fixture):
    from dataclasses import replace
    app, _, _, _, digest = fixture
    app.state.images[digest] = replace(app.state.images[digest], data=b"different synthetic input")
    with pytest.raises(module.Case16SnapshotError, match="SOURCE_IDENTITY"):
        export(app)


def test_nested_recorded_hash_conflict_rejected(fixture):
    app, db, _, _, digest = fixture
    app.state.admissions[digest]["source_metadata"]["source_sha256"] = "f" * 64
    db.row[1]["admission"] = deepcopy(app.state.admissions[digest])
    with pytest.raises(module.Case16SnapshotError, match="SOURCE_IDENTITY"):
        export(app)


def test_app_workspace_change_during_read_rejected(fixture):
    app, db, _, _, _ = fixture
    db.on_select = lambda: setattr(app.state, "workspace_id", "other")
    with pytest.raises(module.Case16SnapshotError, match="PROJECTION_CHANGED"):
        export(app)


def test_supported_runtime_locks_held_during_sql(fixture):
    app, db, _, _, _ = fixture
    def check_locks():
        assert app.state.store.lock._is_owned()
        assert app.state.workspace_manager.lock._is_owned()
    db.on_select = check_locks
    export(app)
