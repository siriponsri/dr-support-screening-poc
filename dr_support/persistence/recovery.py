"""Explicit, non-destructive PostgreSQL/image recovery for operator-owned targets.

No command creates/drops a database, starts a service, or removes partial output.
Connection material is accepted only through the existing server environment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from .config import PostgresSettings
from .database import PostgresDatabase
from .migrations import SchemaMigrator

BUNDLE_VERSION = "dr-support-recovery.v1"
RESTORE_URL_ENV = "DR_SUPPORT_RESTORE_DATABASE_URL"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".dcm", ".dicom"}
_HASH = re.compile(r"^[0-9a-f]{64}$")
_PG_ENV = {
    "host": "PGHOST", "hostaddr": "PGHOSTADDR", "port": "PGPORT",
    "dbname": "PGDATABASE", "user": "PGUSER", "password": "PGPASSWORD",
    "passfile": "PGPASSFILE", "service": "PGSERVICE", "sslmode": "PGSSLMODE",
    "sslcert": "PGSSLCERT", "sslkey": "PGSSLKEY", "sslrootcert": "PGSSLROOTCERT",
    "sslcrl": "PGSSLCRL", "sslcrldir": "PGSSLCRLDIR",
    "sslpassword": "PGSSLPASSWORD", "connect_timeout": "PGCONNECT_TIMEOUT",
    "channel_binding": "PGCHANNELBINDING", "options": "PGOPTIONS",
    "application_name": "PGAPPNAME", "target_session_attrs": "PGTARGETSESSIONATTRS",
}


class RecoveryError(RuntimeError):
    """A safety or verification gate failed; partial files must be preserved."""


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path(value: str | Path, *, exists: bool = False) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise RecoveryError("Use an absolute path without parent traversal")
    # Check before resolve: redirected ancestors must not be followed silently.
    for candidate in reversed((path, *path.parents)):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RecoveryError("Redirected paths are not allowed for recovery")
    if exists and not path.exists():
        raise RecoveryError("A required recovery path is missing")
    return path.resolve()


def _new_directory(value: str | Path, *protected: Path) -> Path:
    path = _path(value)
    if any((parent / ".git").exists() for parent in path.parents):
        raise RecoveryError("Store private recovery output outside source checkouts")
    if path.exists():
        raise RecoveryError("Recovery destination already exists; choose a new directory")
    for other in protected:
        if path.is_relative_to(other) or other.is_relative_to(path):
            raise RecoveryError("Recovery destinations must not overlap source or bundle paths")
    if not path.parent.is_dir():
        raise RecoveryError("Create the approved destination parent directory first")
    return path


def _inventory(root: Path) -> list[dict]:
    if not root.is_dir():
        raise RecoveryError("The approved original-image root must be a directory")
    files = []
    for directory, folders, names in os.walk(root, followlinks=False):
        for name in folders:
            _path(Path(directory) / name, exists=True)
        for name in sorted(names):
            source = _path(Path(directory) / name, exists=True)
            if source.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            if not source.is_file():
                raise RecoveryError("An original image is not a regular file")
            files.append({"path": source.relative_to(root).as_posix(),
                          "size": source.stat().st_size, "sha256": _file_hash(source)})
    return sorted(files, key=lambda item: item["path"])


def _migrations(connection, database: PostgresDatabase) -> list[dict]:
    rows = connection.execute(sql.SQL(
        "SELECT version, name, checksum FROM {}.schema_migrations ORDER BY version"
    ).format(sql.Identifier(database.settings.schema))).fetchall()
    actual = [{"version": version, "name": name, "checksum": checksum}
              for version, name, checksum in rows]
    expected = [{"version": migration.version, "name": migration.name,
                 "checksum": migration.checksum}
                for migration in SchemaMigrator(database).migrations]
    if actual != expected:
        raise RecoveryError("Migration history is incomplete or incompatible with this release")
    return actual


@contextmanager
def _snapshot(database: PostgresDatabase, *, export: bool = False):
    """Hold one read-only repeatable-read snapshot, also usable by pg_dump."""
    with database.session(autocommit=False) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            identity = connection.execute(
                "SELECT current_database(), inet_server_addr()::text, inet_server_port()"
            ).fetchone()
            configured = conninfo_to_dict(database.settings.dsn)["dbname"]
            if identity[0] != configured:
                raise RecoveryError("Connected database does not match the configured database")
            migrations = _migrations(connection, database)
            schema = sql.Identifier(database.settings.schema)
            workspaces = connection.execute(sql.SQL(
                "SELECT workspace_id, revision, input_folder, output_folder "
                "FROM {}.workspaces ORDER BY workspace_id"
            ).format(schema)).fetchall()
            rows = connection.execute(sql.SQL(
                "SELECT workspace_id, case_id, revision, payload FROM {}.review_cases "
                "ORDER BY workspace_id, case_id"
            ).format(schema)).fetchall()
            cases = []
            for workspace_id, case_id, revision, payload in rows:
                if (not isinstance(payload, dict) or payload.get("image_id") != case_id
                        or type(revision) is not int or type(payload.get("revision")) is not int
                        or payload.get("revision") != revision):
                    raise RecoveryError("A stored case has inconsistent identity or revision")
                admission = payload.get("admission") or {}
                source_hash = admission.get("source_sha256")
                if not isinstance(source_hash, str) or not _HASH.fullmatch(source_hash):
                    raise RecoveryError("Every backed-up case requires an admitted original-image hash")
                cases.append({"workspace_id": workspace_id, "case_id": case_id,
                              "revision": revision, "payload_sha256": _digest(payload),
                              "source_sha256": source_hash})
            snapshot_id = (connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
                           if export else None)
            yield {"source_database": {"database": identity[0], "server_address": identity[1],
                                       "server_port": identity[2]},
                   "schema": database.settings.schema, "migrations": migrations,
                   "workspaces": [{"workspace_id": row[0], "revision": row[1],
                                   "input_folder": row[2], "output_folder": row[3]}
                                  for row in workspaces],
                   "cases": cases}, snapshot_id


def _image_plan(state: dict, root: Path) -> list[dict]:
    inventory = _inventory(root)
    names = [_relative(item["path"]).as_posix().casefold() for item in inventory]
    if len(names) != len(set(names)):
        raise RecoveryError("Original-image inventory has a destination path collision")
    hashes = {item["sha256"] for item in inventory}
    if any(case["source_sha256"] not in hashes for case in state["cases"]):
        raise RecoveryError("An admitted original-image hash is missing from the approved image root")
    for workspace in state["workspaces"]:
        folder = workspace["input_folder"]
        if folder:
            path = _path(folder, exists=True)
            if not path.is_relative_to(root):
                raise RecoveryError("All workspace input folders must be inside the approved image root")
            workspace["input_relative"] = path.relative_to(root).as_posix()
        else:
            workspace["input_relative"] = None
    return inventory


def _pg_environment(settings: PostgresSettings) -> dict[str, str]:
    parameters = conninfo_to_dict(settings.dsn)
    if set(parameters) - set(_PG_ENV):
        raise RecoveryError("This recovery tool does not support a configured connection option")
    result = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    result.update({_PG_ENV[key]: value for key, value in parameters.items()})
    result["PGCONNECT_TIMEOUT"] = str(settings.connect_timeout_seconds)
    result["PGAPPNAME"] = "dr-support-recovery"
    return result


def _run(command: list[str], settings: PostgresSettings, *, output=None,
         runner=subprocess.run) -> None:
    try:
        result = runner(command, env=_pg_environment(settings), stdin=subprocess.DEVNULL,
                        stdout=output if output is not None else subprocess.DEVNULL,
                        stderr=subprocess.PIPE, timeout=1800, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise RecoveryError("PostgreSQL recovery utility could not finish; partial output is retained") from error
    if result.returncode != 0:
        # PostgreSQL stderr can echo a DSN/password; never include it in errors.
        raise RecoveryError("PostgreSQL recovery utility failed; partial output is retained")


def _write_json(path: Path, value: dict) -> None:
    with path.open("xb") as stream:
        stream.write(_json_bytes(value))


def backup(database: PostgresDatabase, *, image_root: str | Path,
           destination: str | Path, release: str, apply: bool = False,
           pg_dump: str = "pg_dump", runner=subprocess.run) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", release):
        raise RecoveryError("Supply the exact release version or commit identity")
    if database.settings.schema == "public":
        raise RecoveryError("Recovery requires a dedicated application schema")
    root = _path(image_root, exists=True)
    target = _new_directory(destination, root)
    repository = Path(__file__).resolve().parents[2]
    if target.is_relative_to(repository):
        raise RecoveryError("Store private backups outside the source checkout")
    with _snapshot(database, export=apply) as (state, snapshot_id):
        inventory = _image_plan(state, root)
        report = {"status": "PLAN_ONLY", "action": "backup", "schema": state["schema"],
                  "workspace_count": len(state["workspaces"]), "case_count": len(state["cases"]),
                  "image_count": len(inventory), "image_bytes": sum(x["size"] for x in inventory)}
        if not apply:
            return report
        target.mkdir(exist_ok=False)
        dump = target / "database.dump"
        with dump.open("xb") as output:
            _run([pg_dump, "--no-password", "--format=custom", "--no-owner", "--no-privileges",
                  "--lock-wait-timeout=10s", f"--schema={state['schema']}",
                  f"--snapshot={snapshot_id}"], database.settings, output=output, runner=runner)
        with dump.open("rb") as stream:
            header = stream.read(5)
        if header != b"PGDMP":
            raise RecoveryError("The database dump is not a PostgreSQL custom archive")
        originals = target / "originals"
        originals.mkdir()
        for item in inventory:
            source = _path(root / item["path"], exists=True)
            copied = originals / item["path"]
            copied.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as incoming, copied.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)
            if (copied.stat().st_size != item["size"] or source.stat().st_size != item["size"]
                    or _file_hash(copied) != item["sha256"] or _file_hash(source) != item["sha256"]):
                raise RecoveryError("Original-image bytes changed during backup; partial output retained")
        manifest = {"version": BUNDLE_VERSION, "release": release, **state,
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "images": inventory, "dump_sha256": _file_hash(dump),
                    "scope": "dedicated_schema_and_originals; historical_export_archives_not_included"}
        _write_json(target / "manifest.json", manifest)
        _write_json(target / "receipt.json", {"version": BUNDLE_VERSION, "status": "BACKUP_COMPLETE",
                    "manifest_sha256": _digest(manifest)})
    verify_bundle(target)
    return {**report, "status": "BACKUP_VERIFIED", "inference_requests": 0}


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(_path(path, exists=True).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RecoveryError("Recovery metadata is missing or invalid") from error
    if not isinstance(value, dict):
        raise RecoveryError("Recovery metadata must be an object")
    return value


def _relative(value: Any) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise RecoveryError("An image inventory path is invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise RecoveryError("An image inventory path is invalid")
    return path


def verify_bundle(bundle: str | Path) -> dict:
    root = _path(bundle, exists=True)
    manifest, receipt = _load_json(root / "manifest.json"), _load_json(root / "receipt.json")
    if (manifest.get("version") != BUNDLE_VERSION or receipt.get("version") != BUNDLE_VERSION
            or receipt.get("status") != "BACKUP_COMPLETE"
            or receipt.get("manifest_sha256") != _digest(manifest)):
        raise RecoveryError("Backup completion receipt does not match the manifest")
    try:
        settings = PostgresSettings(dsn="dbname=recovery_verify", schema=manifest["schema"])
        expected = [{"version": item.version, "name": item.name, "checksum": item.checksum}
                    for item in SchemaMigrator(PostgresDatabase(settings)).migrations]
        if manifest["migrations"] != expected or settings.schema == "public":
            raise RecoveryError("Backup migration history is incompatible with this release")
        workspaces, cases = manifest["workspaces"], manifest["cases"]
        if not isinstance(workspaces, list) or not isinstance(cases, list):
            raise RecoveryError("Backup workspace/case inventory is invalid")
        workspace_ids = set()
        for workspace in workspaces:
            workspace_id, revision = workspace["workspace_id"], workspace["revision"]
            if (not isinstance(workspace_id, str) or not workspace_id.strip()
                    or workspace_id in workspace_ids or type(revision) is not int or revision < 0):
                raise RecoveryError("Backup workspace identities or revisions are invalid")
            workspace_ids.add(workspace_id)
            for key in ("input_folder", "output_folder"):
                if workspace[key] is not None and not isinstance(workspace[key], str):
                    raise RecoveryError("Backup workspace configuration is invalid")
            relative = workspace["input_relative"]
            if relative not in {None, "."}:
                _relative(relative)
            if bool(workspace["input_folder"]) != (relative is not None):
                raise RecoveryError("Backup workspace image mapping is incomplete")
        case_keys = set()
        for case in cases:
            case_id, revision = case["case_id"], case["revision"]
            key = (case["workspace_id"], case_id)
            if (case["workspace_id"] not in workspace_ids or not isinstance(case_id, str)
                    or not case_id.strip() or key in case_keys
                    or type(revision) is not int or revision < 0
                    or not _HASH.fullmatch(case["payload_sha256"])
                    or not _HASH.fullmatch(case["source_sha256"])):
                raise RecoveryError("Backup case identities, revisions or hashes are invalid")
            case_keys.add(key)
        images = manifest["images"]
        if not isinstance(images, list):
            raise RecoveryError("Backup image inventory is invalid")
        paths = set()
        for item in images:
            relative = _relative(item["path"])
            if relative.as_posix().casefold() in paths:
                raise RecoveryError("Backup image inventory contains a path collision")
            paths.add(relative.as_posix().casefold())
            image = _path(root / "originals" / relative, exists=True)
            if (not _HASH.fullmatch(item["sha256"]) or image.stat().st_size != item["size"]
                    or _file_hash(image) != item["sha256"]):
                raise RecoveryError("Backup original-image hash or size does not match")
        hashes = {item["sha256"] for item in images}
        if any(case["source_sha256"] not in hashes for case in manifest["cases"]):
            raise RecoveryError("Backup is missing an admitted original-image hash")
        source_name = manifest["source_database"]["database"]
        if not isinstance(source_name, str) or not source_name:
            raise RecoveryError("Backup source identity is missing")
        dump = _path(root / "database.dump", exists=True)
        with dump.open("rb") as stream:
            header = stream.read(5)
        if header != b"PGDMP" or _file_hash(dump) != manifest["dump_sha256"]:
            raise RecoveryError("Backup database dump hash does not match")
    except (KeyError, TypeError, ValueError) as error:
        raise RecoveryError("Backup inventory is invalid or incomplete") from error
    return manifest


def _empty_target(database: PostgresDatabase, expected_name: str, source_name: str) -> None:
    actual_name = conninfo_to_dict(database.settings.dsn)["dbname"]
    if (expected_name != actual_name or "test" not in re.split(r"[^a-z0-9]+", expected_name.lower())
            or source_name.casefold() == actual_name.casefold()):
        raise RecoveryError("Restore requires an exact, separate, visibly test-only database name")
    with database.session(autocommit=False) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            if connection.execute("SELECT current_database()").fetchone()[0] != expected_name:
                raise RecoveryError("Connected restore database does not match the approved target")
            occupied = connection.execute("""
                SELECT nspname FROM pg_namespace
                WHERE nspname !~ '^pg_' AND nspname NOT IN ('public', 'information_schema')
                UNION ALL
                SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public'
                UNION ALL
                SELECT n.nspname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='public'
                UNION ALL
                SELECT n.nspname FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                WHERE n.nspname='public'
                LIMIT 1
            """).fetchone()
            if occupied:
                raise RecoveryError("Restore target is occupied; nothing will be overwritten or removed")


def restore(database: PostgresDatabase, *, bundle: str | Path, expected_database: str,
            image_destination: str | Path, output_destination: str | Path,
            apply: bool = False, target_quiesced: bool = False,
            pg_restore: str = "pg_restore", runner=subprocess.run) -> dict:
    root = _path(bundle, exists=True)
    manifest = verify_bundle(root)
    if database.settings.schema != manifest["schema"]:
        raise RecoveryError("Restore schema does not match the explicitly configured target schema")
    images = _new_directory(image_destination, root)
    outputs = _new_directory(output_destination, root, images)
    _empty_target(database, expected_database, manifest["source_database"]["database"])
    report = {"status": "PLAN_ONLY", "action": "restore", "schema": manifest["schema"],
              "workspace_count": len(manifest["workspaces"]), "case_count": len(manifest["cases"]),
              "image_count": len(manifest["images"]), "paths_remapped_in_isolated_target": True}
    if not apply:
        return report
    if not target_quiesced:
        raise RecoveryError("Confirm the isolated target has no concurrent writers before restore")
    images.mkdir(exist_ok=False)
    outputs.mkdir(exist_ok=False)
    for item in manifest["images"]:
        relative = _relative(item["path"])
        source = _path(root / "originals" / relative, exists=True)
        target = images / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        if target.stat().st_size != item["size"] or _file_hash(target) != item["sha256"]:
            raise RecoveryError("Restored original-image hash does not match; partial output retained")
    # Recheck after file copying, immediately before the first DB mutation.
    _empty_target(database, expected_database, manifest["source_database"]["database"])
    _run([pg_restore, "--no-password", "--exit-on-error", "--single-transaction",
          "--no-owner", "--no-privileges", str(root / "database.dump")],
         database.settings, runner=runner)
    expected_workspaces = [dict(item) for item in manifest["workspaces"]]
    with database.transaction() as connection:
        for workspace in expected_workspaces:
            relative = workspace["input_relative"]
            if relative is None:
                continue
            input_folder = str(images / relative)
            output_folder = outputs / hashlib.sha256(workspace["workspace_id"].encode()).hexdigest()[:16]
            output_folder.mkdir(exist_ok=False)
            connection.execute(sql.SQL(
                "UPDATE {}.workspaces SET input_folder=%s, output_folder=%s WHERE workspace_id=%s"
            ).format(sql.Identifier(manifest["schema"])),
                (input_folder, str(output_folder), workspace["workspace_id"]))
            workspace["input_folder"], workspace["output_folder"] = input_folder, str(output_folder)
    with _snapshot(database) as (state, _):
        if state["cases"] != manifest["cases"]:
            raise RecoveryError("Restored case identities, revisions or payload hashes differ")
        expected = [{key: value for key, value in item.items() if key != "input_relative"}
                    for item in expected_workspaces]
        if state["workspaces"] != expected:
            raise RecoveryError("Restored workspace identities, revisions or mapped paths differ")
    _write_json(outputs / "recovery-receipt.json", {
        "version": BUNDLE_VERSION, "status": "RESTORE_DATA_VERIFIED",
        "manifest_sha256": _digest(manifest), "release": manifest["release"],
        "application_reopen_export": "NOT_RUN", "inference": "NOT_RUN"})
    return {**report, "status": "RESTORE_DATA_VERIFIED", "application_reopen_export": "NOT_RUN"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "backup"):
        command = commands.add_parser(name)
        command.add_argument("--image-root", required=True)
        command.add_argument("--destination", required=True)
        command.add_argument("--release", required=True)
        if name == "backup":
            command.add_argument("--apply", action="store_true")
            command.add_argument("--pg-dump", default="pg_dump")
    command = commands.add_parser("verify")
    command.add_argument("--bundle", required=True)
    command = commands.add_parser("restore")
    command.add_argument("--bundle", required=True)
    command.add_argument("--expected-target-database", required=True)
    command.add_argument("--image-destination", required=True)
    command.add_argument("--output-destination", required=True)
    command.add_argument("--apply", action="store_true")
    command.add_argument("--target-quiesced", action="store_true")
    command.add_argument("--pg-restore", default="pg_restore")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            manifest = verify_bundle(args.bundle)
            result = {"status": "BUNDLE_VERIFIED", "live_restore": "NOT_RUN",
                      "image_count": len(manifest["images"])}
        else:
            settings = PostgresSettings.from_env(
                url_variable=RESTORE_URL_ENV if args.command == "restore" else "DR_SUPPORT_DATABASE_URL")
            database = PostgresDatabase(settings)
            if args.command == "restore":
                result = restore(database, bundle=args.bundle,
                                 expected_database=args.expected_target_database,
                                 image_destination=args.image_destination,
                                 output_destination=args.output_destination, apply=args.apply,
                                 target_quiesced=args.target_quiesced, pg_restore=args.pg_restore)
            else:
                result = backup(database, image_root=args.image_root, destination=args.destination,
                                release=args.release, apply=getattr(args, "apply", False),
                                pg_dump=getattr(args, "pg_dump", "pg_dump"))
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        # Database, file-system and client exceptions can include secret-bearing
        # connection strings or patient paths. Only a fixed diagnostic is public.
        detail = (str(error) if isinstance(error, RecoveryError) else
                  "Check private connection configuration, utilities and approved path permissions")
        print(json.dumps({"status": "BLOCKED", "detail": detail,
                          "partial_output": "RETAINED_IF_CREATED", "automatic_retry": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
