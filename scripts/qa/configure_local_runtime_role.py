"""Create a least-privilege runtime role for the project-owned local PostgreSQL (AC-16 / DT-02).

Owner decision 2026-10-25. Dry-run by default; ``--apply`` makes the change once.

* Only the Windows launcher's project-owned database is touched: the owner
  connection comes from ``local-state/release/postgres.env`` and must point at
  127.0.0.1 on its recorded port.
* Creates ``dr_support_runtime`` (LOGIN, no SUPERUSER/CREATEDB/CREATEROLE/
  REPLICATION/BYPASSRLS) with CONNECT, USAGE on the app schema, SELECT on
  ``schema_migrations`` and SELECT/INSERT/UPDATE on ``workspaces`` and
  ``review_cases`` (the PostgreSQL path never deletes; archiving is an update).
  Default privileges give the same access to tables later migrations add. No
  CREATE, no ownership. An existing role is never altered or overwritten.
* The password is sent pre-hashed (SCRAM) so it cannot reach server logs. If any
  step fails before the end, the role is dropped and the file removed.
* Proves the new login works and that DDL is denied, then writes the runtime
  connection to ``local-state/release/postgres-runtime.env`` (git-ignored, beside
  the existing owner file). The password is generated and never printed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import quote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = "dr_support_runtime"
DML_TABLES = ("workspaces", "review_cases")
DML_PRIVILEGES = "SELECT, INSERT, UPDATE"
READ_TABLES = ("schema_migrations",)


class RuntimeRoleError(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise RuntimeRoleError(code)


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key:
            values[key] = value.strip().strip('"').strip("'")
    return values


def owner_settings(checkout: Path) -> tuple[str, str, Path]:
    state = checkout / "local-state" / "release"
    owner_file = state / "postgres.env"
    require(owner_file.is_file(), "PROJECT_OWNED_POSTGRES_CONFIGURATION_REQUIRED")
    values = read_env(owner_file)
    dsn = values.get("DR_SUPPORT_DATABASE_URL", "")
    parts = urlsplit(dsn)
    require(parts.scheme in {"postgresql", "postgres"} and parts.hostname == "127.0.0.1"
            and str(parts.port) == values.get("DR_SUPPORT_POSTGRES_PORT"), "LOOPBACK_PROJECT_OWNED_DATABASE_ONLY")
    # Same order as the launcher and PostgresSettings: process env, .env, then the default.
    dotenv = read_env(checkout / ".env") if (checkout / ".env").is_file() else {}
    schema = (os.environ.get("DR_SUPPORT_DATABASE_SCHEMA") or dotenv.get("DR_SUPPORT_DATABASE_SCHEMA")
              or "dr_support").strip()
    return dsn, schema, state


def runtime_dsn(owner_dsn: str, password: str) -> str:
    parts = urlsplit(owner_dsn)
    return f"{parts.scheme}://{ROLE}:{quote(password, safe='')}@{parts.hostname}:{parts.port}{parts.path}"


def plan(connection, schema: str) -> dict:
    from psycopg import sql
    role = connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,)).fetchone()
    tables = {row[0] for row in connection.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema=%s", (schema,))}
    require(set(DML_TABLES + READ_TABLES) <= tables, "APPLICATION_TABLES_MISSING_RUN_MIGRATIONS_FIRST")
    sequences = [row[0] for row in connection.execute(
        "SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema=%s", (schema,))]
    database = connection.execute("SELECT current_database()").fetchone()[0]
    statements = [
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(database), sql.Identifier(ROLE)),
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(ROLE)),
        *(sql.SQL("GRANT SELECT ON {}.{} TO {}").format(sql.Identifier(schema), sql.Identifier(table),
                                                      sql.Identifier(ROLE)) for table in READ_TABLES),
        *(sql.SQL("GRANT " + DML_PRIVILEGES + " ON {}.{} TO {}").format(
            sql.Identifier(schema), sql.Identifier(table), sql.Identifier(ROLE)) for table in DML_TABLES),
        sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT " + DML_PRIVILEGES + " ON TABLES TO {}").format(
            sql.Identifier(schema), sql.Identifier(ROLE)),
        *(sql.SQL("GRANT USAGE, SELECT ON SEQUENCE {}.{} TO {}").format(
            sql.Identifier(schema), sql.Identifier(name), sql.Identifier(ROLE)) for name in sequences),
    ]
    return {"role_exists": role is not None, "database": database, "schema": schema,
            "grants": [statement.as_string(connection) for statement in statements], "_statements": statements}


def verify_runtime(dsn: str, schema: str) -> dict:
    import psycopg
    from psycopg import sql
    with psycopg.connect(dsn, connect_timeout=10) as connection:
        flags = connection.execute(
            "SELECT current_user, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls FROM pg_roles "
            "WHERE rolname=current_user").fetchone()
        connection.execute(sql.SQL("SELECT count(*) FROM {}.review_cases").format(sql.Identifier(schema)))
        try:
            connection.execute(sql.SQL("CREATE TABLE {}.dr_runtime_ddl_probe (x int)").format(sql.Identifier(schema)))
            ddl_denied = False
        except psycopg.errors.InsufficientPrivilege:
            ddl_denied = True
        connection.rollback()
    require(flags[0] == ROLE and not any(flags[1:]) and ddl_denied, "RUNTIME_ROLE_NOT_LEAST_PRIVILEGE")
    return {"login": True, "superuser": flags[1], "createdb": flags[2], "createrole": flags[3],
            "bypassrls": flags[4], "can_read_cases": True, "ddl_denied": ddl_denied}


def main(argv=None) -> int:
    import psycopg
    from psycopg import sql
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkout", default=str(REPO_ROOT))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    owner_dsn, schema, state = owner_settings(Path(args.checkout))
    runtime_file = state / "postgres-runtime.env"
    with psycopg.connect(owner_dsn, connect_timeout=10) as connection:
        planned = plan(connection, schema)
        report = {key: value for key, value in planned.items() if not key.startswith("_")}
        report["runtime_file_exists"] = runtime_file.exists()
        if not args.apply:
            print(json.dumps({"mode": "DRY_RUN", **report}, indent=1))
            return 0
        require(not planned["role_exists"] and not runtime_file.exists(), "RUNTIME_ROLE_OR_FILE_ALREADY_EXISTS")
        password = secrets.token_urlsafe(32)
        dsn = runtime_dsn(owner_dsn, password)
        # Claim the file first so a lost password can never leave an unusable role behind.
        with runtime_file.open("x", encoding="ascii") as stream:
            stream.write(f"DR_SUPPORT_DATABASE_URL={dsn}\nDR_SUPPORT_DATABASE_MIGRATION_MODE=verify\n")
        hashed = connection.pgconn.encrypt_password(password.encode(), ROLE.encode(), b"scram-sha-256").decode()
        # End the read-only planning transaction so the block below is a real
        # top-level transaction that commits before the new login is tested.
        connection.commit()
        try:
            with connection.transaction():
                connection.execute(sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(sql.Identifier(ROLE), sql.Literal(hashed)))
                for statement in planned["_statements"]:
                    connection.execute(statement)
            verified = verify_runtime(dsn, schema)
        except Exception:
            # Undo only what this run created.
            connection.rollback()
            with connection.transaction():
                if connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,)).fetchone():
                    connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(ROLE)))
                    connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(ROLE)))
            runtime_file.unlink(missing_ok=True)
            raise
    print(json.dumps({"mode": "APPLIED", **report, "verified": verified,
                      "runtime_file": str(runtime_file.relative_to(Path(args.checkout)))}, indent=1))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    try:
        raise SystemExit(main())
    except RuntimeRoleError as error:
        print(json.dumps({"status": "BLOCKED", "code": str(error)}))
        raise SystemExit(2)
