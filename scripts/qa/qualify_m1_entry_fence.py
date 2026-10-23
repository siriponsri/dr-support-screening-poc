"""One owner-approved isolated SQL rehearsal. Dry-run unless explicitly applied.

Never changes an existing role/database or creates/stores a password. LOGIN
roles have PASSWORD NULL until a separately permission-checked configuration is
available. SET SESSION AUTHORIZATION tests SQL privileges, not credential login.
All created objects are retained; no reset/drop/retry/resume path exists.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from dr_support.persistence import PostgresDatabase, PostgresSettings, SchemaMigrator
from dr_support.persistence.entry_fence_plan import EntryFencePlan


DATABASE = "dr_support_m1_interactive_test_20261023"
OWNER = "dr_support_m1_owner_test"
RUNTIME = "dr_support_m1_runtime_test"
AUTHORITY = "dr_support_m1_authority_test"
PLAN = EntryFencePlan("dr_support", "dr_support_entry_guard", OWNER, RUNTIME, AUTHORITY)


def executed_sql_controls(result):
    # Exit zero can mean collection-only/all-skipped. Accept the exact owned
    # twelve-test executed summary, never arbitrary child stdout as evidence.
    return result.returncode == 0 and re.search(
        r"(?m)^12 passed(?:, [0-9]+ warnings?)? in [0-9]+(?:\.[0-9]+)?s$",
        result.stdout.strip()) is not None


def checked_local_parameters(dsn, *, environ):
    parameters = conninfo_to_dict(dsn)
    if (any(key.startswith("PG") and value for key, value in environ.items())
            or parameters.get("service") or parameters.get("options")
            or parameters.get("host") not in {"127.0.0.1", "::1"}
            or (parameters.get("hostaddr") and parameters["hostaddr"] != parameters["host"])
            or not all(parameters.get(key) for key in ("port", "dbname", "user", "password"))
            or not parameters["port"].isascii() or not parameters["port"].isdigit()
            or not 1 <= int(parameters["port"]) <= 65535):
        raise RuntimeError("EXPLICIT_LOCAL_DB_ROUTE_WITHOUT_LIBPQ_OVERRIDES_REQUIRED")
    return parameters


def render_identity_plan():
    # These exact new identities are the explicitly approved test scope.
    # No pre-existing principal is granted membership or altered.
    return (
        sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS").format(sql.Identifier(OWNER)),
        *(sql.SQL("CREATE ROLE {} LOGIN PASSWORD NULL NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS").format(sql.Identifier(role))
          for role in (RUNTIME, AUTHORITY)),
    )


def qualify(private_configuration: Path, *, apply: bool):
    guard_sql = PLAN.render()
    identity_plan = [query.as_string(None) for query in render_identity_plan()]
    review = dict(database=DATABASE, roles=[OWNER, RUNTIME, AUTHORITY],
                  guard_sql_sha256=hashlib.sha256(guard_sql.encode()).hexdigest(),
                  role_sql_sha256=hashlib.sha256("\n".join(identity_plan).encode()).hexdigest(),
                  password_creation=False, authenticated_login_qualification="NOT_RUN")
    if not apply:
        return review | {"status": "PLAN_ONLY", "guard_sql": guard_sql, "role_sql": identity_plan}
    values = dict(line.strip().split("=", 1) for line in private_configuration.read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#"))
    source_dsn = values["DR_SUPPORT_DATABASE_URL"]
    checked_local_parameters(source_dsn, environ=os.environ)
    with psycopg.connect(source_dsn, connect_timeout=5, autocommit=True) as connection:
        if connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (DATABASE,)).fetchone():
            raise RuntimeError("NEW_TEST_DATABASE_ALREADY_EXISTS_NO_RESUME")
        if connection.execute("SELECT 1 FROM pg_roles WHERE rolname=ANY(%s)",
                              ([OWNER, RUNTIME, AUTHORITY],)).fetchone():
            raise RuntimeError("NEW_TEST_ROLE_ALREADY_EXISTS_NO_ABSORB")
        # All names checked before any mutation. A partial failure is retained;
        # rerunning never overwrites or absorbs partially provisioned scope.
        with connection.transaction():
            for query in render_identity_plan():
                connection.execute(query)
        connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
            sql.Identifier(DATABASE), sql.Identifier(OWNER)))
    target_dsn = make_conninfo(source_dsn, dbname=DATABASE)
    database = PostgresDatabase(PostgresSettings(target_dsn, schema=PLAN.application_schema))
    SchemaMigrator(database).migrate()
    with database.transaction() as connection:
        connection.execute(sql.SQL("ALTER SCHEMA {} OWNER TO {}").format(
            sql.Identifier(PLAN.application_schema), sql.Identifier(OWNER)))
        for table in ("schema_migrations", "workspaces", "review_cases", "legacy_migration_receipts"):
            connection.execute(sql.SQL("ALTER TABLE {}.{} OWNER TO {}").format(
                sql.Identifier(PLAN.application_schema), sql.Identifier(table), sql.Identifier(OWNER)))
        connection.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
            sql.Identifier(DATABASE), sql.Identifier(RUNTIME), sql.Identifier(AUTHORITY)))
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier(PLAN.application_schema), sql.Identifier(RUNTIME)))
        connection.execute(sql.SQL("GRANT SELECT ON {}.schema_migrations TO {}").format(
            sql.Identifier(PLAN.application_schema), sql.Identifier(RUNTIME)))
        for table in ("workspaces", "review_cases", "legacy_migration_receipts"):
            connection.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE ON {}.{} TO {}").format(
                sql.Identifier(PLAN.application_schema), sql.Identifier(table), sql.Identifier(RUNTIME)))
    with database.session() as connection:
        connection.execute(guard_sql)
    # Test runner gets the existing administrator DSN only in its child
    # environment; it is never printed or passed through command arguments.
    environment = dict(os.environ, DR_SUPPORT_ENTRY_FENCE_TEST_DSN=target_dsn,
                       DR_SUPPORT_ENTRY_FENCE_TEST_DATABASE=DATABASE)
    for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "FORCE_COLOR"):
        environment.pop(key, None)
    environment.update(NO_COLOR="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run([sys.executable, "-m", "pytest", "-o", "addopts=", "--color=no",
                             "-q", "tests/test_postgres_entry_fence.py"],
                            env=environment, cwd=Path(__file__).resolve().parents[2],
                            capture_output=True, text=True, timeout=180, check=False)
    # Tests must not format DSNs/secrets; retain only status/count output here.
    passed = executed_sql_controls(result)
    return review | {"status": "SQL_CONTROL_PASS" if passed else "SQL_CONTROL_FAILED",
                     "pytest_exit_code": result.returncode,
                     "pytest_output_sha256": hashlib.sha256((result.stdout + result.stderr).encode()).hexdigest(),
                     "pytest_summary": "12_EXECUTED_PASS" if passed else "FAILED_DETAILS_REDACTED",
                     "created_scope_retained": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-existing-db-env", type=Path, required=True)
    parser.add_argument("--apply-test-scope", action="store_true")
    args = parser.parse_args()
    try:
        result = qualify(args.private_existing_db_env, apply=args.apply_test_scope)
    except Exception as error:
        # Never echo psycopg exception/DSN/credentials to an operator log.
        print(json.dumps({"status": "BLOCKED_NO_AUTOMATIC_RETRY", "error_type": type(error).__name__,
                          "sqlstate": getattr(error, "sqlstate", None), "created_scope_may_be_partial": True}))
        raise SystemExit(1) from None
    print(json.dumps(result, sort_keys=True))
    if result["status"] == "SQL_CONTROL_FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
