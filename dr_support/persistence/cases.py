"""Workspace-scoped PostgreSQL persistence for review case documents."""

from __future__ import annotations

import json
from contextlib import contextmanager
from threading import RLock
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from ..store import apply_case_defaults, new_case
from .database import PostgresDatabase


class CaseConflictError(RuntimeError):
    """A case update was based on a revision that is no longer current."""


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

    @contextmanager
    def repeatable_read_cases(self):
        """Materialize one short-lived PostgreSQL read-only snapshot."""
        with self.database.session(autocommit=False) as connection:
            with connection.transaction():
                connection.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
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
                yield cases

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
                        # Startup admission enrichment can preserve the current revision.
                        updated = connection.execute(
                            sql.SQL(
                                "UPDATE {}.review_cases SET payload = %s, "
                                "updated_at = CURRENT_TIMESTAMP WHERE workspace_id = %s "
                                "AND case_id = %s AND revision = %s AND payload = %s"
                            ).format(self._schema),
                            (
                                payload,
                                self.workspace_id,
                                image_id,
                                revision,
                                Jsonb(json.loads(observed)),
                            ),
                        ).rowcount
                    if updated != 1:
                        raise CaseConflictError("Case changed; reload")
            self._observed[image_id] = payload_text


PostgresStore = PostgresCaseStore
