"""Opt-in isolated real PostgreSQL controls; no model/native-entry qualification.

No provisioning occurs in these tests. Three fresh roles and a new DB must have
been explicitly approved/provisioned by qualify_m1_entry_fence.py. Connections
use SET SESSION AUTHORIZATION, not newly authenticated runtime credentials.
"""
from contextlib import contextmanager
import os
from threading import Event, Thread
import time
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
import pytest

from scripts.qa.qualify_m1_entry_fence import AUTHORITY, DATABASE, RUNTIME


@pytest.fixture(scope="module")
def dsn():
    value = os.environ.get("DR_SUPPORT_ENTRY_FENCE_TEST_DSN")
    if not value:
        pytest.skip("Explicit new M1 entry-fence test scope not configured")
    if (os.environ.get("DR_SUPPORT_ENTRY_FENCE_TEST_DATABASE") != DATABASE
            or conninfo_to_dict(value).get("dbname") != DATABASE):
        pytest.fail("EXACT_APPROVED_ENTRY_FENCE_TEST_DATABASE_REQUIRED")
    return value


@contextmanager
def session(dsn, role, *, autocommit=True):
    from psycopg import sql
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as connection:
        connection.execute(sql.SQL("SET SESSION AUTHORIZATION {}").format(sql.Identifier(role)))
        connection.execute("SET lock_timeout='2s'")
        connection.execute("SET statement_timeout='5s'")
        connection.autocommit = autocommit
        yield connection


def wait_for_blocked_backend(dsn, pid, blocker):
    # Observe the actual owned backend waiting for a lock. Thread scheduling
    # or an Event fired before execute() is not evidence of a SQL lock barrier.
    end = time.monotonic() + 2
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as observer:
        while time.monotonic() < end:
            row = observer.execute("SELECT state,wait_event_type,%s = ANY(pg_blocking_pids(pid)) FROM pg_stat_activity WHERE pid=%s", (blocker, pid)).fetchone()
            if row == ("active", "Lock", True):
                return
            time.sleep(.01)
    pytest.fail("Owned PostgreSQL backend did not reach the lock barrier")


def fixture_case(dsn):
    workspace, image = "ws_fence_test_" + uuid4().hex, "engineering_case_" + uuid4().hex
    payload = dict(image_id=image, revision=0, engineering_test_control=True)
    with session(dsn, RUNTIME) as connection:
        connection.execute("INSERT INTO dr_support.workspaces(workspace_id) VALUES(%s)", (workspace,))
        connection.execute("INSERT INTO dr_support.review_cases(workspace_id,case_id,revision,payload) VALUES(%s,%s,0,%s)",
                           (workspace, image, Jsonb(payload)))
        row = connection.execute("SELECT to_jsonb(w) FROM dr_support.workspaces w WHERE workspace_id=%s",
                                 (workspace,)).fetchone()[0]
    binding = dict(fence_id=uuid4().hex, epoch="synthetic_control_epoch", job_id=uuid4().hex,
                   ticket_id=uuid4().hex, plan_sha256="1" * 64, pins={"control": "no model"}, challenge_id=uuid4().hex)
    return workspace, image, payload, row, binding


def acquire(connection, case):
    workspace, image, payload, row, binding = case
    connection.execute("SELECT dr_support_entry_guard.begin_entry(%s,%s,%s,%s,%s)",
                       (workspace, image, Jsonb(payload), Jsonb(row), Jsonb(binding)))


def release(dsn, binding):
    # SQL permission/lock control only. No claim that this synthetic binding
    # authenticates a real model. Composed authority qualification is separate.
    with session(dsn, AUTHORITY) as connection:
        connection.execute("SELECT dr_support_entry_guard.release_entry(%s)", (Jsonb(binding),))


def test_new_runtime_privileges_are_non_owner_and_non_elevated(dsn):
    with session(dsn, RUNTIME) as connection:
        assert connection.execute("SELECT current_user,session_user").fetchone() == (RUNTIME, RUNTIME)
        assert connection.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone() == (False,) * 4
        assert not connection.execute("SELECT has_schema_privilege(current_user,'dr_support','CREATE')").fetchone()[0]
        assert not connection.execute("SELECT has_table_privilege(current_user,c.oid,'UPDATE') FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='dr_support_entry_guard' AND c.relname='entry_fence'").fetchone()[0]


@pytest.mark.parametrize("query", [
    "CREATE TABLE dr_support.forbidden_test(value int)",
    "ALTER TABLE dr_support.review_cases DISABLE TRIGGER m1_entry_fence",
    "UPDATE dr_support_entry_guard.entry_fence SET binding=NULL",
    "SELECT dr_support_entry_guard.release_entry('{}'::jsonb)",
    "TRUNCATE dr_support.review_cases",
    "SET ROLE dr_support_m1_authority_test",
    "SET session_replication_role='replica'",
])
def test_runtime_cannot_disable_or_release_the_guard(dsn, query):
    with session(dsn, RUNTIME) as connection:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(query)


def test_committed_fence_survives_connection_loss_and_refuses_another_writer(dsn):
    case = fixture_case(dsn)
    with session(dsn, AUTHORITY) as connection:
        acquire(connection, case)
    # Authority connection is gone. Its committed binding remains active.
    try:
        with session(dsn, RUNTIME) as connection:
            with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
                connection.execute("UPDATE dr_support.review_cases SET payload=payload WHERE workspace_id=%s", (case[0],))
        with session(dsn, AUTHORITY) as connection:
            assert connection.execute("SELECT dr_support_entry_guard.read_entry()").fetchone()[0] == case[4]
            with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
                connection.execute("SELECT dr_support_entry_guard.release_entry('{}'::jsonb)")
    finally:
        release(dsn, case[4])
    with session(dsn, RUNTIME) as connection:
        assert connection.execute("UPDATE dr_support.review_cases SET payload=payload WHERE workspace_id=%s", (case[0],)).rowcount == 1


def test_same_revision_write_changes_final_source_context(dsn):
    case = fixture_case(dsn)
    with session(dsn, RUNTIME) as connection:
        connection.execute("UPDATE dr_support.review_cases SET payload=payload || '{\"changed_without_revision\":true}'::jsonb WHERE workspace_id=%s", (case[0],))
    with session(dsn, AUTHORITY) as connection:
        with pytest.raises(psycopg.errors.SerializationFailure):
            acquire(connection, case)
        assert connection.execute("SELECT dr_support_entry_guard.read_entry()").fetchone()[0] is None


def test_entry_waits_for_prior_writer_then_compares_committed_payload(dsn):
    case, started, finished, outcome, backend = fixture_case(dsn), Event(), Event(), [], []
    def entry():
        with session(dsn, AUTHORITY) as connection:
            backend.append(connection.info.backend_pid)
            started.set()
            try:
                acquire(connection, case)
                outcome.append("unexpected_grant")
            except psycopg.errors.SerializationFailure:
                outcome.append("source_changed")
            finally:
                finished.set()
    with session(dsn, RUNTIME, autocommit=False) as writer:
        writer.execute("UPDATE dr_support.review_cases SET payload=payload || '{\"prior_writer\":true}'::jsonb WHERE workspace_id=%s", (case[0],))
        thread = Thread(target=entry)
        thread.start()
        assert started.wait(2)
        wait_for_blocked_backend(dsn, backend[0], writer.info.backend_pid)
        assert not finished.is_set()
        writer.commit()
        thread.join(6)
    assert not thread.is_alive() and outcome == ["source_changed"]


def test_writer_waiting_on_uncommitted_fence_is_refused_after_commit(dsn):
    case, started, finished, outcome, backend = fixture_case(dsn), Event(), Event(), [], []
    def writer():
        with session(dsn, RUNTIME) as connection:
            backend.append(connection.info.backend_pid)
            started.set()
            try:
                connection.execute("UPDATE dr_support.review_cases SET payload=payload WHERE workspace_id=%s", (case[0],))
                outcome.append("unexpected_write")
            except psycopg.errors.ObjectNotInPrerequisiteState:
                outcome.append("fenced")
            finally:
                finished.set()
    try:
        with session(dsn, AUTHORITY, autocommit=False) as authority:
            acquire(authority, case)
            thread = Thread(target=writer)
            thread.start()
            assert started.wait(2)
            wait_for_blocked_backend(dsn, backend[0], authority.info.backend_pid)
            assert not finished.is_set()
            authority.commit()
            thread.join(6)
        assert not thread.is_alive() and outcome == ["fenced"]
    finally:
        release(dsn, case[4])
