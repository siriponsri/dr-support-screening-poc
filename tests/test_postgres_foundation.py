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

from dr_support.persistence import (
    CaseConflictError,
    CaseImportConflictError,
    PostgresCaseStore,
    DatabaseConfigurationError,
    DatabaseUnavailableError,
    LATEST_SCHEMA_VERSION,
    PostgresDatabase,
    PostgresSettings,
    SchemaMigrator,
)
from dr_support.persistence.config import CASE_STORE_MODE_ENV, DATABASE_SCHEMA_ENV, DATABASE_URL_ENV
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
        connection.execute(
            "INSERT INTO cases (id, data) VALUES (?, ?)",
            (case["image_id"], json.dumps(case, sort_keys=True)),
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
    monkeypatch.setenv(CASE_STORE_MODE_ENV, "postgres")
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_ID", "ws_application")

    app = create_app(include_samples=False, include_demo_fixtures=False)

    assert app.state.case_store_mode == "postgres"
    assert isinstance(app.state.store, PostgresCaseStore)
    assert app.state.workspace_id == "ws_application"
    assert app.state.workspace_manager.database_status == "postgres"
    assert postgres_database.settings.dsn not in app.state.workspace_manager.active_payload()["database"]["path"]
    assert not (tmp_path / "reviews.sqlite").exists()
