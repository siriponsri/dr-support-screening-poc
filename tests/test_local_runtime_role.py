"""Synthetic checks for the local least-privilege runtime role script (AC-16)."""
from urllib.parse import unquote, urlsplit

import pytest

from scripts.qa import configure_local_runtime_role as tool


def write_owner(tmp_path, dsn, port="54329", schema="app_schema"):
    state = tmp_path / "local-state" / "release"
    state.mkdir(parents=True)
    (state / "postgres.env").write_text(
        f"DR_SUPPORT_DATABASE_URL={dsn}\nDR_SUPPORT_POSTGRES_PORT={port}\n", encoding="utf-8")
    (tmp_path / ".env").write_text(f"DR_SUPPORT_DATABASE_SCHEMA={schema}\n", encoding="utf-8")


def test_only_the_loopback_project_owned_database_is_accepted(tmp_path):
    write_owner(tmp_path, "postgresql://owner:secret@127.0.0.1:54329/dr_support")
    dsn, schema, state = tool.owner_settings(tmp_path)
    assert schema == "app_schema" and state.name == "release" and dsn.endswith("/dr_support")


@pytest.mark.parametrize("dsn", [
    "postgresql://owner:secret@db.hospital.invalid:54329/dr_support",
    "postgresql://owner:secret@127.0.0.1:5432/dr_support",
])
def test_remote_or_unrecorded_databases_are_refused(tmp_path, dsn):
    write_owner(tmp_path, dsn)
    with pytest.raises(tool.RuntimeRoleError, match="LOOPBACK_PROJECT_OWNED_DATABASE_ONLY"):
        tool.owner_settings(tmp_path)


def test_runtime_dsn_uses_the_runtime_role_and_quotes_the_password():
    dsn = tool.runtime_dsn("postgresql://owner:secret@127.0.0.1:54329/dr_support", "a/b:c@d")
    parts = urlsplit(dsn)
    assert parts.username == tool.ROLE and unquote(parts.password) == "a/b:c@d"
    assert parts.hostname == "127.0.0.1" and parts.port == 54329 and parts.path == "/dr_support"
    assert "owner" not in dsn and "secret" not in dsn


def test_role_creation_commits_before_the_login_is_tested():
    source = (tool.REPO_ROOT / "scripts" / "qa" / "configure_local_runtime_role.py").read_text(encoding="utf-8")
    apply_block = source[source.index('require(not planned["role_exists"]'):]
    assert apply_block.index("connection.commit()") < apply_block.index("with connection.transaction():")
    assert apply_block.index("with connection.transaction():") < apply_block.index("verify_runtime(dsn, schema)")
