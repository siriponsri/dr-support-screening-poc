"""Focused unit and opt-in integration tests for the M1 PostgreSQL foundation."""

from __future__ import annotations

import os
import re
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb
from fastapi.testclient import TestClient

from dr_support.persistence import (
    CaseConflictError,
    CaseImportConflictError,
    ConsistencyBoundary,
    LegacySQLiteMigrationService,
    LegacySourceConflictError,
    MigrationConsistencyError,
    MigrationNotSafeError,
    PostgresCaseStore,
    DatabaseConfigurationError,
    DatabaseUnavailableError,
    LATEST_SCHEMA_VERSION,
    PostgresDatabase,
    PostgresSettings,
    PostgresWorkspaceCatalog,
    SchemaMigrator,
)
from dr_support.persistence.config import CASE_STORE_MODE_ENV, DATABASE_SCHEMA_ENV, DATABASE_URL_ENV
from dr_support.persistence.legacy_migration import _capture_source
from dr_support.api import create_app
from dr_support.persistence.migrations import MIGRATIONS


TEST_DATABASE_URL_ENV = "DR_SUPPORT_TEST_DATABASE_URL"
TEST_DATABASE_NAME_ENV = "DR_SUPPORT_TEST_DATABASE_NAME"


def _designated_test_settings(environ: dict[str, str]) -> PostgresSettings | None:
    dsn = (environ.get(TEST_DATABASE_URL_ENV) or "").strip()
    if not dsn:
        return None
    expected_name = (environ.get(TEST_DATABASE_NAME_ENV) or "").strip()
    if not expected_name:
        raise ValueError(
            f"{TEST_DATABASE_NAME_ENV} is required when {TEST_DATABASE_URL_ENV} is configured"
        )
    actual_name = conninfo_to_dict(dsn).get("dbname")
    if actual_name != expected_name:
        raise ValueError(
            f"Designated test database mismatch: expected {expected_name!r}, got {actual_name!r}"
        )
    name_tokens = re.split(r"[^a-z0-9]+", expected_name.lower())
    if "test" not in name_tokens:
        raise ValueError("Designated PostgreSQL database name must contain a distinct 'test' token")
    return PostgresSettings(dsn=dsn)


def test_postgres_settings_require_explicit_server_side_configuration():
    with pytest.raises(DatabaseConfigurationError, match=TEST_DATABASE_URL_ENV):
        PostgresSettings.from_env({}, url_variable=TEST_DATABASE_URL_ENV)


def test_postgres_settings_reject_invalid_configuration_without_echoing_secret():
    secret = "do-not-log-this"
    with pytest.raises(DatabaseConfigurationError) as exc_info:
        PostgresSettings(dsn=f"not-a-postgres-dsn-{secret}")

    assert secret not in str(exc_info.value)


def test_configured_unavailable_postgres_fails_clearly_without_dsn_leak():
    password = "synthetic-secret"
    settings = PostgresSettings(
        dsn=f"postgresql://app:{password}@127.0.0.1:5432/dr_support"
    )

    def unavailable(*_args, **_kwargs):
        raise psycopg.OperationalError("connection refused")

    database = PostgresDatabase(settings, connector=unavailable)

    with pytest.raises(DatabaseUnavailableError, match="configured but unavailable") as exc_info:
        database.verify_available()

    assert password not in str(exc_info.value)


def test_migration_sequence_and_checksums_are_deterministic():
    assert tuple(migration.version for migration in MIGRATIONS) == tuple(
        range(1, LATEST_SCHEMA_VERSION + 1)
    )
    assert len({migration.checksum for migration in MIGRATIONS}) == len(MIGRATIONS)
    assert all(len(migration.checksum) == 64 for migration in MIGRATIONS)


def test_postgres_test_target_requires_exact_visibly_test_only_database_name():
    dsn = "postgresql://user:private@127.0.0.1:5432/dr_support_test"

    with pytest.raises(ValueError, match="mismatch"):
        _designated_test_settings(
            {
                TEST_DATABASE_URL_ENV: dsn,
                TEST_DATABASE_NAME_ENV: "different_test",
            }
        )
    with pytest.raises(ValueError, match="distinct 'test' token"):
        _designated_test_settings(
            {
                TEST_DATABASE_URL_ENV: "postgresql://user:private@127.0.0.1:5432/dr_support",
                TEST_DATABASE_NAME_ENV: "dr_support",
            }
        )


@pytest.fixture(scope="session")
def postgres_test_target() -> PostgresSettings:
    """Load only an explicitly named, visibly test-only PostgreSQL database."""

    try:
        settings = _designated_test_settings(dict(os.environ))
    except (DatabaseConfigurationError, ValueError) as exc:
        pytest.fail(str(exc))
    if settings is None:
        pytest.skip(
            f"{TEST_DATABASE_URL_ENV} is not configured; PostgreSQL integration tests skipped"
        )
    try:
        PostgresDatabase(settings).verify_available()
    except DatabaseUnavailableError as exc:
        pytest.fail(str(exc))
    return settings


@pytest.fixture
def postgres_database(postgres_test_target: PostgresSettings):
    """Use and later remove only a unique schema created by this test fixture."""

    schema = f"dr_support_test_{uuid4().hex}"
    settings = PostgresSettings(
        dsn=postgres_test_target.dsn,
        schema=schema,
        connect_timeout_seconds=postgres_test_target.connect_timeout_seconds,
        application_name="dr-support-postgres-tests",
    )
    database = PostgresDatabase(settings)
    yield database
    if not schema.startswith("dr_support_test_"):
        pytest.fail("Refusing to clean up a schema not created by the PostgreSQL fixture")
    with database.transaction() as connection:
        connection.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
        )


def test_clean_schema_upgrade_is_repeatable(postgres_database: PostgresDatabase):
    migrator = SchemaMigrator(postgres_database)

    first = migrator.migrate(target_version=1)
    upgraded = migrator.migrate()
    repeated = migrator.migrate()

    assert first.applied_versions == (1,)
    assert upgraded.previous_version == 1
    assert upgraded.applied_versions == tuple(range(2, LATEST_SCHEMA_VERSION + 1))
    assert repeated.current_version == LATEST_SCHEMA_VERSION
    assert repeated.applied_versions == ()
    schema = sql.Identifier(postgres_database.settings.schema)
    with postgres_database.session() as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT version, name, checksum FROM {}.schema_migrations ORDER BY version"
            ).format(schema)
        ).fetchall()
    assert rows == [
        (migration.version, migration.name, migration.checksum) for migration in MIGRATIONS
    ]
    with postgres_database.session() as connection:
        columns = {
            row[0]
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = 'workspaces'",
                (postgres_database.settings.schema,),
            ).fetchall()
        }
    assert {
        "workspace_id", "name", "input_folder", "output_folder", "database_path",
        "note", "created_at", "updated_at", "last_opened", "archived_at",
    }.issubset(columns)
    with postgres_database.session() as connection:
        indexes = connection.execute(
            "SELECT schemaname, indexname FROM pg_indexes "
            "WHERE schemaname = %s AND tablename = 'workspaces' "
            "AND indexname = 'workspaces_catalog_order_idx'",
            (postgres_database.settings.schema,),
        ).fetchall()
    assert indexes == [(postgres_database.settings.schema, "workspaces_catalog_order_idx")]


def test_transaction_exception_rolls_back(postgres_database: PostgresDatabase):
    SchemaMigrator(postgres_database).migrate()
    schema = sql.Identifier(postgres_database.settings.schema)

    with pytest.raises(RuntimeError, match="planned rollback"):
        with postgres_database.transaction() as connection:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {}.workspaces (workspace_id) VALUES (%s)"
                ).format(schema),
                ("ws_rollback",),
            )
            raise RuntimeError("planned rollback")

    with postgres_database.session() as connection:
        count = connection.execute(
            sql.SQL("SELECT count(*) FROM {}.workspaces WHERE workspace_id = %s").format(
                schema
            ),
            ("ws_rollback",),
        ).fetchone()[0]
    assert count == 0


def test_workspace_case_keys_and_revisions_are_enforced(
    postgres_database: PostgresDatabase,
):
    SchemaMigrator(postgres_database).migrate()
    schema = sql.Identifier(postgres_database.settings.schema)
    with postgres_database.transaction() as connection:
        connection.execute(
            sql.SQL(
                "INSERT INTO {}.workspaces (workspace_id) VALUES (%s), (%s)"
            ).format(schema),
            ("ws_a", "ws_b"),
        )
        connection.execute(
            sql.SQL(
                "INSERT INTO {}.review_cases (workspace_id, case_id, payload) "
                "VALUES (%s, %s, '{{}}'::jsonb), (%s, %s, '{{}}'::jsonb)"
            ).format(schema),
            ("ws_a", "case_shared", "ws_b", "case_shared"),
        )

    with pytest.raises(UniqueViolation):
        with postgres_database.transaction() as connection:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {}.review_cases (workspace_id, case_id, payload) "
                    "VALUES (%s, %s, '{{}}'::jsonb)"
                ).format(schema),
                ("ws_a", "case_shared"),
            )

    with pytest.raises(CheckViolation):
        with postgres_database.transaction() as connection:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {}.review_cases "
                    "(workspace_id, case_id, revision, payload) "
                    "VALUES (%s, %s, %s, '{{}}'::jsonb)"
                ).format(schema),
                ("ws_a", "case_negative_revision", -1),
            )

    with pytest.raises(ForeignKeyViolation):
        with postgres_database.transaction() as connection:
            connection.execute(
                sql.SQL("DELETE FROM {}.workspaces WHERE workspace_id = %s").format(
                    schema
                ),
                ("ws_a",),
            )

    with postgres_database.session() as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT workspace_id, case_id, revision FROM {}.review_cases "
                "ORDER BY workspace_id"
            ).format(schema)
        ).fetchall()
    assert rows == [
        ("ws_a", "case_shared", 0),
        ("ws_b", "case_shared", 0),
    ]


def test_case_insert_read_update_survives_new_store_instance(
    postgres_database: PostgresDatabase,
):
    SchemaMigrator(postgres_database).migrate()
    first = PostgresCaseStore(postgres_database, "ws_restart")
    case = first.get("case_restart")
    case["events"].append({"action": "INITIALIZED", "source": "synthetic"})
    first.put(case)

    second = PostgresCaseStore(postgres_database, "ws_restart")
    restored = second.get("case_restart")
    assert restored["image_id"] == "case_restart"
    assert restored["revision"] == 0
    assert restored["events"] == [{"action": "INITIALIZED", "source": "synthetic"}]

    restored["revision"] += 1
    restored["review_history"].append({"reviewer": "Synthetic reviewer", "grade": 2})
    second.put(restored)

    third = PostgresCaseStore(postgres_database, "ws_restart")
    updated = third.get("case_restart")
    assert updated["revision"] == 1
    assert updated["review_history"] == [{"reviewer": "Synthetic reviewer", "grade": 2}]


def test_case_update_transaction_rolls_back(postgres_database: PostgresDatabase):
    SchemaMigrator(postgres_database).migrate()
    store = PostgresCaseStore(postgres_database, "ws_case_rollback")
    case = store.get("case_rollback")
    case["events"].append({"action": "COMMITTED"})
    store.put(case)
    schema = sql.Identifier(postgres_database.settings.schema)

    with pytest.raises(RuntimeError, match="planned case rollback"):
        with postgres_database.transaction() as connection:
            connection.execute(
                sql.SQL(
                    "UPDATE {}.review_cases SET payload = jsonb_set(payload, "
                        "'{{state}}', '\"PARTIAL\"'::jsonb) "
                    "WHERE workspace_id = %s AND case_id = %s"
                ).format(schema),
                ("ws_case_rollback", "case_rollback"),
            )
            raise RuntimeError("planned case rollback")

    assert store.get("case_rollback")["state"] == "PENDING"


def test_independent_postgres_connections_reject_stale_case_update(
    postgres_database: PostgresDatabase,
):
    SchemaMigrator(postgres_database).migrate()
    first = PostgresCaseStore(postgres_database, "ws_conflict")
    second = PostgresCaseStore(postgres_database, "ws_conflict")
    seed = first.get("case_conflict")
    first.put(seed)
    first_view = first.get("case_conflict")
    second_view = second.get("case_conflict")

    first_view["revision"] += 1
    first_view["events"].append({"action": "FIRST_COMMIT"})
    first.put(first_view)

    second_view["revision"] += 1
    second_view["events"].append({"action": "STALE_COMMIT"})
    with pytest.raises(CaseConflictError, match="Case changed; reload"):
        second.put(second_view)

    current = PostgresCaseStore(postgres_database, "ws_conflict").get("case_conflict")
    assert current["revision"] == 1
    assert current["events"] == [{"action": "FIRST_COMMIT"}]


def test_revision_change_rejects_payload_changed_after_observation(
    postgres_database: PostgresDatabase,
):
    SchemaMigrator(postgres_database).migrate()
    first = PostgresCaseStore(postgres_database, "ws_payload_conflict")
    second = PostgresCaseStore(postgres_database, "ws_payload_conflict")
    first.put(first.get("case_payload_conflict"))
    first_view = first.get("case_payload_conflict")
    stale_view = second.get("case_payload_conflict")

    first_view["events"].append({"action": "AUTOMATIC_ENRICHMENT"})
    first.put(first_view)
    stale_view["revision"] += 1
    stale_view["events"].append({"action": "STALE_REVIEW"})

    with pytest.raises(CaseConflictError, match="Case changed; reload"):
        second.put(stale_view)

    current = PostgresCaseStore(postgres_database, "ws_payload_conflict").get(
        "case_payload_conflict"
    )
    assert current["revision"] == 0
    assert current["events"] == [{"action": "AUTOMATIC_ENRICHMENT"}]


def test_case_store_isolates_same_case_id_by_workspace(
    postgres_database: PostgresDatabase,
):
    SchemaMigrator(postgres_database).migrate()
    workspace_a = PostgresCaseStore(postgres_database, "ws_case_a")
    workspace_b = PostgresCaseStore(postgres_database, "ws_case_b")

    case_a = workspace_a.get("case_shared")
    case_a["events"].append({"workspace": "a"})
    workspace_a.put(case_a)
    case_b = workspace_b.get("case_shared")
    case_b["events"].append({"workspace": "b"})
    workspace_b.put(case_b)

    assert workspace_a.get("case_shared")["events"] == [{"workspace": "a"}]
    assert workspace_b.get("case_shared")["events"] == [{"workspace": "b"}]
    assert [case["image_id"] for case in workspace_a.all_cases()] == ["case_shared"]
    assert [case["image_id"] for case in workspace_b.all_cases()] == ["case_shared"]


def test_all_cases_records_observation_for_same_revision_updates(
    postgres_database: PostgresDatabase,
):
    SchemaMigrator(postgres_database).migrate()
    writer = PostgresCaseStore(postgres_database, "ws_all_cases")
    seed = writer.get("case_all")
    writer.put(seed)

    reconciler = PostgresCaseStore(postgres_database, "ws_all_cases")
    cases = reconciler.all_cases()
    cases[0]["events"].append({"action": "RECONCILED"})
    reconciler.put(cases[0])

    assert PostgresCaseStore(postgres_database, "ws_all_cases").get("case_all")["events"] == [
        {"action": "RECONCILED"}
    ]


def _write_legacy_case_database(path: Path, case: dict) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE cases (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        cases = case if isinstance(case, list) else [case]
        connection.executemany(
            "INSERT INTO cases (id, data) VALUES (?, ?)",
            [(item["image_id"], json.dumps(item, sort_keys=True)) for item in cases],
        )
        connection.commit()
    finally:
        connection.close()


def _write_legacy_catalog(path: Path, profiles: list[dict]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE workspaces ("
            "id TEXT PRIMARY KEY, name TEXT NOT NULL, input_folder TEXT NOT NULL, "
            "output_folder TEXT NOT NULL, database_path TEXT NOT NULL, note TEXT, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_opened TEXT"
            ")"
        )
        connection.executemany(
            "INSERT INTO workspaces "
            "(id, name, input_folder, output_folder, database_path, note, "
            "created_at, updated_at, last_opened) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    profile["id"],
                    profile["name"],
                    profile["input_folder"],
                    profile["output_folder"],
                    profile["database_path"],
                    profile.get("note"),
                    profile["created_at"],
                    profile["updated_at"],
                    profile.get("last_opened"),
                )
                for profile in profiles
            ],
        )
        connection.commit()
    finally:
        connection.close()


def test_case_import_is_read_only_dry_run_and_idempotent(
    postgres_database: PostgresDatabase,
    tmp_path: Path,
):
    SchemaMigrator(postgres_database).migrate()
    source = tmp_path / "legacy-reviews.sqlite"
    case = {
        "image_id": "legacy-case",
        "revision": 2,
        "state": "REVIEWED",
        "events": [{"action": "REVIEW", "source": "synthetic"}],
        "review_history": [{"reviewer": "Synthetic reviewer"}],
    }
    _write_legacy_case_database(source, case)
    before = source.read_bytes()
    store = PostgresCaseStore(postgres_database, "ws_import")

    dry_run = store.import_sqlite_cases(source, dry_run=True)
    assert dry_run.discovered_cases == 1
    assert dry_run.imported_cases == 0
    assert dry_run.dry_run is True
    assert source.read_bytes() == before
    assert store.all_cases() == []

    imported = store.import_sqlite_cases(source)
    assert imported.imported_cases == 1
    assert imported.unchanged_cases == 0
    assert store.get("legacy-case")["revision"] == 2
    assert store.get("legacy-case")["review_history"] == case["review_history"]
    assert source.read_bytes() == before

    repeated = store.import_sqlite_cases(source)
    assert repeated.imported_cases == 0
    assert repeated.unchanged_cases == 1


def test_case_import_rejects_changed_source_without_merging(
    postgres_database: PostgresDatabase,
    tmp_path: Path,
):
    SchemaMigrator(postgres_database).migrate()
    source = tmp_path / "legacy-reviews.sqlite"
    _write_legacy_case_database(
        source,
        {"image_id": "legacy-conflict", "revision": 0, "events": [{"source": "one"}]},
    )
    store = PostgresCaseStore(postgres_database, "ws_import_conflict")
    store.import_sqlite_cases(source)

    source.unlink()
    _write_legacy_case_database(
        source,
        {"image_id": "legacy-conflict", "revision": 1, "events": [{"source": "two"}]},
    )
    with pytest.raises(CaseImportConflictError):
        store.import_sqlite_cases(source)

    current = store.get("legacy-conflict")
    assert current["revision"] == 0
    assert current["events"] == [{"source": "one"}]


def test_case_store_preserves_audit_and_provenance_payloads(
    postgres_database: PostgresDatabase,
):
    SchemaMigrator(postgres_database).migrate()
    store = PostgresCaseStore(postgres_database, "ws_provenance")
    case = store.get("case_provenance")
    case.update(
        {
            "admission": {
                "source_sha256": "a" * 64,
                "source_reference": "WORKSPACE_INPUT/synthetic.png",
                "retinal_modality": "CFP",
            },
            "global": {
                "grade": 3,
                "model_id": "retfound-aptos5",
                "provenance": {"source_sha256": "a" * 64, "runtime": "remote"},
            },
            "lesion": {
                "model_id": "prism-dr-5fold",
                "lesions": [],
                "provenance": {"analysis_sha256": "b" * 64, "transform_id": "identity"},
            },
            "review_history": [
                {"action": "CORRECT_GRADE", "reviewer": "Synthetic reviewer", "identity_assurance": "LOCAL_POC_SELF_DECLARED"}
            ],
            "ai_annotation_reviews": [
                {"detection_id": "ai-0123456789abcdef0123", "action": "REJECT", "original_score": 0.71}
            ],
            "resolver_evidence": {
                "method": "FILENAME",
                "source": "synthetic.png",
                "candidate": "patient-001",
            },
            "events": [
                {"action": "INFERENCE", "model_id": "retfound-aptos5", "timestamp": "2026-09-28T00:00:00+00:00"},
                {"action": "REVIEW", "reviewer": "Synthetic reviewer", "timestamp": "2026-09-28T00:01:00+00:00"},
            ],
        }
    )
    store.put(case)

    restored = PostgresCaseStore(postgres_database, "ws_provenance").get("case_provenance")
    for field in ("admission", "global", "lesion", "review_history", "ai_annotation_reviews", "resolver_evidence", "events"):
        assert restored[field] == case[field]


def test_application_selects_postgres_case_mode_without_sqlite_fallback(
    monkeypatch,
    tmp_path: Path,
    postgres_database: PostgresDatabase,
):
    monkeypatch.setenv(DATABASE_URL_ENV, postgres_database.settings.dsn)
    monkeypatch.setenv(DATABASE_SCHEMA_ENV, postgres_database.settings.schema)
    monkeypatch.delenv(CASE_STORE_MODE_ENV, raising=False)
    monkeypatch.delenv("DR_SUPPORT_STATE", raising=False)
    monkeypatch.delenv("DR_SUPPORT_WORKSPACE_CATALOG", raising=False)
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_ID", "ws_application")

    app = create_app(include_samples=False, include_demo_fixtures=False)

    assert app.state.case_store_mode == "postgres"
    assert isinstance(app.state.store, PostgresCaseStore)
    assert app.state.workspace_id == "ws_application"
    assert app.state.workspace_manager.database_status == "postgres"
    assert postgres_database.settings.dsn not in app.state.workspace_manager.active_payload()["database"]["path"]
    assert not (tmp_path / "reviews.sqlite").exists()


def test_application_defaults_to_postgres_and_requires_dsn_without_legacy_paths(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.delenv(CASE_STORE_MODE_ENV, raising=False)
    monkeypatch.delenv(DATABASE_URL_ENV, raising=False)
    monkeypatch.delenv("DR_SUPPORT_STATE", raising=False)
    monkeypatch.delenv("DR_SUPPORT_WORKSPACE_CATALOG", raising=False)

    with pytest.raises(DatabaseConfigurationError, match=DATABASE_URL_ENV):
        create_app(include_samples=False, include_demo_fixtures=False)

    assert not (tmp_path / "reviews.sqlite").exists()
    assert not (tmp_path / "workspaces.sqlite").exists()


def test_application_defaults_to_postgres_with_configured_dsn(
    monkeypatch,
    postgres_database: PostgresDatabase,
):
    monkeypatch.delenv(CASE_STORE_MODE_ENV, raising=False)
    monkeypatch.setenv(DATABASE_URL_ENV, postgres_database.settings.dsn)
    monkeypatch.setenv(DATABASE_SCHEMA_ENV, postgres_database.settings.schema)
    monkeypatch.delenv("DR_SUPPORT_STATE", raising=False)
    monkeypatch.delenv("DR_SUPPORT_WORKSPACE_CATALOG", raising=False)
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_ID", "ws_default_postgres")

    app = create_app(include_samples=False, include_demo_fixtures=False)

    assert app.state.case_store_mode == "postgres"
    assert isinstance(app.state.store, PostgresCaseStore)


def test_postgres_workspace_catalog_is_authoritative_and_switches_case_store(
    monkeypatch,
    tmp_path: Path,
    postgres_database: PostgresDatabase,
):
    monkeypatch.setenv(DATABASE_URL_ENV, postgres_database.settings.dsn)
    monkeypatch.setenv(DATABASE_SCHEMA_ENV, postgres_database.settings.schema)
    monkeypatch.setenv(CASE_STORE_MODE_ENV, "postgres")
    monkeypatch.delenv("DR_SUPPORT_WORKSPACE_ID", raising=False)
    catalog_path = tmp_path / "workspaces.sqlite"
    fallback_path = tmp_path / "reviews.sqlite"
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_CATALOG", str(catalog_path))
    monkeypatch.setenv("DR_SUPPORT_STATE", str(fallback_path))

    app = create_app(include_samples=False, include_demo_fixtures=False)
    client = TestClient(app)
    input_a = tmp_path / "input-a"
    output_a = tmp_path / "output-a"
    input_b = tmp_path / "input-b"
    output_b = tmp_path / "output-b"
    for path in (input_a, output_a, input_b, output_b):
        path.mkdir()

    first = client.post(
        "/v1/workspaces",
        json={
            "name": "Managed A",
            "input_folder": str(input_a),
            "output_folder": str(output_a),
            "database_path": str(tmp_path / "should-not-open.sqlite"),
            "note": "synthetic workspace A",
        },
    )
    assert first.status_code == 200
    first_profile = first.json()["workspace"]
    assert first_profile["database_path"] is None
    assert first.json()["database"]["status"] == "postgres"
    assert not (tmp_path / "should-not-open.sqlite").exists()

    updated = client.put(
        f"/v1/workspaces/{first_profile['id']}",
        json={
            "name": "Managed A updated",
            "input_folder": str(input_a),
            "output_folder": str(output_a),
            "note": "updated synthetic workspace",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["workspace"]["name"] == "Managed A updated"
    assert updated.json()["workspace"]["database_path"] is None
    assert not catalog_path.exists()
    assert not fallback_path.exists()

    first_case = app.state.store.get("shared-case")
    first_case["events"].append({"workspace": "a"})
    app.state.store.put(first_case)

    second = client.post(
        "/v1/workspaces",
        json={
            "name": "Managed B",
            "input_folder": str(input_b),
            "output_folder": str(output_b),
        },
    )
    assert second.status_code == 200
    second_profile = second.json()["workspace"]
    second_case = app.state.store.get("shared-case")
    second_case["events"].append({"workspace": "b"})
    app.state.store.put(second_case)
    assert app.state.store.get("shared-case")["events"] == [{"workspace": "b"}]

    opened = client.post(f"/v1/workspaces/{first_profile['id']}/open")
    assert opened.status_code == 200
    assert app.state.workspace_id == first_profile["id"]
    assert app.state.store.get("shared-case")["events"] == [{"workspace": "a"}]

    archived = client.delete(f"/v1/workspaces/{second_profile['id']}")
    assert archived.status_code == 200
    assert all(
        item["id"] != second_profile["id"]
        for item in client.get("/v1/workspaces").json()["workspaces"]
    )
    with postgres_database.session() as connection:
        schema = sql.Identifier(postgres_database.settings.schema)
        archived_at = connection.execute(
            sql.SQL("SELECT archived_at FROM {}.workspaces WHERE workspace_id = %s").format(schema),
            (second_profile["id"],),
        ).fetchone()[0]
        remaining_cases = connection.execute(
            sql.SQL("SELECT count(*) FROM {}.review_cases WHERE workspace_id = %s").format(schema),
            (second_profile["id"],),
        ).fetchone()[0]
    assert archived_at is not None
    assert remaining_cases == 1

    fresh = create_app(include_samples=False, include_demo_fixtures=False)
    assert fresh.state.workspace_manager.active_workspace.id == first_profile["id"]
    assert fresh.state.workspace_id == first_profile["id"]
    assert fresh.state.store.get("shared-case")["events"] == [{"workspace": "a"}]


def test_postgres_workspace_catalog_get_ignores_identity_only_and_archived_rows(
    postgres_database: PostgresDatabase,
    tmp_path: Path,
):
    from dr_support.contracts import WorkspaceProfile

    SchemaMigrator(postgres_database).migrate()
    catalog = PostgresWorkspaceCatalog(postgres_database)
    catalog.create_and_activate(
        WorkspaceProfile(
            id="ws_catalog_complete",
            name="Complete workspace",
            input_folder=str(tmp_path / "input"),
            output_folder=str(tmp_path / "output"),
            created_at="2026-09-28T00:00:00+00:00",
            updated_at="2026-09-28T00:00:00+00:00",
        )
    )
    PostgresCaseStore(postgres_database, "ws_catalog_identity_only").ensure_workspace()

    assert catalog.get("ws_catalog_complete").name == "Complete workspace"
    assert catalog.get("ws_catalog_identity_only") is None
    assert "ws_catalog_identity_only" not in {
        profile.id for profile in catalog.list_profiles()
    }

    catalog.create_and_activate(
        WorkspaceProfile(
            id="ws_catalog_archived",
            name="Archived workspace",
            input_folder=str(tmp_path / "archived-input"),
            output_folder=str(tmp_path / "archived-output"),
            created_at="2026-09-28T00:00:00+00:00",
            updated_at="2026-09-28T00:00:00+00:00",
        )
    )
    catalog.archive("ws_catalog_archived")
    assert catalog.get("ws_catalog_archived") is None


def test_postgres_workspace_mode_accepts_missing_database_path_but_requires_managed_fields(
    monkeypatch,
    tmp_path: Path,
    postgres_database: PostgresDatabase,
):
    monkeypatch.setenv(DATABASE_URL_ENV, postgres_database.settings.dsn)
    monkeypatch.setenv(DATABASE_SCHEMA_ENV, postgres_database.settings.schema)
    monkeypatch.setenv(CASE_STORE_MODE_ENV, "postgres")
    app = create_app(include_samples=False, include_demo_fixtures=False, workspace_id="ws_validation")
    client = TestClient(app)
    input_folder = tmp_path / "input"
    output_folder = tmp_path / "output"
    input_folder.mkdir()
    output_folder.mkdir()

    missing_database = client.post(
        "/v1/workspaces",
        json={
            "name": "No local database",
            "input_folder": str(input_folder),
            "output_folder": str(output_folder),
        },
    )
    assert missing_database.status_code == 200
    invalid = client.post(
        "/v1/workspaces",
        json={"name": "Missing folders"},
    )
    assert invalid.status_code == 422


def test_postgres_workspace_catalog_is_not_used_when_postgres_is_unavailable(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv(DATABASE_URL_ENV, "postgresql://postgres@127.0.0.1:59999/dr_support_test")
    monkeypatch.setenv(DATABASE_SCHEMA_ENV, "dr_support_test_unavailable")
    monkeypatch.setenv(CASE_STORE_MODE_ENV, "postgres")
    monkeypatch.setenv("DR_SUPPORT_DATABASE_CONNECT_TIMEOUT", "1")
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_CATALOG", str(tmp_path / "workspaces.sqlite"))
    monkeypatch.setenv("DR_SUPPORT_STATE", str(tmp_path / "reviews.sqlite"))

    with pytest.raises(DatabaseUnavailableError):
        create_app(include_samples=False, include_demo_fixtures=False, workspace_id="ws_outage")

    assert not (tmp_path / "workspaces.sqlite").exists()
    assert not (tmp_path / "reviews.sqlite").exists()


def _legacy_profile(workspace_id: str, database_path: Path) -> dict:
    return {
        "id": workspace_id,
        "name": f"Synthetic {workspace_id}",
        "input_folder": str(database_path.parent / f"input-{workspace_id}"),
        "output_folder": str(database_path.parent / f"output-{workspace_id}"),
        "database_path": str(database_path),
        "note": "synthetic migration fixture",
        "created_at": "2026-09-28T00:00:00+00:00",
        "updated_at": "2026-09-28T00:01:00+00:00",
        "last_opened": "2026-09-28T00:02:00+00:00",
    }


def test_legacy_inventory_reports_missing_duplicate_and_orphan_without_mutation(
    postgres_database: PostgresDatabase,
    tmp_path: Path,
):
    SchemaMigrator(postgres_database).migrate()
    referenced = tmp_path / "referenced.sqlite"
    missing = tmp_path / "missing.sqlite"
    orphan = tmp_path / "orphan.sqlite"
    _write_legacy_case_database(
        referenced,
        {"image_id": "synthetic-inventory", "revision": 1, "events": []},
    )
    orphan.write_bytes(b"synthetic orphan")
    catalog = tmp_path / "catalog.sqlite"
    profiles = [
        _legacy_profile("ws_inventory_a", referenced),
        _legacy_profile("ws_inventory_b", referenced),
        _legacy_profile("ws_inventory_missing", missing),
    ]
    _write_legacy_catalog(catalog, profiles)
    catalog_before = catalog.read_bytes()
    referenced_before = referenced.read_bytes()

    service = LegacySQLiteMigrationService(
        postgres_database, catalog, orphan_roots=(tmp_path,)
    )
    report = service.dry_run(ConsistencyBoundary.writer_quiesced("synthetic-window-1"))

    assert report.safe_to_proceed is False
    assert report.inventory.workspace_count == 3
    assert report.inventory.case_counts["ws_inventory_a"] == 1
    assert report.inventory.case_counts["ws_inventory_missing"] == 0
    assert any("missing" in conflict for conflict in report.conflicts)
    assert any("multiple workspaces" in conflict for conflict in report.conflicts)
    assert [item.path for item in report.inventory.orphan_files] == [str(orphan.resolve())]
    assert "Safe to proceed: NO" in report.render()
    assert catalog.read_bytes() == catalog_before
    assert referenced.read_bytes() == referenced_before


@pytest.mark.parametrize("sidecar_kind", ("wal", "journal"))
def test_legacy_inventory_records_readable_sidecar_without_mutating_or_importing(
    postgres_database: PostgresDatabase,
    tmp_path: Path,
    sidecar_kind: str,
):
    SchemaMigrator(postgres_database).migrate()
    workspace_db = tmp_path / "workspace.sqlite"
    _write_legacy_case_database(
        workspace_db,
        {"image_id": "synthetic-sidecar", "revision": 0, "events": []},
    )
    workspace_before = workspace_db.read_bytes()
    clean_source = _capture_source(workspace_db, "workspace_database", "ws_sidecar")

    sidecar_path = Path(f"{workspace_db}-{sidecar_kind}")
    sidecar_path.write_bytes(f"synthetic {sidecar_kind} state".encode("ascii"))
    sidecar_before = sidecar_path.read_bytes()
    source = _capture_source(workspace_db, "workspace_database", "ws_sidecar")
    repeated = _capture_source(workspace_db, "workspace_database", "ws_sidecar")
    sidecar = next(item for item in source.effective_state if item.kind == sidecar_kind)

    assert sidecar.status == "readable"
    assert source != clean_source
    assert source == repeated
    if sidecar_kind == "journal":
        assert source.status == "invalid"
        assert source.error == "SQLite rollback journal is present; source state is not stable"
    else:
        assert source.status == "readable"
    assert workspace_db.read_bytes() == workspace_before
    assert sidecar_path.read_bytes() == sidecar_before
    with postgres_database.session() as connection:
        schema = sql.Identifier(postgres_database.settings.schema)
        assert connection.execute(
            sql.SQL("SELECT count(*) FROM {}.workspaces").format(schema)
        ).fetchone()[0] == 0
        assert connection.execute(
            sql.SQL("SELECT count(*) FROM {}.review_cases").format(schema)
        ).fetchone()[0] == 0


def test_legacy_import_preserves_profiles_cases_receipt_and_is_idempotent(
    postgres_database: PostgresDatabase,
    tmp_path: Path,
):
    SchemaMigrator(postgres_database).migrate()
    workspace_db = tmp_path / "workspace.sqlite"
    cases = [
        {
            "image_id": "synthetic-case-a",
            "revision": 2,
            "state": "REVIEWED",
            "events": [{"action": "REVIEW", "source": "synthetic"}],
            "review_history": [{"reviewer": "Synthetic reviewer", "grade": 2}],
        },
        {
            "image_id": "synthetic-case-b",
            "revision": 0,
            "admission": {"source_reference": "synthetic/case-b.png"},
            "global": {"model_id": "retfound-aptos5", "grade": 1},
        },
    ]
    _write_legacy_case_database(workspace_db, cases)
    catalog = tmp_path / "catalog.sqlite"
    _write_legacy_catalog(catalog, [_legacy_profile("ws_imported", workspace_db)])
    catalog_before = catalog.read_bytes()
    workspace_before = workspace_db.read_bytes()
    service = LegacySQLiteMigrationService(postgres_database, catalog)
    boundary = ConsistencyBoundary.snapshot("synthetic-snapshot-1")
    plan = service.plan(boundary)

    assert plan.report.safe_to_proceed is True
    first = service.import_legacy(boundary, plan=plan)
    assert first.imported_workspaces == 1
    assert first.imported_cases == 2
    assert first.idempotent is False
    assert first.receipt_recorded is True

    schema = sql.Identifier(postgres_database.settings.schema)
    with postgres_database.session() as connection:
        profile = connection.execute(
            sql.SQL(
                "SELECT workspace_id, name, input_folder, output_folder, database_path, note "
                "FROM {}.workspaces WHERE workspace_id = %s"
            ).format(schema),
            ("ws_imported",),
        ).fetchone()
        imported_cases = connection.execute(
            sql.SQL(
                "SELECT case_id, revision, payload FROM {}.review_cases "
                "WHERE workspace_id = %s ORDER BY case_id"
            ).format(schema),
            ("ws_imported",),
        ).fetchall()
        receipt = connection.execute(
            sql.SQL(
                "SELECT source_set_sha256, catalog_sha256, consistency_kind, consistency_id, "
                "workspace_count, case_count FROM {}.legacy_migration_receipts"
            ).format(schema)
        ).fetchone()

    assert profile == (
        "ws_imported",
        "Synthetic ws_imported",
        str(tmp_path / "input-ws_imported"),
        str(tmp_path / "output-ws_imported"),
        str(workspace_db),
        "synthetic migration fixture",
    )
    assert [(row[0], row[1]) for row in imported_cases] == [
        ("synthetic-case-a", 2),
        ("synthetic-case-b", 0),
    ]
    assert imported_cases[0][2]["review_history"] == [
        {"reviewer": "Synthetic reviewer", "grade": 2}
    ]
    assert imported_cases[0][2]["state"] == "REVIEWED"
    assert imported_cases[0][2]["events"] == [{"action": "REVIEW", "source": "synthetic"}]
    assert imported_cases[1][2]["admission"] == {
        "source_reference": "synthetic/case-b.png"
    }
    assert imported_cases[1][2]["global"] == {"model_id": "retfound-aptos5", "grade": 1}
    assert receipt == (
        plan.inventory.source_set_sha256,
        plan.inventory.catalog.sha256,
        "snapshot",
        "synthetic-snapshot-1",
        1,
        2,
    )

    repeated = service.import_legacy(
        boundary, expected_source_set_sha256=plan.inventory.source_set_sha256
    )
    assert repeated.idempotent is True
    assert repeated.imported_workspaces == 0
    assert repeated.imported_cases == 0
    assert catalog.read_bytes() == catalog_before
    assert workspace_db.read_bytes() == workspace_before


def test_legacy_import_requires_boundary_and_rejects_changed_source(
    postgres_database: PostgresDatabase,
    tmp_path: Path,
):
    SchemaMigrator(postgres_database).migrate()
    workspace_db = tmp_path / "workspace.sqlite"
    _write_legacy_case_database(
        workspace_db,
        {"image_id": "synthetic-conflict", "revision": 0, "events": [{"source": "one"}]},
    )
    catalog = tmp_path / "catalog.sqlite"
    _write_legacy_catalog(catalog, [_legacy_profile("ws_conflict", workspace_db)])
    service = LegacySQLiteMigrationService(postgres_database, catalog)

    with pytest.raises(MigrationConsistencyError):
        service.import_legacy()

    boundary = ConsistencyBoundary.writer_quiesced("synthetic-window-2")
    plan = service.plan(boundary)
    with pytest.raises(LegacySourceConflictError, match="Expected source-set"):
        service.import_legacy(boundary, expected_source_set_sha256="0" * 64)
    schema = sql.Identifier(postgres_database.settings.schema)
    with postgres_database.session() as connection:
        assert connection.execute(
            sql.SQL("SELECT count(*) FROM {}.workspaces").format(schema)
        ).fetchone()[0] == 0
        assert connection.execute(
            sql.SQL("SELECT count(*) FROM {}.review_cases").format(schema)
        ).fetchone()[0] == 0
        assert connection.execute(
            sql.SQL("SELECT count(*) FROM {}.legacy_migration_receipts").format(schema)
        ).fetchone()[0] == 0
    service.import_legacy(boundary, plan=plan)
    connection = sqlite3.connect(workspace_db)
    try:
        connection.execute(
            "UPDATE cases SET data = ? WHERE id = ?",
            (
                json.dumps(
                    {
                        "image_id": "synthetic-conflict",
                        "revision": 1,
                        "events": [{"source": "two"}],
                    },
                    sort_keys=True,
                ),
                "synthetic-conflict",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(LegacySourceConflictError, match="source set"):
        service.import_legacy(boundary, plan=plan)

    with postgres_database.session() as connection:
        stored = connection.execute(
            sql.SQL(
                "SELECT revision, payload FROM {}.review_cases "
                "WHERE workspace_id = %s AND case_id = %s"
            ).format(schema),
            ("ws_conflict", "synthetic-conflict"),
        ).fetchone()
    assert stored[0] == 0
    assert stored[1]["events"] == [{"source": "one"}]


def test_legacy_import_rolls_back_when_source_changes_during_import(
    postgres_database: PostgresDatabase,
    tmp_path: Path,
    monkeypatch,
):
    SchemaMigrator(postgres_database).migrate()
    workspace_db = tmp_path / "workspace.sqlite"
    _write_legacy_case_database(
        workspace_db,
        {"image_id": "synthetic-atomic", "revision": 0, "events": [{"source": "one"}]},
    )
    catalog = tmp_path / "catalog.sqlite"
    _write_legacy_catalog(catalog, [_legacy_profile("ws_atomic", workspace_db)])
    service = LegacySQLiteMigrationService(postgres_database, catalog)
    expected_source_set_sha256 = service.inventory().source_set_sha256
    original_inventory = service.inventory
    inventory_calls = 0

    def inventory_with_source_change():
        nonlocal inventory_calls
        inventory_calls += 1
        if inventory_calls == 3:
            connection = sqlite3.connect(workspace_db)
            try:
                connection.execute(
                    "UPDATE cases SET data = ? WHERE id = ?",
                    (
                        json.dumps(
                            {
                                "image_id": "synthetic-atomic",
                                "revision": 1,
                                "events": [{"source": "two"}],
                            },
                            sort_keys=True,
                        ),
                        "synthetic-atomic",
                    ),
                )
                connection.commit()
            finally:
                connection.close()
        return original_inventory()

    monkeypatch.setattr(service, "inventory", inventory_with_source_change)
    boundary = ConsistencyBoundary.writer_quiesced("synthetic-window-atomic")

    with pytest.raises(LegacySourceConflictError, match="changed during import"):
        service.import_legacy(
            boundary, expected_source_set_sha256=expected_source_set_sha256
        )

    schema = sql.Identifier(postgres_database.settings.schema)
    with postgres_database.session() as connection:
        workspace_count = connection.execute(
            sql.SQL("SELECT count(*) FROM {}.workspaces WHERE workspace_id = %s").format(schema),
            ("ws_atomic",),
        ).fetchone()[0]
        case_count = connection.execute(
            sql.SQL("SELECT count(*) FROM {}.review_cases WHERE workspace_id = %s").format(schema),
            ("ws_atomic",),
        ).fetchone()[0]
        receipt_count = connection.execute(
            sql.SQL("SELECT count(*) FROM {}.legacy_migration_receipts WHERE catalog_path = %s").format(schema),
            (str(catalog.resolve()),),
        ).fetchone()[0]

    assert workspace_count == 0
    assert case_count == 0
    assert receipt_count == 0


def test_legacy_import_rejects_preexisting_extra_case_without_deleting_it(
    postgres_database: PostgresDatabase,
    tmp_path: Path,
):
    SchemaMigrator(postgres_database).migrate()
    workspace_db = tmp_path / "workspace.sqlite"
    _write_legacy_case_database(
        workspace_db,
        {"image_id": "synthetic-imported", "revision": 0, "events": []},
    )
    catalog = tmp_path / "catalog.sqlite"
    _write_legacy_catalog(catalog, [_legacy_profile("ws_extra_case", workspace_db)])
    service = LegacySQLiteMigrationService(postgres_database, catalog)
    boundary = ConsistencyBoundary.snapshot("synthetic-extra-case-snapshot")
    plan = service.plan(boundary)
    service.import_legacy(boundary, plan=plan)

    target = PostgresCaseStore(postgres_database, "ws_extra_case")
    extra = target.get("synthetic-extra")
    extra["events"] = [{"source": "pre-existing-postgres"}]
    target.put(extra)
    extra_before = target.get("synthetic-extra")
    repeated = service.plan(boundary)

    assert repeated.report.safe_to_proceed is False
    assert any("extra PostgreSQL cases" in conflict for conflict in repeated.report.conflicts)

    with pytest.raises(MigrationNotSafeError, match="not safe to proceed"):
        service.import_legacy(
            boundary, expected_source_set_sha256=plan.inventory.source_set_sha256
        )

    assert target.get("synthetic-extra") == extra_before


def test_legacy_import_rejects_divergent_target_case_identity_and_revision(
    postgres_database: PostgresDatabase,
    tmp_path: Path,
):
    SchemaMigrator(postgres_database).migrate()
    workspace_db = tmp_path / "workspace.sqlite"
    _write_legacy_case_database(
        workspace_db,
        {"image_id": "synthetic-target", "revision": 0, "events": []},
    )
    catalog = tmp_path / "catalog.sqlite"
    _write_legacy_catalog(catalog, [_legacy_profile("ws_target_divergence", workspace_db)])
    service = LegacySQLiteMigrationService(postgres_database, catalog)
    boundary = ConsistencyBoundary.snapshot("synthetic-target-divergence-snapshot")
    plan = service.plan(boundary)
    service.import_legacy(boundary, plan=plan)

    schema = sql.Identifier(postgres_database.settings.schema)
    with postgres_database.transaction() as connection:
        stored_payload = connection.execute(
            sql.SQL(
                "SELECT payload FROM {}.review_cases "
                "WHERE workspace_id = %s AND case_id = %s"
            ).format(schema),
            ("ws_target_divergence", "synthetic-target"),
        ).fetchone()[0]
        stored_payload["image_id"] = "synthetic-divergent-target"
        stored_payload["revision"] = 99
        connection.execute(
            sql.SQL(
                "UPDATE {}.review_cases SET payload = %s "
                "WHERE workspace_id = %s AND case_id = %s"
            ).format(schema),
            (Jsonb(stored_payload), "ws_target_divergence", "synthetic-target"),
        )

    with pytest.raises(LegacySourceConflictError, match="differs in PostgreSQL"):
        service.import_legacy(
            boundary,
            plan=plan,
            expected_source_set_sha256=plan.inventory.source_set_sha256,
        )

    with postgres_database.session() as connection:
        stored = connection.execute(
            sql.SQL(
                "SELECT revision, payload FROM {}.review_cases "
                "WHERE workspace_id = %s AND case_id = %s"
            ).format(schema),
            ("ws_target_divergence", "synthetic-target"),
        ).fetchone()
    assert stored[0] == 0
    assert stored[1]["image_id"] == "synthetic-divergent-target"
    assert stored[1]["revision"] == 99
