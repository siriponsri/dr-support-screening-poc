"""Catalog persistence and active-store switching for S2 workspaces."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from ..contracts import WorkspaceInput, WorkspaceProfile, is_absolute_local_path
from ..store import Store
from .pickers import NativePicker


class WorkspaceError(RuntimeError):
    """Base class for expected workspace service failures."""


class WorkspaceCatalogError(WorkspaceError):
    """The workspace catalog could not be read or written."""


class WorkspaceNotFoundError(WorkspaceError):
    """A requested workspace id is not in the catalog."""


class WorkspaceActiveError(WorkspaceError):
    """The currently active workspace cannot be removed from the catalog."""


class WorkspaceDatabaseError(WorkspaceError):
    """A workspace database is missing, inaccessible, or not SQLite."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceCatalog:
    """SQLite catalog independent of every workspace's review database."""

    _TABLE = """
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            input_folder TEXT NOT NULL,
            output_folder TEXT NOT NULL,
            database_path TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_opened TEXT
        )
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock = RLock()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(str(self.path), check_same_thread=False)
            self.db.execute("PRAGMA busy_timeout=5000")
            self.db.execute(self._TABLE)
            columns = {row[1] for row in self.db.execute("PRAGMA table_info(workspaces)")}
            if "note" not in columns:
                self.db.execute("ALTER TABLE workspaces ADD COLUMN note TEXT")
            self.db.commit()
        except (OSError, sqlite3.DatabaseError) as exc:
            try:
                self.db.close()
            except AttributeError:
                pass
            raise WorkspaceCatalogError(f"Workspace catalog is unavailable: {exc}") from exc

    @staticmethod
    def _profile(row) -> WorkspaceProfile:
        return WorkspaceProfile.model_validate(
            {
                "id": row[0],
                "name": row[1],
                "input_folder": row[2],
                "output_folder": row[3],
                "database_path": row[4],
                "note": row[5],
                "created_at": row[6],
                "updated_at": row[7],
                "last_opened": row[8],
            }
        )

    def list_profiles(self) -> list[WorkspaceProfile]:
        with self.lock:
            try:
                rows = self.db.execute(
                    "SELECT id, name, input_folder, output_folder, database_path, note, "
                    "created_at, updated_at, last_opened "
                    "FROM workspaces ORDER BY name COLLATE NOCASE, id"
                ).fetchall()
                return [self._profile(row) for row in rows]
            except (sqlite3.DatabaseError, ValueError) as exc:
                raise WorkspaceCatalogError(f"Workspace catalog could not be read: {exc}") from exc

    def get(self, workspace_id: str) -> WorkspaceProfile | None:
        with self.lock:
            try:
                row = self.db.execute(
                    "SELECT id, name, input_folder, output_folder, database_path, note, "
                    "created_at, updated_at, last_opened FROM workspaces WHERE id=?",
                    (workspace_id,),
                ).fetchone()
                return self._profile(row) if row else None
            except (sqlite3.DatabaseError, ValueError) as exc:
                raise WorkspaceCatalogError(f"Workspace catalog could not be read: {exc}") from exc

    def create_and_activate(self, profile: WorkspaceProfile) -> WorkspaceProfile:
        with self.lock:
            try:
                with self.db:
                    self.db.execute(
                        "INSERT INTO workspaces "
                        "(id, name, input_folder, output_folder, database_path, note, created_at, updated_at, last_opened) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            except sqlite3.DatabaseError as exc:
                raise WorkspaceCatalogError(f"Workspace catalog could not be written: {exc}") from exc

    def update_and_activate(self, profile: WorkspaceProfile) -> WorkspaceProfile:
        with self.lock:
            try:
                with self.db:
                    cursor = self.db.execute(
                        "UPDATE workspaces SET name=?, input_folder=?, output_folder=?, database_path=?, note=?, "
                        "updated_at=?, last_opened=? WHERE id=?",
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
                    )
                    if cursor.rowcount != 1:
                        raise WorkspaceNotFoundError(profile.id)
                return profile
            except WorkspaceNotFoundError:
                raise
            except sqlite3.DatabaseError as exc:
                raise WorkspaceCatalogError(f"Workspace catalog could not be written: {exc}") from exc

    def activate(self, workspace_id: str, opened_at: str) -> WorkspaceProfile:
        with self.lock:
            try:
                with self.db:
                    cursor = self.db.execute(
                        "UPDATE workspaces SET last_opened=? WHERE id=?",
                        (opened_at, workspace_id),
                    )
                    if cursor.rowcount != 1:
                        raise WorkspaceNotFoundError(workspace_id)
                    row = self.db.execute(
                        "SELECT id, name, input_folder, output_folder, database_path, note, "
                        "created_at, updated_at, last_opened FROM workspaces WHERE id=?",
                        (workspace_id,),
                    ).fetchone()
                return self._profile(row)
            except WorkspaceNotFoundError:
                raise
            except (sqlite3.DatabaseError, ValueError) as exc:
                raise WorkspaceCatalogError(f"Workspace catalog could not be written: {exc}") from exc

    def delete(self, workspace_id: str) -> None:
        with self.lock:
            try:
                with self.db:
                    cursor = self.db.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))
                    if cursor.rowcount != 1:
                        raise WorkspaceNotFoundError(workspace_id)
            except WorkspaceNotFoundError:
                raise
            except sqlite3.DatabaseError as exc:
                raise WorkspaceCatalogError(f"Workspace catalog could not be written: {exc}") from exc


class WorkspaceManager:
    """Resolve startup state and safely switch the process-local review store."""

    def __init__(
        self,
        root: str | Path,
        *,
        state_path: str | Path | None = None,
        picker: NativePicker | None = None,
    ):
        self.root = Path(root)
        self.lock = RLock()
        self.picker = picker or NativePicker()
        self.catalog_path = Path(
            (os.environ.get("DR_SUPPORT_WORKSPACE_CATALOG") or "").strip()
            or self.root / "local-state/bridge/workspaces.sqlite"
        )
        self.fallback_path = Path(
            (os.environ.get("DR_SUPPORT_STATE") or "").strip()
            or self.root / "local-state/bridge/reviews.sqlite"
        )
        self.catalog: WorkspaceCatalog | None = None
        self.warnings: list[str] = []
        self.app = None
        self.active_workspace: WorkspaceProfile | None = None
        self.database_status = "fallback"
        self.database_path = str(state_path or self.fallback_path)

        try:
            self.catalog = WorkspaceCatalog(self.catalog_path)
        except WorkspaceCatalogError as exc:
            self._warn(str(exc))

        if state_path is not None:
            self.store = Store(state_path)
            self.database_path = str(state_path)
            return

        self.store = self._resolve_startup_store()

    def _warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def _resolve_startup_store(self) -> Store:
        if self.catalog is not None:
            try:
                profiles = self.catalog.list_profiles()
            except WorkspaceCatalogError as exc:
                self._warn(str(exc))
                profiles = []
            candidates = sorted(
                (profile for profile in profiles if profile.last_opened),
                key=lambda profile: profile.last_opened or "",
                reverse=True,
            )
            for profile in candidates:
                try:
                    store = self._open_workspace_database(profile.database_path)
                except WorkspaceDatabaseError as exc:
                    self._warn(f"Workspace '{profile.name}' could not be restored: {exc}")
                    continue
                self.active_workspace = profile
                self.database_status = "ready"
                self.database_path = profile.database_path
                return store

        store = self._open_fallback_store()
        if self.catalog is not None and any(profile.last_opened for profile in locals().get("profiles", [])):
            self._warn("No last-opened workspace database was usable; using the fallback review database.")
        return store

    def _open_fallback_store(self) -> Store:
        candidates = [self.fallback_path]
        default_path = self.root / "local-state/bridge/reviews.sqlite"
        if self.fallback_path != default_path:
            candidates.append(default_path)
        errors: list[str] = []
        for path in candidates:
            try:
                store = Store(path)
                self.database_path = str(path)
                self.database_status = "fallback"
                return store
            except (OSError, sqlite3.DatabaseError) as exc:
                errors.append(f"{path}: {exc}")
        raise WorkspaceDatabaseError("No usable fallback review database: " + "; ".join(errors))

    @staticmethod
    def _open_workspace_database(database_path: str) -> Store:
        try:
            path = Path(database_path)
            if not is_absolute_local_path(database_path) or not path.is_absolute():
                raise WorkspaceDatabaseError("Database path must be an absolute local path")
            if not path.parent.exists() or not path.parent.is_dir():
                raise WorkspaceDatabaseError("Database parent folder does not exist")
            if path.exists() and not path.is_file():
                raise WorkspaceDatabaseError("Database path is not a file")
            return Store(path)
        except WorkspaceDatabaseError:
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise WorkspaceDatabaseError(f"Database could not be opened: {exc}") from exc

    def attach(self, app) -> None:
        self.app = app
        app.state.workspace_manager = self
        app.state.workspace_picker = self.picker
        app.state.store = self.store

    def _require_catalog(self) -> WorkspaceCatalog:
        if self.catalog is None:
            raise WorkspaceCatalogError("Workspace catalog is unavailable")
        return self.catalog

    def _swap_store(self, store: Store, profile: WorkspaceProfile) -> None:
        self.store = store
        self.active_workspace = profile
        self.database_status = "ready"
        self.database_path = profile.database_path
        if self.app is not None:
            self.app.state.store = store

    def list_profiles(self) -> list[WorkspaceProfile]:
        return self._require_catalog().list_profiles()

    def get_profile(self, workspace_id: str) -> WorkspaceProfile:
        profile = self._require_catalog().get(workspace_id)
        if profile is None:
            raise WorkspaceNotFoundError(workspace_id)
        return profile

    def create_and_open(self, request: WorkspaceInput) -> WorkspaceProfile:
        with self.lock:
            store = self._open_workspace_database(request.database_path)
            now = utc_now()
            profile = WorkspaceProfile(
                id=f"ws_{uuid4().hex}",
                name=request.name,
                input_folder=request.input_folder,
                output_folder=request.output_folder,
                database_path=request.database_path,
                note=request.note,
                created_at=now,
                updated_at=now,
                last_opened=now,
            )
            created = self._require_catalog().create_and_activate(profile)
            self._swap_store(store, created)
            return created

    def update_and_open(self, workspace_id: str, request: WorkspaceInput) -> WorkspaceProfile:
        with self.lock:
            current = self.get_profile(workspace_id)
            store = self._open_workspace_database(request.database_path)
            now = utc_now()
            profile = WorkspaceProfile(
                id=current.id,
                name=request.name,
                input_folder=request.input_folder,
                output_folder=request.output_folder,
                database_path=request.database_path,
                note=request.note if "note" in request.model_fields_set else current.note,
                created_at=current.created_at,
                updated_at=now,
                last_opened=now,
            )
            updated = self._require_catalog().update_and_activate(profile)
            self._swap_store(store, updated)
            return updated

    def open(self, workspace_id: str) -> WorkspaceProfile:
        with self.lock:
            current = self.get_profile(workspace_id)
            store = self._open_workspace_database(current.database_path)
            opened = self._require_catalog().activate(workspace_id, utc_now())
            self._swap_store(store, opened)
            return opened

    def delete(self, workspace_id: str) -> None:
        with self.lock:
            profile = self.get_profile(workspace_id)
            if self.active_workspace is not None and self.active_workspace.id == profile.id:
                raise WorkspaceActiveError(profile.id)
            self._require_catalog().delete(profile.id)

    def list_payload(self) -> dict:
        try:
            profiles = self.list_profiles()
        except WorkspaceCatalogError as exc:
            self._warn(str(exc))
            profiles = []
        return {
            "workspaces": [profile.model_dump(mode="json") for profile in profiles],
            "active_workspace_id": self.active_workspace.id if self.active_workspace else None,
            "active_workspace": (
                self.active_workspace.model_dump(mode="json") if self.active_workspace else None
            ),
            "warnings": list(self.warnings),
        }

    def active_payload(self) -> dict:
        return {
            "workspace": (
                self.active_workspace.model_dump(mode="json") if self.active_workspace else None
            ),
            "database": {"path": self.database_path, "status": self.database_status},
            "warnings": list(self.warnings),
        }
