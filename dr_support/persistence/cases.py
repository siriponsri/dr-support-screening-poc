"""Workspace-scoped PostgreSQL persistence for review case documents."""

from __future__ import annotations

import json
import hashlib
import sqlite3
from dataclasses import dataclass
from threading import RLock
from typing import Any
from pathlib import Path

from psycopg import sql
from psycopg.types.json import Jsonb

from ..store import apply_case_defaults, new_case
from .database import PostgresDatabase


class CaseConflictError(RuntimeError):
    """A case update was based on a revision that is no longer current."""


class CaseImportConflictError(RuntimeError):
    """A legacy case differs from an already imported PostgreSQL case."""


class CaseImportError(RuntimeError):
    """A legacy case source cannot be imported safely."""


@dataclass(frozen=True)
class CaseImportResult:
    """Non-sensitive summary of one legacy case-source inspection/import."""

    source_sha256: str
    discovered_cases: int
    imported_cases: int
    unchanged_cases: int
    dry_run: bool


def _serialized_payload(case: dict[str, Any]) -> str:
    return json.dumps(case, allow_nan=False, sort_keys=True, separators=(",", ":"))


class PostgresCaseStore:
    """Store the legacy case JSON contract in workspace-scoped JSONB rows."""

    def __init__(self, database: PostgresDatabase, workspace_id: str) -> None:
        workspace_id = workspace_id.strip()
        if not workspace_id:
            raise ValueError("workspace_id is required for PostgreSQL case storage")
        self.database = database
        self.workspace_id = workspace_id
        self.lock = RLock()
        # Same-revision automatic enrichment needs the payload observed by get().
        # Revision-changing writes use the database revision predicate directly.
        self._observed: dict[str, str | None] = {}
        self._schema = sql.Identifier(database.settings.schema)

    def ensure_workspace(self) -> None:
        """Create the identity row needed by the case foreign key if absent."""
        with self.database.transaction() as connection:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {}.workspaces (workspace_id) VALUES (%s) "
                    "ON CONFLICT (workspace_id) DO NOTHING"
                ).format(self._schema),
                (self.workspace_id,),
            )

    def get(self, image_id: str) -> dict[str, Any]:
        with self.lock:
            with self.database.session() as connection:
                row = connection.execute(
                    sql.SQL(
                        "SELECT revision, payload FROM {}.review_cases "
                        "WHERE workspace_id = %s AND case_id = %s"
                    ).format(self._schema),
                    (self.workspace_id, image_id),
                ).fetchone()
            if row is None:
                self._observed[image_id] = None
                return new_case(image_id)
            stored_revision, raw_case = row
            case = apply_case_defaults(dict(raw_case))
            case["image_id"] = image_id
            case["revision"] = stored_revision
            self._observed[image_id] = _serialized_payload(dict(raw_case))
            return case

    def all_cases(self) -> list[dict[str, Any]]:
        """Return only cases owned by this store's explicit workspace."""
        with self.lock:
            with self.database.session() as connection:
                rows = connection.execute(
                    sql.SQL(
                        "SELECT case_id, revision, payload FROM {}.review_cases "
                        "WHERE workspace_id = %s ORDER BY case_id"
                    ).format(self._schema),
                    (self.workspace_id,),
                ).fetchall()
            cases = []
            for case_id, stored_revision, raw_case in rows:
                case = apply_case_defaults(dict(raw_case))
                case["image_id"] = case_id
                case["revision"] = stored_revision
                self._observed[case_id] = _serialized_payload(dict(raw_case))
                cases.append(case)
            return cases

    def import_sqlite_cases(
        self,
        source_path: str | Path,
        *,
        dry_run: bool = False,
    ) -> CaseImportResult:
        """Inspect or import one catalog-referenced legacy SQLite case store.

        The source is opened through SQLite's read-only URI mode and is hashed
        before and after inspection. All target writes are planned before one
        transaction, so a conflict cannot leave a partial import.
        """
        path = Path(source_path).expanduser().resolve()
        if not path.is_file():
            raise CaseImportError("Legacy case source does not exist")
        source_sha256 = _sha256_file(path)
        source_cases = _read_sqlite_cases(path)
        if _sha256_file(path) != source_sha256:
            raise CaseImportError("Legacy case source changed during inspection")

        plan: list[tuple[str, int, dict[str, Any]]] = []
        unchanged = 0
        with self.database.session() as connection:
            for case_id, case in source_cases:
                normalized = apply_case_defaults(dict(case))
                normalized["image_id"] = case_id
                revision = normalized.get("revision")
                if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
                    raise CaseImportError(f"Legacy case {case_id!r} has an invalid revision")
                payload = _serialized_payload(normalized)
                existing = connection.execute(
                    sql.SQL(
                        "SELECT revision, payload FROM {}.review_cases "
                        "WHERE workspace_id = %s AND case_id = %s"
                    ).format(self._schema),
                    (self.workspace_id, case_id),
                ).fetchone()
                if existing is None:
                    plan.append((case_id, revision, normalized))
                    continue
                existing_revision, existing_payload = existing
                existing_normalized = apply_case_defaults(dict(existing_payload))
                existing_normalized["image_id"] = case_id
                if existing_revision == revision and _serialized_payload(existing_normalized) == payload:
                    unchanged += 1
                    continue
                raise CaseImportConflictError(
                    f"Legacy case {case_id!r} conflicts with PostgreSQL state"
                )

        if not dry_run and plan:
            with self.database.transaction() as connection:
                if _sha256_file(path) != source_sha256:
                    raise CaseImportError("Legacy case source changed during import")
                connection.execute(
                    sql.SQL(
                        "INSERT INTO {}.workspaces (workspace_id) VALUES (%s) "
                        "ON CONFLICT (workspace_id) DO NOTHING"
                    ).format(self._schema),
                    (self.workspace_id,),
                )
                for case_id, revision, case in plan:
                    connection.execute(
                        sql.SQL(
                            "INSERT INTO {}.review_cases "
                            "(workspace_id, case_id, revision, payload) "
                            "VALUES (%s, %s, %s, %s)"
                        ).format(self._schema),
                        (
                            self.workspace_id,
                            case_id,
                            revision,
                            Jsonb(json.loads(_serialized_payload(case))),
                        ),
                    )
                if _sha256_file(path) != source_sha256:
                    raise CaseImportError("Legacy case source changed during import")
        return CaseImportResult(
            source_sha256=source_sha256,
            discovered_cases=len(source_cases),
            imported_cases=0 if dry_run else len(plan),
            unchanged_cases=unchanged,
            dry_run=dry_run,
        )

    def put(self, case: dict[str, Any]) -> None:
        """Persist a case with an atomic revision check across connections."""
        image_id = str(case.get("image_id") or "").strip()
        if not image_id:
            raise ValueError("Case image_id is required")
        normalized = apply_case_defaults(dict(case))
        normalized["image_id"] = image_id
        revision = normalized.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValueError("Case revision must be a non-negative integer")
        payload_text = _serialized_payload(normalized)
        payload = Jsonb(json.loads(payload_text))

        with self.lock:
            observed = self._observed.get(image_id, None)
            with self.database.transaction() as connection:
                connection.execute(
                    sql.SQL(
                        "INSERT INTO {}.workspaces (workspace_id) VALUES (%s) "
                        "ON CONFLICT (workspace_id) DO NOTHING"
                    ).format(self._schema),
                    (self.workspace_id,),
                )
                if revision == 0:
                    inserted = connection.execute(
                        sql.SQL(
                            "INSERT INTO {}.review_cases "
                            "(workspace_id, case_id, revision, payload) "
                            "VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT (workspace_id, case_id) DO NOTHING"
                        ).format(self._schema),
                        (self.workspace_id, image_id, revision, payload),
                    ).rowcount
                    if inserted != 1:
                        if observed is None:
                            raise CaseConflictError("Case changed; reload")
                        updated = connection.execute(
                            sql.SQL(
                                "UPDATE {}.review_cases SET payload = %s, "
                                "updated_at = CURRENT_TIMESTAMP "
                                "WHERE workspace_id = %s AND case_id = %s "
                                "AND revision = %s AND payload = %s"
                            ).format(self._schema),
                            (payload, self.workspace_id, image_id, revision,
                             Jsonb(json.loads(observed))),
                        ).rowcount
                        if updated != 1:
                            raise CaseConflictError("Case changed; reload")
                else:
                    if observed is None:
                        raise CaseConflictError("Case changed; reload")
                    connection.execute(
                        sql.SQL(
                            "INSERT INTO {}.review_cases "
                            "(workspace_id, case_id, revision, payload) "
                            "VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT (workspace_id, case_id) DO NOTHING"
                        ).format(self._schema),
                        (self.workspace_id, image_id, 0, payload),
                    )
                    updated = connection.execute(
                        sql.SQL(
                            "UPDATE {}.review_cases SET revision = %s, payload = %s, "
                            "updated_at = CURRENT_TIMESTAMP WHERE workspace_id = %s "
                            "AND case_id = %s AND revision = %s AND payload = %s"
                        ).format(self._schema),
                        (
                            revision,
                            payload,
                            self.workspace_id,
                            image_id,
                            revision - 1,
                            Jsonb(json.loads(observed)),
                        ),
                    ).rowcount
                    if updated != 1:
                        raise CaseConflictError("Case changed; reload")
            self._observed[image_id] = payload_text


PostgresStore = PostgresCaseStore


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_sqlite_cases(path: Path) -> list[tuple[str, dict[str, Any]]]:
    uri = f"{path.as_uri()}?mode=ro"
    connection = None
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute("SELECT id, data FROM cases ORDER BY id").fetchall()
    except (sqlite3.Error, OSError) as exc:
        raise CaseImportError("Legacy case source is not readable") from exc
    finally:
        if connection is not None:
            connection.close()

    cases: list[tuple[str, dict[str, Any]]] = []
    for case_id, raw_data in rows:
        case_id = str(case_id or "").strip()
        if not case_id:
            raise CaseImportError("Legacy case source contains an empty case id")
        try:
            case = json.loads(raw_data)
        except (TypeError, json.JSONDecodeError) as exc:
            raise CaseImportError(f"Legacy case {case_id!r} is not valid JSON") from exc
        if not isinstance(case, dict):
            raise CaseImportError(f"Legacy case {case_id!r} is not a JSON object")
        declared_id = case.get("image_id")
        if declared_id not in (None, case_id):
            raise CaseImportError(f"Legacy case {case_id!r} has a mismatched image_id")
        cases.append((case_id, case))
    return cases
