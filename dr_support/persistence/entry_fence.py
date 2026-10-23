"""Unregistered authority-only PostgreSQL fence client, with bounded calls.

The composed app must additionally coordinate all in-memory writers and immutable
source checks. Neither the SQL functions nor this class authenticates arbitrary
status JSON. The injected reader must be the separately qualified private channel.
"""
from copy import deepcopy

from psycopg import sql
from psycopg.types.json import Jsonb

from .entry_fence_plan import EntryFencePlan


class EntryFenceError(RuntimeError):
    pass


class PostgresEntryFence:
    def __init__(self, database, *, plan: EntryFencePlan, authenticated_status_reader):
        if not callable(authenticated_status_reader):
            raise ValueError("AUTHENTICATED_OLD_JOB_READER_REQUIRED")
        if database.settings.schema != plan.application_schema:
            raise ValueError("ENTRY_FENCE_DATABASE_SCHEMA_MISMATCH")
        self.database, self.plan = database, plan
        self.reader = authenticated_status_reader

    def _call(self, operation, *parameters):
        if operation not in {"read_entry", "begin_entry", "release_entry"}:
            raise ValueError("FIXED_ENTRY_FENCE_OPERATION_REQUIRED")
        placeholders = sql.SQL(",").join(sql.Placeholder() for _ in parameters)
        query = sql.SQL("SELECT {}.{}({})").format(
            sql.Identifier(self.plan.guard_schema), sql.Identifier(operation), placeholders)
        with self.database.transaction() as connection:
            # Installation-time settings do not survive into runtime sessions.
            # No inherited REPEATABLE READ snapshot may predate the SHARE fence.
            connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            connection.execute("SET LOCAL lock_timeout = '1s'")
            connection.execute("SET LOCAL statement_timeout = '3s'")
            result = connection.execute(query, parameters).fetchone()[0]
        # Successful return is AFTER the transaction commit; uncertain commit
        # raises and the durable fence is inspected on recovery, never reset.
        return deepcopy(result)

    def read(self):
        return self._call("read_entry")

    def acquire(self, *, workspace_id, image_id, case, workspace, binding):
        self._call("begin_entry", workspace_id, image_id,
                   Jsonb(deepcopy(case)), Jsonb(deepcopy(workspace)), Jsonb(deepcopy(binding)))
        return _DatabaseEntryPermit(self, deepcopy(binding))

    def recover(self):
        binding = self.read()
        if binding is not None:
            self._release_authenticated(binding)

    def _release_authenticated(self, binding):
        status = self.reader(deepcopy(binding))
        keys = ("epoch", "job_id", "ticket_id", "plan_sha256", "pins", "challenge_id")
        if (not isinstance(status, dict)
                or any(status.get(key) != binding.get(key) for key in keys)
                or any(key not in binding for key in keys)
                or type(status.get("forward_started")) is not bool
                or type(status.get("terminal")) is not bool
                or status.get("state") not in {"FORWARD_STARTED", "COMPLETE", "FAILED", "ABORTED"}
                or status["terminal"] != (status["state"] in {"COMPLETE", "FAILED", "ABORTED"})
                or (status["state"] in {"FORWARD_STARTED", "COMPLETE"} and not status["forward_started"])
                or not (status["forward_started"] or status["terminal"])):
            raise EntryFenceError("MATCHING_AUTHENTICATED_ENTRY_OR_TERMINAL_REQUIRED")
        self._call("release_entry", Jsonb(binding))


class _DatabaseEntryPermit:
    def __init__(self, authority, binding):
        self._authority, self._binding = authority, binding
        self.fence_id = binding["fence_id"]

    def release(self, _proof):
        # Re-read through the trusted channel. A supplied dict/NO_GRANT_SENT,
        # timeout, cancel ACK or new epoch never authenticates release.
        self._authority._release_authenticated(self._binding)

    def quarantine(self, _reason):
        # The committed binding is already the durable quarantine. No TTL or
        # release occurs on exception/connection close/process restart.
        pass
