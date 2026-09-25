"""Focused unit and opt-in integration tests for the M1 PostgreSQL foundation."""

from __future__ import annotations

import os
import re
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation

from dr_support.persistence import (
    DatabaseConfigurationError,
    DatabaseUnavailableError,
    LATEST_SCHEMA_VERSION,
    PostgresDatabase,
    PostgresSettings,
    SchemaMigrator,
)
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
