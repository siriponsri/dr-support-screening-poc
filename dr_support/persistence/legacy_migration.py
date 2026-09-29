"""Read-only legacy SQLite inventory and PostgreSQL migration service.

The service treats the configured catalog as the only authority. It never
creates, updates, or deletes SQLite files; all PostgreSQL writes for one
import are made in one transaction after a source-set recheck.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Sequence

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from ..contracts import WorkspaceProfile
from ..store import apply_case_defaults
from .cases import _serialized_payload
from .config import PostgresSettings
from .database import PostgresDatabase


ConsistencyKind = Literal["writer_quiesced", "snapshot"]


class LegacyMigrationError(RuntimeError):
    """Base error for a migration that cannot safely continue."""


class MigrationConsistencyError(LegacyMigrationError):
    """The operator did not provide one approved logical source boundary."""


class MigrationNotSafeError(LegacyMigrationError):
    """Inventory or target conflicts make the migration unsafe to write."""


class LegacySourceConflictError(LegacyMigrationError):
    """The source set differs from a planned or previously imported source set."""


SourceSetConflictError = LegacySourceConflictError


@dataclass(frozen=True)
class ConsistencyBoundary:
    """Operator evidence that all legacy writers share one logical source state."""

    kind: ConsistencyKind
    identifier: str

    def __post_init__(self) -> None:
        if self.kind not in ("writer_quiesced", "snapshot"):
            raise ValueError("Consistency kind must be writer_quiesced or snapshot")
        if not isinstance(self.identifier, str) or not self.identifier.strip():
            raise ValueError("Consistency boundary identifier is required")
        object.__setattr__(self, "identifier", self.identifier.strip())

    @classmethod
    def writer_quiesced(cls, identifier: str) -> ConsistencyBoundary:
        return cls("writer_quiesced", identifier)

    @classmethod
    def snapshot(cls, identifier: str) -> ConsistencyBoundary:
        return cls("snapshot", identifier)


@dataclass(frozen=True)
class SQLiteSidecarIdentity:
    """Identity for SQLite state stored beside the main database file."""

    kind: Literal["wal", "shm", "journal"]
    path: str
    status: Literal["readable", "missing", "invalid"]
    size_bytes: int | None = None
    mtime_ns: int | None = None
    sha256: str | None = None
    error: str | None = None

    @property
    def mtime_utc(self) -> str | None:
        if self.mtime_ns is None:
            return None
        return datetime.fromtimestamp(self.mtime_ns / 1_000_000_000, tz=timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.path,
            "status": self.status,
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
            "mtime_utc": self.mtime_utc,
            "sha256": self.sha256,
            "error": self.error,
        }


@dataclass(frozen=True)
class SourceIdentity:
    """Main-file and effective sidecar identity recorded for one SQLite source."""

    role: str
    path: str
    workspace_id: str | None
    status: Literal["readable", "missing", "invalid"]
    size_bytes: int | None = None
    mtime_ns: int | None = None
    sha256: str | None = None
    error: str | None = None
    effective_state: tuple[SQLiteSidecarIdentity, ...] = ()

    @property
    def mtime_utc(self) -> str | None:
        if self.mtime_ns is None:
            return None
        return datetime.fromtimestamp(self.mtime_ns / 1_000_000_000, tz=timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "path": self.path,
            "workspace_id": self.workspace_id,
            "status": self.status,
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
            "mtime_utc": self.mtime_utc,
            "sha256": self.sha256,
            "error": self.error,
            "effective_state": [item.to_dict() for item in self.effective_state],
        }


@dataclass(frozen=True)
class LegacyWorkspace:
    """One catalog entry and its read-only case snapshot."""

    workspace_id: str
    profile: WorkspaceProfile | None
    raw_profile: dict[str, Any]
    database: SourceIdentity
    cases: tuple[tuple[str, dict[str, Any]], ...]


@dataclass(frozen=True)
class LegacyInventory:
    """Complete source inventory used to derive a deterministic source set."""

    catalog: SourceIdentity
    workspaces: tuple[LegacyWorkspace, ...]
    orphan_files: tuple[SourceIdentity, ...]
    conflicts: tuple[str, ...]
    source_set_sha256: str

    @property
    def workspace_count(self) -> int:
        return len(self.workspaces)

    @property
    def referenced_database_count(self) -> int:
        return len(self.workspaces)

    @property
    def readable_database_count(self) -> int:
        return sum(item.database.status == "readable" for item in self.workspaces)

    @property
    def case_count(self) -> int:
        return sum(len(item.cases) for item in self.workspaces)

    @property
    def case_counts(self) -> dict[str, int]:
        return {item.workspace_id: len(item.cases) for item in self.workspaces}

    @property
    def source_files(self) -> tuple[SourceIdentity, ...]:
        return (self.catalog, *(item.database for item in self.workspaces))


@dataclass(frozen=True)
class MigrationReport:
    """Human and machine-readable dry-run result."""

    inventory: LegacyInventory
    boundary: ConsistencyBoundary | None
    target_conflicts: tuple[str, ...] = ()

    @property
    def safe_to_proceed(self) -> bool:
        return bool(
            self.boundary
            and not self.inventory.conflicts
            and not self.target_conflicts
            and self.inventory.catalog.status == "readable"
            and all(item.database.status == "readable" for item in self.inventory.workspaces)
        )

    @property
    def conflicts(self) -> tuple[str, ...]:
        return self.inventory.conflicts + self.target_conflicts

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog": self.inventory.catalog.to_dict(),
            "workspaces_discovered": self.inventory.workspace_count,
            "referenced_databases": self.inventory.referenced_database_count,
            "readable_databases": self.inventory.readable_database_count,
            "case_counts": self.inventory.case_counts,
            "case_count": self.inventory.case_count,
            "source_set_sha256": self.inventory.source_set_sha256,
            "sources": [item.to_dict() for item in self.inventory.source_files],
            "orphans": [item.to_dict() for item in self.inventory.orphan_files],
            "conflicts": list(self.conflicts),
            "workspace_mappings": [
                {"legacy_workspace_id": item.workspace_id, "target_workspace_id": item.workspace_id}
                for item in self.inventory.workspaces
            ],
            "consistency_boundary": (
                {"kind": self.boundary.kind, "identifier": self.boundary.identifier}
                if self.boundary
                else None
            ),
            "safe_to_proceed": self.safe_to_proceed,
        }

    def render(self) -> str:
        """Render an operator report without exposing database credentials."""

        lines = [
            "Legacy SQLite migration dry run",
            f"Authoritative catalog: {self.inventory.catalog.path}",
            f"Catalog status: {self._format_source(self.inventory.catalog)}",
            (
                "Consistency boundary: "
                + (
                    f"{self.boundary.kind} ({self.boundary.identifier})"
                    if self.boundary
                    else "NOT PROVIDED"
                )
            ),
            f"Workspaces discovered: {self.inventory.workspace_count}",
            f"Referenced workspace databases: {self.inventory.referenced_database_count}",
            f"Readable workspace databases: {self.inventory.readable_database_count}",
            f"Cases discovered: {self.inventory.case_count}",
            "Workspace mappings:",
        ]
        for item in self.inventory.workspaces:
            lines.append(
                f"  {item.workspace_id} -> {item.workspace_id}; "
                f"cases={len(item.cases)}; database={self._format_source(item.database)}"
            )
        lines.append("Orphan SQLite files (not selected):")
        if self.inventory.orphan_files:
            lines.extend(f"  {self._format_source(item)}" for item in self.inventory.orphan_files)
        else:
            lines.append("  none")
        lines.append("Conflicts:")
        if self.conflicts:
            lines.extend(f"  - {item}" for item in self.conflicts)
        else:
            lines.append("  none")
        lines.append(f"Source-set SHA-256: {self.inventory.source_set_sha256}")
        lines.append(f"Safe to proceed: {'YES' if self.safe_to_proceed else 'NO'}")
        return "\n".join(lines)

    @staticmethod
    def _format_source(source: SourceIdentity) -> str:
        details = [f"status={source.status}", f"size={source.size_bytes}", f"mtime={source.mtime_utc}"]
        if source.sha256:
            details.append(f"sha256={source.sha256}")
        sidecars = [
            f"{item.kind}:{item.status}"
            + (f":{item.sha256}" if item.sha256 else "")
            for item in source.effective_state
            if item.status != "missing"
        ]
        if sidecars:
            details.append("effective_sidecars=" + ",".join(sidecars))
        if source.error:
            details.append(f"detail={source.error}")
        return f"{source.path} ({', '.join(details)})"

    def __str__(self) -> str:
        return self.render()


@dataclass(frozen=True)
class MigrationPlan:
    report: MigrationReport

    @property
    def inventory(self) -> LegacyInventory:
        return self.report.inventory


@dataclass(frozen=True)
class MigrationResult:
    source_set_sha256: str
    workspace_count: int
    case_count: int
    imported_workspaces: int
    unchanged_workspaces: int
    imported_cases: int
    unchanged_cases: int
    idempotent: bool
    receipt_recorded: bool


class LegacySQLiteMigrationService:
    """Inventory and import catalog-referenced SQLite state into PostgreSQL."""

    _RECEIPTS_TABLE = "legacy_migration_receipts"
    _SQLITE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}

    def __init__(
        self,
        database: PostgresDatabase,
        catalog_path: str | Path,
        *,
        orphan_roots: Sequence[str | Path] = (),
    ) -> None:
        self.database = database
        self.catalog_path = _normalized_path(Path(catalog_path).expanduser())
        self.orphan_roots = tuple(
            _normalized_path(Path(root).expanduser()) for root in orphan_roots
        )
        self._schema = sql.Identifier(database.settings.schema)

    def inventory(self) -> LegacyInventory:
        """Read the catalog and all referenced databases without writing either store."""

        conflicts: list[str] = []
        catalog, rows = self._read_catalog(conflicts)
        workspaces: list[LegacyWorkspace] = []
        seen_ids: set[str] = set()
        path_owners: dict[str, list[str]] = {}

        for raw_profile in rows:
            workspace_id = str(raw_profile.get("id") or "").strip()
            if not workspace_id:
                conflicts.append("Catalog contains a workspace with an empty id")
                workspace_id = f"<invalid-{len(workspaces) + 1}>"
            if workspace_id in seen_ids:
                conflicts.append(f"Catalog contains duplicate workspace id {workspace_id!r}")
            seen_ids.add(workspace_id)

            profile: WorkspaceProfile | None
            try:
                profile = WorkspaceProfile.model_validate(raw_profile)
            except ValueError as exc:
                profile = None
                conflicts.append(f"Workspace {workspace_id!r} has invalid profile fields: {exc}")

            raw_path = raw_profile.get("database_path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                source_path = _normalized_path(Path(raw_path or f"<missing-{workspace_id}>") )
                database = SourceIdentity(
                    role="workspace_database",
                    path=str(source_path),
                    workspace_id=workspace_id,
                    status="invalid",
                    error="Catalog database_path is missing",
                )
                cases: tuple[tuple[str, dict[str, Any]], ...] = ()
            else:
                source_path = _normalized_path(Path(raw_path).expanduser())
                path_key = _path_comparison_key(source_path)
                path_owners.setdefault(path_key, []).append(workspace_id)
                database, cases = self._read_case_database(source_path, workspace_id, conflicts)

            workspaces.append(
                LegacyWorkspace(
                    workspace_id=workspace_id,
                    profile=profile,
                    raw_profile=raw_profile,
                    database=database,
                    cases=cases,
                )
            )

        for path, owners in path_owners.items():
            if len(owners) > 1:
                conflicts.append(
                    f"Catalog database path {path!r} is referenced by multiple workspaces: "
                    + ", ".join(sorted(owners))
                )

        referenced_paths = {_path_comparison_key(Path(item.database.path)) for item in workspaces}
        orphan_files = self._find_orphans(
            referenced_paths, _path_comparison_key(Path(catalog.path)), conflicts
        )
        source_set_sha256 = _source_set_hash(catalog, workspaces)
        return LegacyInventory(
            catalog=catalog,
            workspaces=tuple(workspaces),
            orphan_files=tuple(orphan_files),
            conflicts=tuple(dict.fromkeys(conflicts)),
            source_set_sha256=source_set_sha256,
        )

    def dry_run(self, boundary: ConsistencyBoundary | None = None) -> MigrationReport:
        """Build a report; this method performs no PostgreSQL application-data writes."""

        inventory = self.inventory()
        target_conflicts = self._target_conflicts(inventory)
        return MigrationReport(inventory, boundary, target_conflicts)

    def plan(self, boundary: ConsistencyBoundary | None = None) -> MigrationPlan:
        return MigrationPlan(self.dry_run(boundary))

    def import_legacy(
        self,
        boundary: ConsistencyBoundary | None = None,
        *,
        plan: MigrationPlan | None = None,
        expected_source_set_sha256: str | None = None,
    ) -> MigrationResult:
        """Import one approved source set atomically into the explicit target database."""

        expected_source_set_sha256 = _normalize_expected_source_set_sha256(
            expected_source_set_sha256
        )
        if plan is None:
            if expected_source_set_sha256 is None:
                raise MigrationConsistencyError(
                    "Fresh import requires the reviewed source-set SHA-256"
                )
            plan = self.plan(boundary)
        elif boundary is not None and plan.report.boundary != boundary:
            raise MigrationConsistencyError("Import boundary differs from the planned boundary")
        boundary = plan.report.boundary
        if (
            expected_source_set_sha256 is not None
            and expected_source_set_sha256 != plan.inventory.source_set_sha256
        ):
            raise LegacySourceConflictError(
                "Expected source-set SHA-256 does not match the reviewed dry run"
            )
        if boundary is None:
            raise MigrationConsistencyError(
                "Import requires a writer-quiesced or approved snapshot boundary"
            )
        if not plan.report.safe_to_proceed:
            if any("source set" in conflict for conflict in plan.report.conflicts):
                raise LegacySourceConflictError("Legacy source set conflicts with PostgreSQL state")
            raise MigrationNotSafeError("Migration dry run is not safe to proceed")

        verified = self.inventory()
        if verified.source_set_sha256 != plan.inventory.source_set_sha256:
            raise LegacySourceConflictError(
                "Legacy source set changed after dry run; no PostgreSQL data was written"
            )
        if verified.conflicts:
            raise LegacySourceConflictError(
                "Legacy source set became ambiguous or invalid; no PostgreSQL data was written"
            )

        with self.database.transaction() as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"{self.database.settings.schema}.legacy_migration_receipts",),
            )
            receipt_rows = connection.execute(
                sql.SQL(
                    "SELECT source_set_sha256 FROM {}.{} "
                    "WHERE catalog_path = %s ORDER BY imported_at"
                ).format(self._schema, sql.Identifier(self._RECEIPTS_TABLE)),
                (str(verified.catalog.path),),
            ).fetchall()
            prior_source_sets = {row[0] for row in receipt_rows}
            divergent = prior_source_sets - {verified.source_set_sha256}
            if divergent:
                raise LegacySourceConflictError(
                    "Legacy catalog has already been imported from a different source set"
                )

            if verified.source_set_sha256 in prior_source_sets:
                self._assert_target_matches(connection, verified)
                return MigrationResult(
                    source_set_sha256=verified.source_set_sha256,
                    workspace_count=verified.workspace_count,
                    case_count=verified.case_count,
                    imported_workspaces=0,
                    unchanged_workspaces=verified.workspace_count,
                    imported_cases=0,
                    unchanged_cases=verified.case_count,
                    idempotent=True,
                    receipt_recorded=False,
                )

            self._assert_target_matches(connection, verified, allow_missing=True)
            imported_workspaces, unchanged_workspaces = self._write_workspaces(
                connection, verified
            )
            imported_cases, unchanged_cases = self._write_cases(connection, verified)
            self._assert_target_matches(connection, verified)

            final_inventory = self.inventory()
            if final_inventory.source_set_sha256 != verified.source_set_sha256:
                raise LegacySourceConflictError(
                    "Legacy source set changed during import; PostgreSQL transaction rolled back"
                )
            connection.execute(
                sql.SQL(
                    "INSERT INTO {}.{} ("
                    "source_set_sha256, catalog_path, catalog_sha256, consistency_kind, "
                    "consistency_id, source_files, workspace_mappings, workspace_count, case_count"
                    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                ).format(self._schema, sql.Identifier(self._RECEIPTS_TABLE)),
                (
                    verified.source_set_sha256,
                    str(verified.catalog.path),
                    verified.catalog.sha256,
                    boundary.kind,
                    boundary.identifier,
                    Jsonb([item.to_dict() for item in verified.source_files]),
                    Jsonb(
                        [
                            {
                                "legacy_workspace_id": item.workspace_id,
                                "target_workspace_id": item.workspace_id,
                                "database_path": item.database.path,
                            }
                            for item in verified.workspaces
                        ]
                    ),
                    verified.workspace_count,
                    verified.case_count,
                ),
            )

        return MigrationResult(
            source_set_sha256=verified.source_set_sha256,
            workspace_count=verified.workspace_count,
            case_count=verified.case_count,
            imported_workspaces=imported_workspaces,
            unchanged_workspaces=unchanged_workspaces,
            imported_cases=imported_cases,
            unchanged_cases=unchanged_cases,
            idempotent=False,
            receipt_recorded=True,
        )

    def run_import(
        self,
        boundary: ConsistencyBoundary | None = None,
        *,
        plan: MigrationPlan | None = None,
        expected_source_set_sha256: str | None = None,
    ) -> MigrationResult:
        """Explicitly named alias for callers that avoid a method named ``import``."""

        return self.import_legacy(
            boundary,
            plan=plan,
            expected_source_set_sha256=expected_source_set_sha256,
        )

    def _read_catalog(
        self, conflicts: list[str]
    ) -> tuple[SourceIdentity, list[dict[str, Any]]]:
        before = _capture_source(self.catalog_path, "catalog", None)
        if before.status != "readable":
            conflicts.append(f"Authoritative catalog is {before.status}: {before.path}")
            return before, []
        rows: list[dict[str, Any]] = []
        connection = None
        try:
            connection = _open_read_only(before.path)
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(workspaces)").fetchall()
            }
            required = {
                "id",
                "name",
                "input_folder",
                "output_folder",
                "database_path",
                "note",
                "created_at",
                "updated_at",
                "last_opened",
            }
            if not required.issubset(columns):
                missing = ", ".join(sorted(required - columns))
                raise ValueError(f"catalog workspaces table is missing columns: {missing}")
            values = connection.execute(
                "SELECT id, name, input_folder, output_folder, database_path, note, "
                "created_at, updated_at, last_opened FROM workspaces ORDER BY id"
            ).fetchall()
            for value in values:
                rows.append(
                    {
                        "id": value[0],
                        "name": value[1],
                        "input_folder": value[2],
                        "output_folder": value[3],
                        "database_path": value[4],
                        "note": value[5],
                        "created_at": value[6],
                        "updated_at": value[7],
                        "last_opened": value[8],
                    }
                )
        except (sqlite3.Error, OSError, ValueError) as exc:
            conflicts.append(f"Authoritative catalog is invalid: {exc}")
            return SourceIdentity(
                role="catalog",
                path=before.path,
                workspace_id=None,
                status="invalid",
                size_bytes=before.size_bytes,
                mtime_ns=before.mtime_ns,
                sha256=before.sha256,
                error=str(exc),
            ), []
        finally:
            if connection is not None:
                connection.close()
        after = _capture_source(self.catalog_path, "catalog", None)
        if not _same_identity(before, after):
            conflicts.append("Authoritative catalog changed during inventory")
            return SourceIdentity(
                **{**after.__dict__, "status": "invalid", "error": "changed during inventory"}
            ), []
        return before, rows

    def _read_case_database(
        self,
        path: Path,
        workspace_id: str,
        conflicts: list[str],
    ) -> tuple[SourceIdentity, tuple[tuple[str, dict[str, Any]], ...]]:
        before = _capture_source(path, "workspace_database", workspace_id)
        if before.status != "readable":
            conflicts.append(f"Workspace {workspace_id!r} database is {before.status}: {before.path}")
            return before, ()
        connection = None
        try:
            connection = _open_read_only(path)
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(cases)").fetchall()
            }
            if not {"id", "data"}.issubset(columns):
                raise ValueError("cases table is missing id or data columns")
            rows = connection.execute("SELECT id, data FROM cases ORDER BY id").fetchall()
            cases: list[tuple[str, dict[str, Any]]] = []
            seen: set[str] = set()
            for raw_id, raw_data in rows:
                case_id = str(raw_id or "").strip()
                if not case_id:
                    raise ValueError("cases table contains an empty case id")
                if case_id in seen:
                    raise ValueError(f"cases table contains duplicate case id {case_id!r}")
                seen.add(case_id)
                try:
                    case = json.loads(raw_data)
                except (TypeError, json.JSONDecodeError) as exc:
                    raise ValueError(f"case {case_id!r} is not valid JSON") from exc
                if not isinstance(case, dict):
                    raise ValueError(f"case {case_id!r} is not a JSON object")
                if case.get("image_id") not in (None, case_id):
                    raise ValueError(f"case {case_id!r} has a mismatched image_id")
                normalized = apply_case_defaults(dict(case))
                normalized["image_id"] = case_id
                revision = normalized.get("revision")
                if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
                    raise ValueError(f"case {case_id!r} has an invalid revision")
                # Validate that the payload can be serialized deterministically before writing.
                _serialized_payload(normalized)
                cases.append((case_id, normalized))
        except (sqlite3.Error, OSError, ValueError) as exc:
            conflicts.append(f"Workspace {workspace_id!r} database is invalid: {exc}")
            return SourceIdentity(
                role="workspace_database",
                path=before.path,
                workspace_id=workspace_id,
                status="invalid",
                size_bytes=before.size_bytes,
                mtime_ns=before.mtime_ns,
                sha256=before.sha256,
                error=str(exc),
            ), ()
        finally:
            if connection is not None:
                connection.close()
        after = _capture_source(path, "workspace_database", workspace_id)
        if not _same_identity(before, after):
            conflicts.append(f"Workspace {workspace_id!r} database changed during inventory")
            return SourceIdentity(
                **{**after.__dict__, "status": "invalid", "error": "changed during inventory"}
            ), ()
        return before, tuple(cases)

    def _find_orphans(
        self,
        referenced_paths: set[str],
        catalog_path: str,
        conflicts: list[str],
    ) -> list[SourceIdentity]:
        found: dict[str, SourceIdentity] = {}
        for root in self.orphan_roots:
            if not root.exists():
                conflicts.append(f"Configured orphan search location is missing: {root}")
                continue
            if not root.is_dir():
                conflicts.append(f"Configured orphan search location is not a directory: {root}")
                continue
            try:
                candidates = sorted(
                    item
                    for item in root.rglob("*")
                    if item.is_file() and item.suffix.lower() in self._SQLITE_SUFFIXES
                )
            except OSError as exc:
                conflicts.append(f"Could not inspect orphan search location {root}: {exc}")
                continue
            for candidate in candidates:
                normalized = _normalized_path(candidate)
                key = _path_comparison_key(normalized)
                if key in referenced_paths or key == catalog_path:
                    continue
                found[key] = _capture_source(normalized, "orphan", None)
        return [found[key] for key in sorted(found)]

    def _target_conflicts(self, inventory: LegacyInventory) -> tuple[str, ...]:
        if inventory.conflicts or inventory.catalog.status != "readable":
            return ()
        try:
            with self.database.session() as connection:
                return tuple(self._collect_target_conflicts(connection, inventory, allow_missing=True))
        except psycopg.Error as exc:
            return (f"PostgreSQL target could not be inspected: {type(exc).__name__}",)

    def _assert_target_matches(
        self,
        connection: Any,
        inventory: LegacyInventory,
        *,
        allow_missing: bool = False,
    ) -> None:
        conflicts = self._collect_target_conflicts(connection, inventory, allow_missing=allow_missing)
        if conflicts:
            raise LegacySourceConflictError("; ".join(conflicts))

    def _collect_target_conflicts(
        self,
        connection: Any,
        inventory: LegacyInventory,
        *,
        allow_missing: bool,
    ) -> list[str]:
        conflicts: list[str] = []
        receipt_table = sql.Identifier(self._RECEIPTS_TABLE)
        prior = connection.execute(
            sql.SQL(
                "SELECT source_set_sha256 FROM {}.{} WHERE catalog_path = %s"
            ).format(self._schema, receipt_table),
            (str(inventory.catalog.path),),
        ).fetchall()
        prior_source_sets = {row[0] for row in prior}
        if prior_source_sets and prior_source_sets != {inventory.source_set_sha256}:
            conflicts.append("PostgreSQL already contains a different source set receipt")

        for item in inventory.workspaces:
            if item.profile is None:
                continue
            row = connection.execute(
                sql.SQL(
                    "SELECT name, input_folder, output_folder, database_path, note, "
                    "created_at, updated_at, last_opened, archived_at "
                    "FROM {}.workspaces WHERE workspace_id = %s"
                ).format(self._schema),
                (item.workspace_id,),
            ).fetchone()
            if row is None:
                if not allow_missing:
                    conflicts.append(f"Workspace {item.workspace_id!r} is missing from PostgreSQL")
                continue
            if row[8] is not None:
                conflicts.append(f"Workspace {item.workspace_id!r} is archived in PostgreSQL")
                continue
            if not _workspace_row_matches(row, item.profile):
                if not _workspace_row_is_identity_only(row):
                    conflicts.append(f"Workspace {item.workspace_id!r} differs in PostgreSQL")

            source_case_ids = {case_id for case_id, _ in item.cases}
            target_case_rows = connection.execute(
                sql.SQL(
                    "SELECT case_id FROM {}.review_cases WHERE workspace_id = %s "
                    "ORDER BY case_id"
                ).format(self._schema),
                (item.workspace_id,),
            ).fetchall()
            target_case_ids = {row[0] for row in target_case_rows}
            extra_case_ids = sorted(target_case_ids - source_case_ids)
            if extra_case_ids:
                conflicts.append(
                    f"Workspace {item.workspace_id!r} has extra PostgreSQL cases: "
                    + ", ".join(repr(case_id) for case_id in extra_case_ids)
                )
            if not allow_missing and len(target_case_rows) != len(source_case_ids):
                conflicts.append(
                    f"Workspace {item.workspace_id!r} target case count "
                    f"{len(target_case_rows)} does not match source count "
                    f"{len(source_case_ids)}"
                )

            for case_id, case in item.cases:
                target = connection.execute(
                    sql.SQL(
                        "SELECT revision, payload FROM {}.review_cases "
                        "WHERE workspace_id = %s AND case_id = %s"
                    ).format(self._schema),
                    (item.workspace_id, case_id),
                ).fetchone()
                if target is None:
                    if not allow_missing:
                        conflicts.append(
                            f"Case {case_id!r} in workspace {item.workspace_id!r} is missing from PostgreSQL"
                        )
                    continue
                if not _case_row_matches(target, case):
                    conflicts.append(
                        f"Case {case_id!r} in workspace {item.workspace_id!r} differs in PostgreSQL"
                    )
        return conflicts

    def _write_workspaces(self, connection: Any, inventory: LegacyInventory) -> tuple[int, int]:
        imported = 0
        unchanged = 0
        for item in inventory.workspaces:
            if item.profile is None:
                raise MigrationNotSafeError(f"Workspace {item.workspace_id!r} has no valid profile")
            profile = item.profile
            row = connection.execute(
                sql.SQL("SELECT name, input_folder, output_folder, database_path, note, "
                        "created_at, updated_at, last_opened, archived_at "
                        "FROM {}.workspaces WHERE workspace_id = %s").format(self._schema),
                (item.workspace_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    sql.SQL(
                        "INSERT INTO {}.workspaces "
                        "(workspace_id, name, input_folder, output_folder, database_path, note, "
                        "created_at, updated_at, last_opened) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    ).format(self._schema),
                    _profile_values(item.workspace_id, profile),
                )
                imported += 1
            elif _workspace_row_is_identity_only(row):
                connection.execute(
                    sql.SQL(
                        "UPDATE {}.workspaces SET name = %s, input_folder = %s, "
                        "output_folder = %s, database_path = %s, note = %s, "
                        "created_at = %s, updated_at = %s, last_opened = %s "
                        "WHERE workspace_id = %s"
                    ).format(self._schema),
                    _profile_values(item.workspace_id, profile)[1:]
                    + (item.workspace_id,),
                )
                imported += 1
            else:
                unchanged += 1
        return imported, unchanged

    def _write_cases(self, connection: Any, inventory: LegacyInventory) -> tuple[int, int]:
        imported = 0
        unchanged = 0
        for item in inventory.workspaces:
            for case_id, case in item.cases:
                row = connection.execute(
                    sql.SQL(
                        "SELECT revision, payload FROM {}.review_cases "
                        "WHERE workspace_id = %s AND case_id = %s"
                    ).format(self._schema),
                    (item.workspace_id, case_id),
                ).fetchone()
                if row is None:
                    connection.execute(
                        sql.SQL(
                            "INSERT INTO {}.review_cases "
                            "(workspace_id, case_id, revision, payload) VALUES (%s, %s, %s, %s)"
                        ).format(self._schema),
                        (
                            item.workspace_id,
                            case_id,
                            case["revision"],
                            Jsonb(json.loads(_serialized_payload(case))),
                        ),
                    )
                    imported += 1
                else:
                    unchanged += 1
        return imported, unchanged


def _normalized_path(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = Path(os.path.abspath(path))
    return resolved


def _path_comparison_key(path: Path) -> str:
    """Return a stable case-insensitive key without changing display spelling."""

    return os.path.normcase(str(path))


def _open_read_only(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{Path(path).as_uri()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capture_sqlite_sidecar(
    path: Path, kind: Literal["wal", "shm", "journal"]
) -> SQLiteSidecarIdentity:
    sidecar_path = Path(f"{path}-{kind}")
    try:
        stat = sidecar_path.stat()
    except FileNotFoundError:
        return SQLiteSidecarIdentity(kind, str(sidecar_path), "missing")
    except OSError as exc:
        return SQLiteSidecarIdentity(kind, str(sidecar_path), "invalid", error=str(exc))
    if not sidecar_path.is_file():
        return SQLiteSidecarIdentity(
            kind,
            str(sidecar_path),
            "invalid",
            stat.st_size,
            stat.st_mtime_ns,
            error="path is not a regular file",
        )
    try:
        digest = _sha256(sidecar_path)
    except OSError as exc:
        return SQLiteSidecarIdentity(
            kind,
            str(sidecar_path),
            "invalid",
            stat.st_size,
            stat.st_mtime_ns,
            error=str(exc),
        )
    return SQLiteSidecarIdentity(
        kind,
        str(sidecar_path),
        "readable",
        stat.st_size,
        stat.st_mtime_ns,
        digest,
    )


def _capture_sqlite_effective_state(path: Path) -> tuple[SQLiteSidecarIdentity, ...]:
    return tuple(
        _capture_sqlite_sidecar(path, kind) for kind in ("wal", "shm", "journal")
    )


def _capture_source(path: Path, role: str, workspace_id: str | None) -> SourceIdentity:
    normalized = _normalized_path(path)
    effective_state = _capture_sqlite_effective_state(normalized)
    sidecar_errors = [item.error for item in effective_state if item.status == "invalid"]
    rollback_journal = next(
        (item for item in effective_state if item.kind == "journal" and item.status == "readable"),
        None,
    )
    sidecar_error = next((error for error in sidecar_errors if error), None)
    if rollback_journal is not None:
        sidecar_error = "SQLite rollback journal is present; source state is not stable"
    try:
        stat = normalized.stat()
    except FileNotFoundError:
        return SourceIdentity(
            role,
            str(normalized),
            workspace_id,
            "missing",
            effective_state=effective_state,
            error=sidecar_error,
        )
    except OSError as exc:
        return SourceIdentity(
            role,
            str(normalized),
            workspace_id,
            "invalid",
            effective_state=effective_state,
            error=str(exc),
        )
    if not normalized.is_file():
        return SourceIdentity(
            role,
            str(normalized),
            workspace_id,
            "invalid",
            stat.st_size,
            stat.st_mtime_ns,
            error="path is not a regular file",
            effective_state=effective_state,
        )
    try:
        digest = _sha256(normalized)
    except OSError as exc:
        return SourceIdentity(
            role,
            str(normalized),
            workspace_id,
            "invalid",
            stat.st_size,
            stat.st_mtime_ns,
            error=str(exc),
            effective_state=effective_state,
        )
    return SourceIdentity(
        role,
        str(normalized),
        workspace_id,
        "invalid" if sidecar_error else "readable",
        stat.st_size,
        stat.st_mtime_ns,
        digest,
        sidecar_error,
        effective_state,
    )


def _same_identity(left: SourceIdentity, right: SourceIdentity) -> bool:
    return (
        _path_comparison_key(Path(left.path)) == _path_comparison_key(Path(right.path))
        and left.status == right.status
        and left.size_bytes == right.size_bytes
        and left.mtime_ns == right.mtime_ns
        and left.sha256 == right.sha256
        and left.effective_state == right.effective_state
    )


def _normalize_expected_source_set_sha256(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise MigrationConsistencyError("Expected source-set SHA-256 must be 64 hexadecimal characters")
    return normalized


def _source_set_hash(catalog: SourceIdentity, workspaces: Sequence[LegacyWorkspace]) -> str:
    payload = {
        "catalog": catalog.to_dict(),
        "workspaces": [
            {
                "workspace_id": item.workspace_id,
                "profile": item.raw_profile,
                "database": item.database.to_dict(),
            }
            for item in workspaces
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_timestamp(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _profile_values(workspace_id: str, profile: WorkspaceProfile) -> tuple[Any, ...]:
    return (
        workspace_id,
        profile.name,
        profile.input_folder,
        profile.output_folder,
        profile.database_path,
        profile.note,
        profile.created_at,
        profile.updated_at,
        profile.last_opened,
    )


def _workspace_row_is_identity_only(row: Sequence[Any]) -> bool:
    return row[0] is None and row[1] is None and row[2] is None and row[3] is None and row[4] is None


def _workspace_row_matches(row: Sequence[Any], profile: WorkspaceProfile) -> bool:
    expected = (
        profile.name,
        profile.input_folder,
        profile.output_folder,
        profile.database_path,
        profile.note,
        _canonical_timestamp(profile.created_at),
        _canonical_timestamp(profile.updated_at),
        _canonical_timestamp(profile.last_opened),
    )
    actual = (
        row[0],
        row[1],
        row[2],
        row[3],
        row[4],
        _canonical_timestamp(row[5]),
        _canonical_timestamp(row[6]),
        _canonical_timestamp(row[7]),
    )
    return actual == expected and row[8] is None


def _case_row_matches(row: Sequence[Any], case: dict[str, Any]) -> bool:
    existing = apply_case_defaults(dict(row[1]))
    existing["image_id"] = case["image_id"]
    existing["revision"] = row[0]
    return row[0] == case["revision"] and _serialized_payload(existing) == _serialized_payload(case)


def _build_boundary(args: argparse.Namespace) -> ConsistencyBoundary | None:
    if args.writer_quiesced and args.snapshot_id:
        raise ValueError("Choose either --writer-quiesced or --snapshot-id")
    if args.writer_quiesced:
        return ConsistencyBoundary.writer_quiesced(args.writer_quiesced)
    if args.snapshot_id:
        return ConsistencyBoundary.snapshot(args.snapshot_id)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("dry-run", "import"))
    parser.add_argument("--catalog", required=True, help="Explicit authoritative legacy catalog path")
    parser.add_argument(
        "--orphan-root", action="append", default=[], help="Configured runtime location to inventory"
    )
    parser.add_argument("--writer-quiesced", help="Approved writer-quiescence window identity")
    parser.add_argument("--snapshot-id", help="Approved consistent snapshot identity")
    parser.add_argument(
        "--expected-source-set-sha256",
        help="Exact SHA-256 copied from the reviewed dry-run report (required for import)",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "import" and not args.expected_source_set_sha256:
            raise MigrationConsistencyError(
                "Fresh CLI import requires --expected-source-set-sha256 copied from the reviewed dry run"
            )
        boundary = _build_boundary(args)
        settings = PostgresSettings.from_env()
        database = PostgresDatabase(settings)
        service = LegacySQLiteMigrationService(
            database, args.catalog, orphan_roots=args.orphan_root
        )
        plan = service.plan(boundary)
        print(plan.report.render())
        if not plan.report.safe_to_proceed:
            return 2
        if args.command == "import":
            result = service.import_legacy(
                boundary,
                plan=plan,
                expected_source_set_sha256=args.expected_source_set_sha256,
            )
            print(
                "Import result: "
                f"workspaces imported={result.imported_workspaces}, "
                f"cases imported={result.imported_cases}, "
                f"idempotent={result.idempotent}"
            )
        return 0
    except (LegacyMigrationError, ValueError, psycopg.Error) as exc:
        print(f"Migration stopped safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
