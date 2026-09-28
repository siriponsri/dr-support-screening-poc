"""PostgreSQL workspace/catalog persistence for managed workspace mode."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from psycopg import sql

from ..contracts import WorkspaceProfile
from .database import PostgresDatabase


MANAGED_STORAGE_LABEL = "Managed PostgreSQL storage"


def _timestamp(value: datetime | str | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class PostgresWorkspaceCatalog:
    """Persist active workspace profiles without a parallel SQLite catalog."""

    _SELECT_COLUMNS = """
        workspace_id, name, input_folder, output_folder, database_path,
        note, created_at, updated_at, last_opened
    """

    def __init__(self, database: PostgresDatabase) -> None:
        self.database = database
        self._schema = sql.Identifier(database.settings.schema)

    @staticmethod
    def _profile(row: tuple[Any, ...]) -> WorkspaceProfile:
        return WorkspaceProfile.model_validate(
            {
                "id": row[0],
                "name": row[1],
                "input_folder": row[2],
                "output_folder": row[3],
                "database_path": row[4],
                "note": row[5],
                "created_at": _timestamp(row[6]),
                "updated_at": _timestamp(row[7]),
                "last_opened": _timestamp(row[8]),
            }
        )

    def list_profiles(self) -> list[WorkspaceProfile]:
        try:
            with self.database.session() as connection:
                rows = connection.execute(
                    sql.SQL(
                        "SELECT " + self._SELECT_COLUMNS + " FROM {}.workspaces "
                        "WHERE archived_at IS NULL AND name IS NOT NULL "
                        "ORDER BY name COLLATE \"C\", workspace_id"
                    ).format(self._schema)
                ).fetchall()
            return [self._profile(row) for row in rows]
        except Exception as exc:
            _raise_catalog_error("could not read", exc)

    def get(self, workspace_id: str) -> WorkspaceProfile | None:
        try:
            with self.database.session() as connection:
                row = connection.execute(
                    sql.SQL(
                        "SELECT " + self._SELECT_COLUMNS + " FROM {}.workspaces "
                        "WHERE workspace_id = %s AND archived_at IS NULL "
                        "AND name IS NOT NULL AND input_folder IS NOT NULL "
                        "AND output_folder IS NOT NULL"
                    ).format(self._schema),
                    (workspace_id,),
                ).fetchone()
            return self._profile(row) if row else None
        except Exception as exc:
            _raise_catalog_error("could not read", exc)

    def latest_opened(self) -> WorkspaceProfile | None:
        try:
            with self.database.session() as connection:
                row = connection.execute(
                    sql.SQL(
                        "SELECT " + self._SELECT_COLUMNS + " FROM {}.workspaces "
                        "WHERE archived_at IS NULL AND name IS NOT NULL AND last_opened IS NOT NULL "
                        "ORDER BY last_opened DESC, workspace_id LIMIT 1"
                    ).format(self._schema)
                ).fetchone()
            return self._profile(row) if row else None
        except Exception as exc:
            _raise_catalog_error("could not read", exc)

    def create_and_activate(self, profile: WorkspaceProfile) -> WorkspaceProfile:
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    sql.SQL(
                        "INSERT INTO {}.workspaces "
                        "(workspace_id, name, input_folder, output_folder, database_path, note, "
                        "created_at, updated_at, last_opened) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    ).format(self._schema),
                    (
                        profile.id,
                        profile.name,
                        profile.input_folder,
                        profile.output_folder,
                        profile.database_path,
                        profile.note,
                        profile.created_at,
                        profile.updated_at,
                        profile.last_opened,
                    ),
                )
            return profile
        except Exception as exc:
            _raise_catalog_error("could not write", exc)

    def update_and_activate(self, profile: WorkspaceProfile) -> WorkspaceProfile:
        try:
            with self.database.transaction() as connection:
                updated = connection.execute(
                    sql.SQL(
                        "UPDATE {}.workspaces SET name = %s, input_folder = %s, "
                        "output_folder = %s, database_path = %s, note = %s, "
                        "updated_at = %s, last_opened = %s "
                        "WHERE workspace_id = %s AND archived_at IS NULL"
                    ).format(self._schema),
                    (
                        profile.name,
                        profile.input_folder,
                        profile.output_folder,
                        profile.database_path,
                        profile.note,
                        profile.updated_at,
                        profile.last_opened,
                        profile.id,
                    ),
                ).rowcount
                if updated != 1:
                    from ..services.workspaces import WorkspaceNotFoundError

                    raise WorkspaceNotFoundError(profile.id)
            return profile
        except Exception as exc:
            from ..services.workspaces import WorkspaceNotFoundError

            if isinstance(exc, WorkspaceNotFoundError):
                raise
            _raise_catalog_error("could not write", exc)

    def activate(self, workspace_id: str, opened_at: str) -> WorkspaceProfile:
        try:
            with self.database.transaction() as connection:
                updated = connection.execute(
                    sql.SQL(
                        "UPDATE {}.workspaces SET last_opened = %s, "
                        "updated_at = updated_at WHERE workspace_id = %s "
                        "AND archived_at IS NULL AND name IS NOT NULL"
                    ).format(self._schema),
                    (opened_at, workspace_id),
                ).rowcount
                if updated != 1:
                    from ..services.workspaces import WorkspaceNotFoundError

                    raise WorkspaceNotFoundError(workspace_id)
                row = connection.execute(
                    sql.SQL(
                        "SELECT " + self._SELECT_COLUMNS + " FROM {}.workspaces "
                        "WHERE workspace_id = %s"
                    ).format(self._schema),
                    (workspace_id,),
                ).fetchone()
            return self._profile(row)
        except Exception as exc:
            from ..services.workspaces import WorkspaceNotFoundError

            if isinstance(exc, WorkspaceNotFoundError):
                raise
            _raise_catalog_error("could not write", exc)

    def archive(self, workspace_id: str) -> None:
        try:
            with self.database.transaction() as connection:
                updated = connection.execute(
                    sql.SQL(
                        "UPDATE {}.workspaces SET archived_at = CURRENT_TIMESTAMP, "
                        "updated_at = CURRENT_TIMESTAMP WHERE workspace_id = %s "
                        "AND archived_at IS NULL AND name IS NOT NULL"
                    ).format(self._schema),
                    (workspace_id,),
                ).rowcount
                if updated != 1:
                    from ..services.workspaces import WorkspaceNotFoundError

                    raise WorkspaceNotFoundError(workspace_id)
        except Exception as exc:
            from ..services.workspaces import WorkspaceNotFoundError

            if isinstance(exc, WorkspaceNotFoundError):
                raise
            _raise_catalog_error("could not write", exc)


def _raise_catalog_error(action: str, error: Exception) -> None:
    from ..services.workspaces import WorkspaceCatalogError

    raise WorkspaceCatalogError(f"PostgreSQL workspace catalog {action}") from error
