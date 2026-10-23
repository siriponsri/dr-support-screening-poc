"""Read-only migration startup controls; no live database or role provisioning."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from dr_support.persistence.migrations import MIGRATIONS, MigrationError, SchemaMigrator


class Database:
    settings = SimpleNamespace(schema="qa_runtime")

    def __init__(self, rows):
        self.rows, self.queries = rows, []

    @contextmanager
    def session(self, *, autocommit):
        assert not autocommit
        yield self

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, query):
        text = query if isinstance(query, str) else query.as_string(None)
        assert text.startswith(("SET TRANSACTION", "SELECT "))
        self.queries.append(text)
        return SimpleNamespace(fetchall=lambda: self.rows)


def history():
    return [(item.version, item.name, item.checksum) for item in MIGRATIONS]


def test_runtime_verifies_complete_history_without_ddl_or_advisory_writes():
    database = Database(history())
    result = SchemaMigrator(database).verify()
    assert result.current_version == len(MIGRATIONS)
    assert not result.applied_versions
    assert len(database.queries) == 2
    assert "READ ONLY" in database.queries[0]


@pytest.mark.parametrize("fault", ["missing", "old", "gap", "checksum", "unknown", "duplicate"])
def test_runtime_refuses_incompatible_history_without_repair(fault):
    rows = history()
    if fault == "missing":
        rows = []
    elif fault == "old":
        rows = rows[:-1]
    elif fault == "gap":
        rows = rows[1:]
    elif fault == "checksum":
        rows[0] = (1, rows[0][1], "0" * 64)
    elif fault == "unknown":
        rows.append((len(MIGRATIONS) + 1, "unknown", "0" * 64))
    else:
        rows.append(rows[-1])
    database = Database(rows)
    with pytest.raises(MigrationError):
        SchemaMigrator(database).verify()
    assert all(query.startswith(("SET TRANSACTION", "SELECT ")) for query in database.queries)


def test_review_startup_selects_read_only_verification_and_never_migrates(monkeypatch):
    from dr_support.api import _factory

    monkeypatch.setenv("DR_SUPPORT_DATABASE_MIGRATION_MODE", "verify")
    monkeypatch.setenv("DR_SUPPORT_DATABASE_URL", "dbname=synthetic_test")
    calls = []
    monkeypatch.setattr(_factory.SchemaMigrator, "verify", lambda self: calls.append("verify"))
    monkeypatch.setattr(_factory.SchemaMigrator, "migrate", lambda self: pytest.fail("DDL attempted"))
    monkeypatch.setattr(_factory, "PostgresCaseStore", lambda *args: SimpleNamespace(ensure_workspace=lambda: None))
    _factory._build_case_store("postgres", None, "test_workspace")
    assert calls == ["verify"]
