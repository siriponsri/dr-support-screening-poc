"""Credential control tests with synthetic SQL ports; no DB, ACL or real secret."""
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts.qa import configure_m1_test_credentials as module


class Result:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value

    def fetchall(self):
        return self.value


class Connection:
    def __init__(self, role="admin", *, password_null=True):
        self.role, self.password_null, self.queries = role, password_null, []
        self.info = SimpleNamespace(user=role, dbname=module.DATABASE)
        self.pgconn = SimpleNamespace(encrypt_password=self.encrypt)

    def encrypt(self, password, role, algorithm):
        assert password == b"synthetic-generated-password" and algorithm == b"scram-sha-256"
        return b"SCRAM-SHA-256$synthetic-verifier-only"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def transaction(self):
        return nullcontext()

    def execute(self, query, parameters=None):
        text = query if isinstance(query, str) else query.as_string(None)
        self.queries.append((text, deepcopy(parameters)))
        if "pg_get_userbyid" in text:
            return Result((module.OWNER,))
        if "FROM pg_authid" in text:
            return Result(sorted((role, True, False, False, False, False, False, self.password_null)
                                 for role in (module.RUNTIME, module.AUTHORITY)))
        if "FROM pg_auth_members" in text:
            return Result(None)
        if "SELECT binding" in text:
            return Result((None,))
        if "SELECT current_user" in text:
            return Result((self.role, self.role, module.DATABASE, False, False, False, False, False))
        return Result((1,))


@pytest.fixture
def rig(tmp_path, monkeypatch):
    private = tmp_path / "approved-synthetic-directory"
    private.mkdir()
    administrator = tmp_path / "source.env"
    administrator.write_text("DR_SUPPORT_DATABASE_URL=host=127.0.0.1 port=54805 dbname=original "
                             "user=admin password=synthetic-existing-admin\n")
    monkeypatch.setattr(module, "PRIVATE_DIRECTORY", private)
    monkeypatch.setattr(module, "private_hospital_root", lambda *_: True)
    monkeypatch.setattr(module.secrets, "token_urlsafe", lambda *_: "synthetic-generated-password")
    for name in tuple(module.os.environ):
        if name.startswith("PG"):
            monkeypatch.delenv(name)
    admin = Connection()
    calls = []

    def connect(dsn, **kwargs):
        from psycopg.conninfo import conninfo_to_dict
        role = conninfo_to_dict(dsn)["user"]
        calls.append(role)
        return admin if role == "admin" else Connection(role)

    monkeypatch.setattr(module.psycopg, "connect", connect)
    return SimpleNamespace(private=private, administrator=administrator, admin=admin, calls=calls)


def test_dry_run_never_reads_admin_config_or_connects_or_generates(rig, monkeypatch):
    monkeypatch.setattr(module.secrets, "token_urlsafe", lambda *_: pytest.fail("No secret generation"))
    result = module.configure(rig.private / "absent-admin.env", directory=rig.private)
    assert result["status"] == "PLAN_ONLY" and not result["password_creation"]
    assert rig.calls == [] and list(rig.private.iterdir()) == []


@pytest.mark.parametrize("gate", ["wrong-directory", "privacy", "collision", "symlink"])
def test_configuration_gate_rejects_before_admin_or_password_access(rig, monkeypatch, gate):
    directory = rig.private
    if gate == "wrong-directory":
        directory = rig.private / "other"
    elif gate == "privacy":
        monkeypatch.setattr(module, "private_hospital_root", lambda *_: False)
    elif gate == "collision":
        (directory / module.FILES[0]).write_text("retain this existing test configuration")
    else:
        monkeypatch.setattr(module, "has_reparse_component", lambda *_: True)
    with pytest.raises(module.CredentialProvisionError):
        module.configure(rig.administrator, directory=directory, apply=True)
    assert rig.calls == []
    if gate == "collision":
        assert (directory / module.FILES[0]).read_text() == "retain this existing test configuration"


def test_existing_password_refused_without_any_file_or_alter(rig):
    rig.admin.password_null = False
    with pytest.raises(module.CredentialProvisionError, match="PASSWORD_NULL"):
        module.configure(rig.administrator, directory=rig.private, apply=True)
    assert list(rig.private.iterdir()) == []
    assert not any("ALTER ROLE" in text for text, _ in rig.admin.queries)


def test_generated_files_are_distinct_role_logins_and_only_scram_verifiers_reach_alter(rig):
    result = module.configure(rig.administrator, directory=rig.private, apply=True)
    assert result["status"] == "AUTHENTICATED_LOGIN_PASS" and result["inference_requests"] == 0
    assert rig.calls == ["admin", module.RUNTIME, module.AUTHORITY]
    assert {item.name for item in rig.private.iterdir()} == set(module.FILES)
    for filename, role in zip(module.FILES[:2], (module.RUNTIME, module.AUTHORITY), strict=True):
        content = (rig.private / filename).read_text()
        assert f"user={role}" in content and "SCHEMA_MODE=verify" in content
        assert "synthetic-existing-admin" not in content
    altered = [text for text, _ in rig.admin.queries if "ALTER ROLE" in text]
    assert len(altered) == 2 and all("SCRAM-SHA-256$synthetic-verifier-only" in text for text in altered)
    assert all("synthetic-generated-password" not in text for text in altered)
    assert "synthetic-generated-password" not in str(result)
    assert "synthetic-existing-admin" not in str(result)
    with pytest.raises(module.CredentialProvisionError, match="NO_OVERWRITE"):
        module.configure(rig.administrator, directory=rig.private, apply=True)


def test_partial_private_write_is_retained_without_a_password_change(rig, monkeypatch):
    real_write = module.write_new

    def interrupted(path, raw):
        real_write(path, raw[:12])
        raise OSError("synthetic interrupted write")

    monkeypatch.setattr(module, "write_new", interrupted)
    with pytest.raises(OSError):
        module.configure(rig.administrator, directory=rig.private, apply=True)
    assert (rig.private / module.FILES[0]).is_file()
    assert not any("ALTER ROLE" in text for text, _ in rig.admin.queries)


def test_logging_failure_does_not_relabel_completed_logins(rig, monkeypatch):
    real_write = module.write_new

    def failing_evidence(path, raw):
        if path.name == module.FILES[3]:
            raise OSError("synthetic evidence failure")
        real_write(path, raw)

    monkeypatch.setattr(module, "write_new", failing_evidence)
    result = module.configure(rig.administrator, directory=rig.private, apply=True)
    assert result["status"] == "AUTHENTICATED_LOGIN_PASS"
    assert result["evidence_logging"] == "BLOCKED" and not result["new_admissions_allowed"]
    assert len(result["logins"]) == 2


def test_admin_session_impersonation_is_not_authenticated_runtime_login(monkeypatch):
    connection = Connection(module.RUNTIME)
    connection.info.user = "admin"
    monkeypatch.setattr(module.psycopg, "connect", lambda *a, **k: connection)
    with pytest.raises(module.CredentialProvisionError, match="AUTHENTICATED"):
        module.authenticated_login("synthetic-dsn", module.RUNTIME)
