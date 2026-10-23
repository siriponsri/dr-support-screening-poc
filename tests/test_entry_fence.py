"""Authority client controls; real SQL/roles require separate opt-in tests."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from dr_support.persistence.entry_fence import EntryFenceError, PostgresEntryFence
from dr_support.persistence.entry_fence_plan import EntryFencePlan


PLAN = EntryFencePlan("app", "guard", "owner", "runtime", "authority")
BINDING = dict(fence_id="fence_1", epoch="old_worker", job_id="old_job",
               ticket_id="old_ticket", plan_sha256="1" * 64,
               pins={"weights": "2" * 64}, challenge_id="old_challenge")


class Database:
    settings = SimpleNamespace(schema="app")

    def __init__(self):
        self.queries, self.committed, self.fail_commit = [], False, False

    @contextmanager
    def transaction(self):
        self.committed = False
        yield self
        if self.fail_commit:
            raise OSError("Ambiguous commit: retained fence must be recovered")
        self.committed = True

    def execute(self, query, parameters=()):
        self.queries.append((query if isinstance(query, str) else query.as_string(None), parameters))
        return SimpleNamespace(fetchone=lambda: (None,))


def test_acquisition_returns_only_after_commit_and_sets_each_runtime_deadline():
    database = Database()
    fence = PostgresEntryFence(database, plan=PLAN, authenticated_status_reader=lambda b: None)
    permit = fence.acquire(workspace_id="w", image_id="i", case={}, workspace={}, binding=BINDING)
    assert database.committed and permit.fence_id == BINDING["fence_id"]
    assert [query for query, _ in database.queries[:3]] == [
        "SET TRANSACTION ISOLATION LEVEL READ COMMITTED",
        "SET LOCAL lock_timeout = '1s'", "SET LOCAL statement_timeout = '3s'"]
    assert 'SELECT "guard"."begin_entry"(' in database.queries[-1][0]
    database.fail_commit = True
    with pytest.raises(OSError, match="Ambiguous commit"):
        fence.acquire(workspace_id="w", image_id="i", case={}, workspace={}, binding=BINDING)
    assert not database.committed


@pytest.mark.parametrize("fault", ["missing", "epoch", "job_id", "ticket_id", "plan_sha256",
                                  "pins", "challenge_id", "cancel_ack", "waiting", "bool_int"])
def test_unknown_or_wrong_status_cannot_release_database_fence(fault):
    status = deepcopy(BINDING) | dict(state="FORWARD_STARTED", forward_started=True, terminal=False)
    if fault == "missing":
        status = None
    elif fault in BINDING:
        status[fault] = "changed"
    elif fault == "cancel_ack":
        status.update(state="CANCEL_REQUESTED", forward_started=False)
    elif fault == "waiting":
        status.update(state="WAITING_SOURCE_FENCE", forward_started=False)
    else:
        status["forward_started"] = 1
    database = Database()
    fence = PostgresEntryFence(database, plan=PLAN, authenticated_status_reader=lambda b: status)
    with pytest.raises(EntryFenceError, match="AUTHENTICATED"):
        fence._release_authenticated(BINDING)
    assert database.queries == []


@pytest.mark.parametrize("state,started,terminal", [("FORWARD_STARTED", True, False),
                                                  ("COMPLETE", True, True),
                                                  ("FAILED", False, True),
                                                  ("ABORTED", False, True)])
def test_release_uses_reauthenticated_old_binding_and_exact_sql_match(state, started, terminal):
    seen = []
    def reader(binding):
        seen.append(binding)
        return binding | dict(state=state, forward_started=started, terminal=terminal)
    database = Database()
    fence = PostgresEntryFence(database, plan=PLAN, authenticated_status_reader=reader)
    permit = fence.acquire(workspace_id="w", image_id="i", case={}, workspace={}, binding=BINDING)
    before = len(database.queries)
    permit.quarantine("unknown")
    assert len(database.queries) == before
    permit.release({"kind": "NO_GRANT_SENT", "status": "untrusted ignored"})
    assert seen == [BINDING]
    assert 'SELECT "guard"."release_entry"(' in database.queries[-1][0]
    assert database.committed
