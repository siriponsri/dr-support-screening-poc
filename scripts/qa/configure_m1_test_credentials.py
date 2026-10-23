"""Provision credentials only for the owner's existing isolated M1 test roles.

Dry-run by default. No role/database creation, ACL changes, old credential edits,
reset, overwrite or automatic resume. Interrupted files remain for inspection.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from dr_support.services.filesystem_privacy import has_reparse_component, private_hospital_root
from scripts.qa.qualify_m1_entry_fence import AUTHORITY, DATABASE, OWNER, PLAN, RUNTIME, checked_local_parameters


PRIVATE_DIRECTORY = Path("C:/Users/User/AppData/Local/DRScreening/M1PrivateConfig")
FILES = ("m1_runtime.env", "m1_authority.env", "credentials-staged.json", "credentials-login-proof.json")


class CredentialProvisionError(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise CredentialProvisionError(code)


def write_new(path, raw):
    with path.open("xb") as stream:
        require(stream.write(raw) == len(raw), "PARTIAL_PRIVATE_CONFIGURATION_RETAINED")
        stream.flush()
        os.fsync(stream.fileno())


def _scope(connection):
    owner = connection.execute(
        "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s", (DATABASE,)
    ).fetchone()
    require(owner == (OWNER,), "EXACT_TEST_DATABASE_OWNER_REQUIRED")
    rows = connection.execute(
        "SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
        "rolbypassrls, rolpassword IS NULL FROM pg_authid WHERE rolname=ANY(%s) ORDER BY rolname",
        ([RUNTIME, AUTHORITY],),
    ).fetchall()
    expected = sorted((role, True, False, False, False, False, False, True) for role in (RUNTIME, AUTHORITY))
    require(rows == expected, "ONLY_EXACT_NEW_PASSWORD_NULL_TEST_ROLES_ALLOWED")
    memberships = connection.execute(
        "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
        "WHERE r.rolname=ANY(%s) LIMIT 1", ([RUNTIME, AUTHORITY],)
    ).fetchone()
    require(memberships is None, "NEW_TEST_ROLES_MUST_HAVE_NO_MEMBERSHIPS")


def authenticated_login(dsn, expected_role):
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '3s'")
            row = connection.execute(
                "SELECT current_user, session_user, current_database(), "
                "r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolreplication, r.rolbypassrls "
                "FROM pg_roles r WHERE r.rolname=current_user"
            ).fetchone()
            require(connection.pgconn.used_password == 1
                    and connection.info.user == expected_role and connection.info.dbname == DATABASE
                    and row == (expected_role, expected_role, DATABASE, False, False, False, False, False),
                    "AUTHENTICATED_LEAST_PRIVILEGE_TEST_LOGIN_REQUIRED")
            connection.execute("SELECT 1").fetchone()
    return {"role": expected_role, "database": DATABASE, "authenticated_login": "PASS", "password_used": True,
            "role_flags": "NO_ELEVATED_ATTRIBUTES", "clinical_validation": "NOT_RUN"}


def configure(administrator_configuration, *, directory=PRIVATE_DIRECTORY, apply=False):
    directory = Path(directory)
    require(directory == PRIVATE_DIRECTORY, "EXACT_OWNER_APPROVED_PRIVATE_DIRECTORY_REQUIRED")
    require(directory.is_dir() and not has_reparse_component(directory)
            and private_hospital_root(directory), "APPROVED_PRIVATE_DIRECTORY_CHECK_REQUIRED")
    require(not any((directory / name).exists() or (directory / name).is_symlink() for name in FILES),
            "EXISTING_PRIVATE_CONFIGURATION_NO_OVERWRITE_OR_RESUME")
    review = {"database": DATABASE, "roles": [RUNTIME, AUTHORITY], "private_directory": str(directory),
              "acl_changes": False, "existing_credentials_changed": False,
              "scope": "NEW_M1_TEST_ROLES_ONLY", "automatic_resume": False}
    if not apply:
        return review | {"status": "PLAN_ONLY", "password_creation": False}
    values = dict(line.strip().split("=", 1) for line in Path(administrator_configuration).read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#"))
    source_dsn = values["DR_SUPPORT_DATABASE_URL"]
    parameters = checked_local_parameters(source_dsn, environ=os.environ)
    require(parameters["host"] == "127.0.0.1" and parameters["port"] == "54805",
            "EXISTING_APPROVED_LOOPBACK_TEST_DATABASE_ROUTE_REQUIRED")
    target_dsn = make_conninfo(source_dsn, dbname=DATABASE)
    # Nothing is generated or written before the real target identities pass.
    with psycopg.connect(target_dsn, connect_timeout=5) as connection:
        with connection.transaction():
            connection.execute("SET LOCAL lock_timeout = '2s'")
            connection.execute("SET LOCAL statement_timeout = '5s'")
            _scope(connection)
            binding = connection.execute(sql.SQL("SELECT binding FROM {}.entry_fence WHERE singleton").format(
                sql.Identifier(PLAN.guard_schema))).fetchone()
            require(binding == (None,), "TEST_ENTRY_FENCE_MUST_BE_IDLE")
            role_dsns = {}
            for role, filename, variable in (
                (RUNTIME, FILES[0], "DR_SUPPORT_DATABASE_URL"),
                (AUTHORITY, FILES[1], "DR_SUPPORT_AUTHORITY_DATABASE_URL"),
            ):
                password = secrets.token_urlsafe(48)
                # An allowlisted explicit DSN prevents libpq options/services
                # and avoids persisting the administrator's other settings.
                role_dsns[role] = make_conninfo(host="127.0.0.1", port="54805", dbname=DATABASE,
                                               user=role, password=password)
                raw = (f"{variable}={role_dsns[role]}\nDR_SUPPORT_DATABASE_SCHEMA={PLAN.application_schema}\n"
                       "DR_SUPPORT_DATABASE_SCHEMA_MODE=verify\n").encode()
                write_new(directory / filename, raw)
                require(private_hospital_root(directory), "NEW_PRIVATE_FILE_CHECK_FAILED_RETAINED")
                # Only a SCRAM verifier enters the ALTER statement; neither
                # password nor verifier is printed or retained in diagnostics.
                verifier = connection.pgconn.encrypt_password(password.encode(), role.encode(), b"scram-sha-256")
                connection.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(verifier.decode())))
            write_new(directory / FILES[2], json.dumps(review | {
                "status": "STAGED_COMMIT_NOT_YET_CONFIRMED",
                "utc": datetime.now(timezone.utc).isoformat(),
            }, sort_keys=True).encode())
        # Successful exit is after COMMIT. Unknown commit is never retried.
    proofs = [authenticated_login(role_dsns[role], role) for role in (RUNTIME, AUTHORITY)]
    result = review | {"status": "AUTHENTICATED_LOGIN_PASS", "password_creation": True,
                       "logins": proofs, "inference_requests": 0, "model_readiness": "NOT_RUN"}
    try:
        write_new(directory / FILES[3], json.dumps(result, sort_keys=True).encode())
    except OSError:
        return result | {"evidence_logging": "BLOCKED", "new_admissions_allowed": False}
    return result | {"evidence_logging": "PASS"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--administrator-config", type=Path, required=True)
    parser.add_argument("--apply-test-credentials", action="store_true")
    args = parser.parse_args()
    try:
        result = configure(args.administrator_config, apply=args.apply_test_credentials)
    except Exception as error:
        # Never print psycopg error text, SQL, DSN, password or verifier.
        result = {"status": "BLOCKED", "error_class": type(error).__name__,
                  "reason": str(error) if type(error) is CredentialProvisionError else "DETAILS_REDACTED",
                  "partial_state_retained": True, "automatic_resume": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"PLAN_ONLY", "AUTHENTICATED_LOGIN_PASS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
