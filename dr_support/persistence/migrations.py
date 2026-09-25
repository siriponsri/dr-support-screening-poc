"""Deterministic, forward-only PostgreSQL schema migrations."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from psycopg import sql

from .database import PostgresDatabase


class MigrationError(RuntimeError):
    """The database schema history is incompatible with this release."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        body = "\0".join((str(self.version), self.name, *self.statements))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


MIGRATIONS = (
    Migration(
        version=1,
        name="workspace_identity",
        statements=(
            """
            CREATE TABLE {schema}.workspaces (
                workspace_id TEXT PRIMARY KEY,
                revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK (length(btrim(workspace_id)) > 0)
            )
            """,
        ),
    ),
    Migration(
        version=2,
        name="workspace_scoped_review_cases",
        statements=(
            """
            CREATE TABLE {schema}.review_cases (
                workspace_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
                payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (workspace_id, case_id),
                FOREIGN KEY (workspace_id)
                    REFERENCES {schema}.workspaces (workspace_id)
                    ON DELETE RESTRICT,
                CHECK (length(btrim(case_id)) > 0)
            )
            """,
        ),
    ),
)
LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version


@dataclass(frozen=True)
class MigrationResult:
    previous_version: int
    current_version: int
    applied_versions: tuple[int, ...]


class SchemaMigrator:
    """Apply the immutable migration sequence inside one database transaction."""

    def __init__(
        self,
        database: PostgresDatabase,
        *,
        schema: str | None = None,
        migrations: tuple[Migration, ...] = MIGRATIONS,
    ) -> None:
        self.database = database
        self.schema = schema or database.settings.schema
        self.migrations = migrations
        expected_versions = tuple(range(1, len(migrations) + 1))
        actual_versions = tuple(migration.version for migration in migrations)
        if actual_versions != expected_versions:
            raise ValueError("Migrations must be ordered, contiguous, and start at version 1")

    def migrate(self, *, target_version: int | None = None) -> MigrationResult:
        latest = self.migrations[-1].version if self.migrations else 0
        target = latest if target_version is None else target_version
        if target < 0 or target > latest:
            raise MigrationError(f"Schema target version must be between 0 and {latest}")

        identifier = sql.Identifier(self.schema)
        with self.database.transaction() as connection:
            connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(identifier))
            connection.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {}.schema_migrations (
                        version INTEGER PRIMARY KEY CHECK (version > 0),
                        name TEXT NOT NULL,
                        checksum TEXT NOT NULL,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                ).format(identifier)
            )
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"{self.schema}.schema_migrations",),
            )
            rows = connection.execute(
                sql.SQL(
                    "SELECT version, name, checksum FROM {}.schema_migrations ORDER BY version"
                ).format(identifier)
            ).fetchall()
            applied = {row[0]: (row[1], row[2]) for row in rows}
            self._validate_history(applied)
            previous = max(applied, default=0)
            if target < previous:
                raise MigrationError(
                    f"Schema downgrade from version {previous} to {target} is not supported"
                )

            applied_now: list[int] = []
            for migration in self.migrations:
                if migration.version > target or migration.version in applied:
                    continue
                for statement in migration.statements:
                    connection.execute(sql.SQL(statement).format(schema=identifier))
                connection.execute(
                    sql.SQL(
                        "INSERT INTO {}.schema_migrations (version, name, checksum) "
                        "VALUES (%s, %s, %s)"
                    ).format(identifier),
                    (migration.version, migration.name, migration.checksum),
                )
                applied_now.append(migration.version)

        return MigrationResult(
            previous_version=previous,
            current_version=target,
            applied_versions=tuple(applied_now),
        )

    def _validate_history(self, applied: dict[int, tuple[str, str]]) -> None:
        known = {migration.version: migration for migration in self.migrations}
        for version, (name, checksum) in applied.items():
            migration = known.get(version)
            if migration is None:
                raise MigrationError(f"Database has unknown schema version {version}")
            if name != migration.name or checksum != migration.checksum:
                raise MigrationError(f"Schema migration {version} does not match this release")
        if applied and tuple(applied) != tuple(range(1, max(applied) + 1)):
            raise MigrationError("Database schema history contains a version gap")
