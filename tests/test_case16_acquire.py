"""Actual app/workflow/inspector/store with injected SQL, synthetic PNG only."""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from dr_support import case16_acquire as module
from dr_support.images import synthetic_image
from dr_support.persistence.cases import PostgresCaseStore
from dr_support.services import case16_snapshot


class SQLFixture:
    def __init__(self, settings):
        self.settings, self.rows, self.calls = settings, {}, []

    @contextmanager
    def session(self, **kwargs):
        yield self

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, query, params=None):
        text = query if isinstance(query, str) else query.as_string()
        self.calls.append((text, params))
        if text.startswith("INSERT") and ".review_cases" in text:
            key = params[1]
            if key in self.rows:
                return SimpleNamespace(rowcount=0)
            self.rows[key] = deepcopy(params[3].obj)
        elif text.startswith("UPDATE") and ".review_cases" in text:
            self.rows[params[2]] = deepcopy(params[0].obj)
        def one():
            if not params:
                return None
            payload = self.rows.get(params[1])
            return (payload["revision"], deepcopy(payload)) if payload else None
        return SimpleNamespace(rowcount=1, fetchone=one,
                               fetchall=lambda: [(key, row["revision"], deepcopy(row))
                                                 for key, row in self.rows.items()])


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    source_root = tmp_path / "demo"
    source_root.mkdir()
    source = source_root / "fixture.png"
    data = synthetic_image().data
    source.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    entry = dict(sha256=digest, modality="UWF", bytes=len(data), relative_path=source.name)
    manifest = tmp_path / "approved-map.json"
    manifest.write_text(json.dumps(dict(sample_root=str(source_root), files=[entry])))
    monkeypatch.setattr(module, "MANIFEST", manifest)
    monkeypatch.setattr(module, "MANIFEST_SHA", hashlib.sha256(manifest.read_bytes()).hexdigest())
    monkeypatch.setattr(module, "SOURCE_ROOT", source_root)
    monkeypatch.setattr(module, "SOURCE_SHA256", digest)
    monkeypatch.setattr(case16_snapshot, "SOURCE_SHA256", digest)
    qa = tmp_path / "qa"
    qa.mkdir()
    monkeypatch.setattr(module, "QA_ROOT", qa)
    monkeypatch.setenv(module.DSN_ENV, "postgresql://fixture:fixture@127.0.0.1:54805/dr_support_model_api_test")
    return source, entry, qa


@pytest.fixture
def app_backend(fixture, monkeypatch):
    # Actual app factory/workflow plus concrete PG store; only SQL wire is fake.
    from dr_support.api import _factory
    captured = {}
    def reserve(settings, workspace_id, directory):
        assert os.environ["DR_SUPPORT_DATABASE_SCHEMA"] == settings.schema
        assert "PGOPTIONS" not in os.environ
        captured.update(settings=settings, workspace_id=workspace_id, directory=directory)
        captured["database"] = SQLFixture(settings)
    def build_store(*args):
        store = PostgresCaseStore(captured["database"], captured["workspace_id"])
        captured["store"] = store
        return store, captured["workspace_id"], captured["settings"], None
    monkeypatch.setattr(module, "reserve_workspace", reserve)
    monkeypatch.setattr(_factory, "_build_case_store", build_store)
    return captured


def test_real_app_normal_ingestion_snapshot_no_confirmation(fixture, app_backend):
    source, entry, qa = fixture
    original = source.read_bytes()
    receipt_path = module.acquire(qa)
    receipt = json.loads(receipt_path.read_bytes())
    raw = (receipt_path.parent / "CASE16_INPUT_RECORD.json").read_bytes()
    value = json.loads(raw)
    assert receipt["status"] == "SNAPSHOT_CAPTURED"
    assert receipt["snapshot_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["model_calls"] == 0 and not receipt["listener_started"]
    assert value["image"]["source_origin"] == value["admission"]["source_origin"] == "PUBLIC"
    assert value["admission"]["retinal_modality"] == "UWF"
    assert value["admission"]["retinal_modality_method"] == "AUTHORIZED_SOURCE"
    assert value["admission"]["quality_state"] != "GRADABLE"
    assert value["case"]["reviewed_grade"] is None
    assert value["case"]["grade_status"] == "NOT_REVIEWED"
    assert value["case"]["clinician_review"] is None
    assert value["case"]["human_annotations"] == []
    assert not any(event.get("action") == "CONFIRM_IMAGE" for event in value["case"]["events"])
    assert value["case"]["admission_history"][0]["action"] == "AUTOMATIC_ADMISSION"
    assert value["case"]["admission"] == value["admission"]
    assert value["case"]["source_sha256"] == value["case"]["image_sha256"] == entry["sha256"]
    assert source.read_bytes() == original
    assert len(app_backend["database"].rows) == 1
    assert receipt["execution_eligibility"].startswith("BLOCKED")


def test_inherited_private_roots_remote_and_pg_settings_cleared_and_restored(fixture, app_backend, monkeypatch):
    monkeypatch.setenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS", "do-not-read")
    monkeypatch.setenv("REMOTE_MODEL_URL", "https://do-not-contact.invalid")
    monkeypatch.setenv("PGOPTIONS", "do-not-use")
    before = dict(os.environ)
    module.acquire(fixture[2])
    assert dict(os.environ) == before


def test_changed_image_fails_before_any_schema_or_directory(fixture, monkeypatch):
    source, _, qa = fixture
    source.write_bytes(b"changed fixture")
    monkeypatch.setattr(module, "reserve_workspace", lambda *args: pytest.fail("DB must not be reached"))
    with pytest.raises(module.AcquisitionError, match="SOURCE_CHANGED"):
        module.acquire(qa)
    assert list(qa.iterdir()) == []


def test_changed_manifest_fails_closed(fixture):
    module.MANIFEST.write_text("{}")
    with pytest.raises(module.AcquisitionError, match="MANIFEST_CHANGED"):
        module.approved_source()


def test_missing_credentials_does_not_read_secret_file(fixture, monkeypatch):
    monkeypatch.delenv(module.DSN_ENV)
    with pytest.raises(module.AcquisitionError, match="DSN_ENV_REQUIRED"):
        module.acquire(fixture[2])
    assert list(fixture[2].iterdir()) == []


@pytest.mark.parametrize("dsn", [
    "postgresql://f:f@127.0.0.1:54805/dr_support",
    "postgresql://f:f@remote.invalid:54805/dr_support_model_api_test",
    "postgresql://f:f@127.0.0.1:5432/dr_support_model_api_test",
    "postgresql://f@127.0.0.1:54805/dr_support_model_api_test",
    "postgresql://f:f@127.0.0.1:54805/dr_support_model_api_test?options=-csearch_path=public",
    "postgresql://f:f@127.0.0.1:54805/dr_support_model_api_test?options=-csearch_path%3Dpublic",
])
def test_reject_wrong_db_endpoint_or_credential_fallback(dsn):
    with pytest.raises(module.AcquisitionError, match="EXACT_LOCAL_TEST_DSN"):
        module.test_settings({module.DSN_ENV: dsn}, "dr_support_test_case16_" + "a" * 32)


def test_fresh_schema_collision_retains_failure_evidence(fixture, monkeypatch):
    def fail(*args):
        raise RuntimeError("private connection details must not leak")
    monkeypatch.setattr(module, "reserve_workspace", fail)
    with pytest.raises(module.AcquisitionError, match="RETAINED"):
        module.acquire(fixture[2])
    receipts = list(fixture[2].glob("*/ACQUISITION_RECEIPT.json"))
    assert len(receipts) == 1
    text = receipts[0].read_text()
    assert "private connection details" not in text
    assert json.loads(text)["stage"] == "RESERVE_NEW_SCHEMA"
    assert not (receipts[0].parent / "CASE16_INPUT_RECORD.json").exists()


def test_repeated_runs_use_new_scopes(fixture, app_backend):
    first = module.acquire(fixture[2])
    second = module.acquire(fixture[2])
    a, b = json.loads(first.read_bytes()), json.loads(second.read_bytes())
    assert first != second and a["test_schema"] != b["test_schema"]
    assert a["workspace_id"] != b["workspace_id"]


def test_output_outside_approved_evidence_root_rejects(fixture, tmp_path):
    with pytest.raises(module.AcquisitionError, match="QA_ROOT"):
        module.acquire(tmp_path)


def test_reserve_uses_exclusive_new_schema_and_verified_database(fixture, monkeypatch):
    calls = []
    class Database:
        def __init__(self, settings):
            self.settings = settings
        @contextmanager
        def transaction(self):
            yield self
        def execute(self, query):
            text = query if isinstance(query, str) else query.as_string()
            calls.append(text)
            return SimpleNamespace(fetchone=lambda: (module.DATABASE_NAME,))
    monkeypatch.setattr(module, "PostgresDatabase", Database)
    monkeypatch.setattr(module, "SchemaMigrator", lambda db: SimpleNamespace(migrate=lambda: calls.append("migrate")))
    monkeypatch.setattr(module, "PostgresWorkspaceCatalog", lambda db: SimpleNamespace(create_and_activate=lambda p: calls.append(p)))
    settings = module.test_settings(os.environ, "dr_support_test_case16_" + "a" * 32)
    module.reserve_workspace(settings, "ws_new_fixture", fixture[2])
    assert calls[0] == "SELECT current_database()"
    assert calls[1] == 'CREATE SCHEMA "' + settings.schema + '"'
    assert "IF NOT EXISTS" not in calls[1]
    assert calls[2] == "migrate"


def test_cli_requires_explicit_execution_flag():
    with pytest.raises(SystemExit):
        module.main(["--output-root", "not-used"])


def test_cli_outputs_receipt_only(fixture, app_backend, capsys):
    assert module.main(["--output-root", str(fixture[2]),
                        "--execute-reviewed-local-ingestion"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    from pathlib import Path
    receipt = Path(lines[0])
    assert receipt.name == "ACQUISITION_RECEIPT.json"
    assert lines[1] == hashlib.sha256(receipt.read_bytes()).hexdigest()
    assert fixture[0].name not in "\n".join(lines)


def test_git_controlled_output_rejected(fixture):
    (fixture[2] / ".git").mkdir()
    with pytest.raises(module.AcquisitionError, match="QA_ROOT"):
        module.acquire(fixture[2])


def test_source_replacement_between_hash_check_and_inspection_rejected(fixture, monkeypatch):
    original = module.inspect_file
    source, entry, _ = fixture
    source.write_bytes(b"not an image")
    # Exercise actual normal inspector's rejected-source path; no fabricated record.
    class Store:
        def all_cases(self):
            pytest.fail("invalid source must reject before store access")
    app = SimpleNamespace(state=SimpleNamespace(store=Store()))
    with pytest.raises(module.AcquisitionError, match="SOURCE_IDENTITY"):
        module.ingest_and_snapshot(app, source, entry, None, None)
    assert module.inspect_file is original


def test_failed_cli_reports_only_bounded_status_and_retained_receipt(fixture, monkeypatch, capsys):
    def fail(*args):
        raise PermissionError("fixture credentials must not be printed")
    monkeypatch.setattr(module, "reserve_workspace", fail)
    assert module.main(["--output-root", str(fixture[2]),
                        "--execute-reviewed-local-ingestion"]) == 2
    text = capsys.readouterr().out
    assert "ACQUISITION_RECEIPT.json" in text
    assert "credentials" not in text
    assert "BLOCKED" in text
