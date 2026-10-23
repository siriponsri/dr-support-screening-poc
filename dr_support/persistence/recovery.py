"""Explicit, non-destructive PostgreSQL/image recovery for operator-owned targets.

No command creates/drops a database, starts a service, or removes partial output.
Connection material is accepted only through the existing server environment.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from ..services.admission import scan_input_folder
from ..services import admission as hospital_admission
from ..services import source_policy
from .config import PostgresSettings
from .cases import PostgresCaseStore
from .database import PostgresDatabase
from .migrations import SchemaMigrator

BUNDLE_VERSION = "dr-support-recovery.v2"
HOSPITAL_BUNDLE_VERSION = "dr-support-recovery.v3"
SOURCE_MAP_VERSION = "dr-support-hospital-source-map.v1"
RESTORE_MAP_VERSION = "dr-support-hospital-restore-map.v1"
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


def _reject_unqualified_entry_guard(connection, schema: str) -> None:
    """App-schema dumps cannot reconstruct unqualified sidecar write guards."""
    present = connection.execute("""SELECT 1 AS recovery_unqualified_guard FROM pg_namespace
        WHERE nspname='dr_support_entry_guard'
        UNION ALL
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relname='entry_fence' AND n.nspname !~ '^pg_'
        UNION ALL
        SELECT 1 FROM pg_trigger t
        JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_proc p ON p.oid=t.tgfoid
        JOIN pg_namespace f ON f.oid=p.pronamespace
        WHERE n.nspname=%s AND c.relname IN
            ('workspaces','review_cases','legacy_migration_receipts')
          AND NOT t.tgisinternal
          AND (t.tgname='m1_entry_fence'
               OR (p.pronamespace<>c.relnamespace AND f.nspname !~ '^pg_'))
        LIMIT 1
    """, (schema,)).fetchone()
    if present:
        raise RecoveryError("M1 guard-aware recovery is NOT_QUALIFIED; app-schema-only recovery refuses entry-fence or external guard dependencies")


@contextmanager
def _snapshot(database: PostgresDatabase, *, export: bool = False, hospital: bool = False):
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
            _reject_unqualified_entry_guard(connection, database.settings.schema)
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
                              "source_sha256": source_hash,
                              "source_origin": admission.get("source_origin"),
                              "source_reference": admission.get("source_reference"),
                              "source_aliases": (admission.get("integrity") or {}).get("aliases") or []})
                if hospital:
                    cases[-1]["hospital_admission"] = admission
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
    for workspace in state["workspaces"]:
        folder = workspace["input_folder"]
        if folder:
            path = _path(folder, exists=True)
            if not path.is_relative_to(root):
                raise RecoveryError("All workspace input folders must be inside the approved image root")
            workspace["input_relative"] = path.relative_to(root).as_posix()
        else:
            workspace["input_relative"] = None
    bindings = _workspace_case_bindings(state, root)
    by_path = {item["path"]: item["sha256"] for item in inventory}
    for case, paths in zip(state["cases"], bindings, strict=True):
        if any(by_path.get(path) != case["source_sha256"] for path in paths):
            raise RecoveryError("A scan-visible admitted original is missing from the image inventory")
        case["image_paths"] = paths
    return inventory


def _workspace_case_bindings(state: dict, root: Path) -> list[list[str]]:
    """Prove ordinary admission identity using the same top-level scanner as the app.

    Hospital/demo/runtime-root lanes cannot be reconstructed by changing catalog
    folders alone and are explicitly outside this increment. No admission or
    historical provenance is rewritten to make a source fit this lane.
    """
    workspaces = {row["workspace_id"]: row for row in state["workspaces"]}
    scans = {}
    result = []
    for case in state["cases"]:
        workspace = workspaces.get(case["workspace_id"])
        if workspace is None or workspace.get("input_relative") is None:
            raise RecoveryError("Every persisted case requires its own workspace input folder")
        if case.get("source_origin") != "WORKSPACE" or case["case_id"] != case["source_sha256"]:
            raise RecoveryError("Recovery supports only ordinary workspace scanner identities; hospital, demo and runtime-root cases are blocked")
        reference = case.get("source_reference")
        aliases = case.get("source_aliases")
        if not isinstance(aliases, list):
            raise RecoveryError("Ordinary workspace source aliases are invalid")
        references = [reference, *(alias.get("source_reference") if isinstance(alias, dict) else None
                                    for alias in aliases)]
        for value in references:
            if not isinstance(value, str) or not value.startswith("WORKSPACE_INPUT/"):
                raise RecoveryError("Recovery requires preserved ordinary WORKSPACE_INPUT references")
            if len(_relative(value.removeprefix("WORKSPACE_INPUT/")).parts) != 1:
                raise RecoveryError("Workspace recovery requires top-level scan-visible source references")
        relative = workspace["input_relative"]
        folder = _path(root / relative, exists=True)
        if not folder.is_relative_to(root):
            raise RecoveryError("Workspace image mapping escapes the approved restored image root")
        key = workspace["workspace_id"]
        if key not in scans:
            scans[key] = scan_input_folder(folder)
        scan = scans[key]
        image, record = scan.images.get(case["case_id"]), scan.records.get(case["case_id"])
        if image is None or record is None or image.sha256 != case["source_sha256"]:
            raise RecoveryError("A persisted case cannot be reopened by its own top-level workspace scanner")
        visible = {alias["source_reference"] for alias in (record.get("integrity") or {}).get("aliases", [])}
        matched = sorted(set(references) & visible)
        if not matched:
            raise RecoveryError("Stored workspace references do not match a scan-visible original")
        result.append(sorted((folder / value.removeprefix("WORKSPACE_INPUT/")).relative_to(root).as_posix()
                             for value in matched))
    return result


def _isolated_restore_environment(environ=None, *, hospital: bool = False) -> None:
    """Refuse inherited source selectors; never silently clear or rewrite them."""
    source = os.environ if environ is None else environ
    forbidden = ("DR_DEMO_FOLDER", "DR_SUPPORT_DATABASE_URL", "DR_SUPPORT_WORKSPACE_ID")
    if (any(str(source.get(key, "")).strip() for key in forbidden)
            or any(str(value).strip() for key, value in source.items()
                   if key.startswith(("DR_SUPPORT_AUTHORIZED_HOSPITAL", "DR_SUPPORT_HOSPITAL_"))
                   and not (hospital and key == source_policy.HOSPITAL_LINKAGE_KEY_ENV))
            or str(source.get("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "")).strip() not in {"", "0"}):
        raise RecoveryError("Restore requires an isolated target environment without source database, workspace, hospital-root or demo overrides; the source configuration was not changed")


def validate_restored_app_environment(settings: PostgresSettings, *, expected_database: str, environ=None,
                                      workspace_id: str | None = None,
                                      bundle: str | Path | None = None,
                                      expected_manifest_sha256: str | None = None,
                                      hospital_source_map: str | Path | None = None,
                                      expected_hospital_source_map_sha256: str | None = None,
                                      hospital_restore_map: str | Path | None = None,
                                      expected_hospital_restore_map_sha256: str | None = None) -> dict:
    """Preflight for a separately launched, fixtures-disabled restore acceptance app.

    The caller must construct create_app(include_samples=False,
    include_demo_fixtures=False) after this check and must not reload a source
    .env afterward. This check alone never establishes application acceptance.
    """
    source = dict(os.environ if environ is None else environ)
    dsn = source.pop("DR_SUPPORT_DATABASE_URL", "")
    if not dsn:
        raise RecoveryError("A restored acceptance app requires its explicit target database configuration")
    expected, actual = conninfo_to_dict(settings.dsn), conninfo_to_dict(dsn)
    if expected.get("service") or actual.get("service") or any(
        str(source.get(key, "")).strip() for key in (
            "PGSERVICE", "PGSERVICEFILE", "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE",
        )
    ):
        raise RecoveryError("Restored acceptance requires an explicit target without inherited libpq endpoint or service overrides")
    if (expected.get("dbname") != expected_database
            or "test" not in re.split(r"[^a-z0-9]+", expected_database.lower())):
        raise RecoveryError("Restored acceptance app must select the exact independently recorded test target")
    identity = lambda value: (value.get("dbname"), value.get("host"), value.get("hostaddr"), value.get("port", "5432"))
    if identity(actual) != identity(expected):
        raise RecoveryError("Restored acceptance app configuration does not select the restored target")
    hospital = hospital_source_map is not None
    if hospital:
        if environ is not None:
            raise RecoveryError("Hospital acceptance must validate its actual isolated process environment")
        mapping, source_pin, _ = _source_map(hospital_source_map, expected_hospital_source_map_sha256)
        if bundle is None or not isinstance(expected_manifest_sha256, str) or not _HASH.fullmatch(expected_manifest_sha256):
            raise RecoveryError("Hospital acceptance requires the independently retained backup and map pins")
        root = _path(bundle, exists=True)
        restored, _, _ = _restore_map(hospital_restore_map, expected_hospital_restore_map_sha256,
                                     mapping, source_pin, expected_manifest_sha256,
                                     bundle=root, database=expected_database)
        if workspace_id != restored["workspace_id"]:
            raise RecoveryError("Hospital acceptance must explicitly select the independently pinned restored workspace")
        expected_roots = {row["modality"]: row["path"] for row in restored["roots"]}
        try:
            configured = json.loads(source.get("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS", "{}"))
            readers = json.loads(source.get(source_policy.HOSPITAL_WINDOWS_READERS_ENV) or "{}")
        except (TypeError, ValueError) as error:
            raise RecoveryError("Hospital acceptance root configuration is invalid") from error
        if (configured != expected_roots or readers != _reader_bindings(restored["roots"])
                or source.get("DR_SUPPORT_HOSPITAL_SCOPE") != restored["scope"]
                or source.get("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL") != "1"):
            raise RecoveryError("Hospital acceptance must select only the independently approved restored roots")
        _source_binding_active(restored)
        for key in ("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS", source_policy.HOSPITAL_WINDOWS_READERS_ENV,
                    "DR_SUPPORT_HOSPITAL_SCOPE", "DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL"):
            source.pop(key, None)
        # The dedicated acceptance process must already carry this exact key;
        # never import configuration or change its environment on behalf of an app.
        if source.get(source_policy.HOSPITAL_LINKAGE_KEY_ENV) != os.environ.get(source_policy.HOSPITAL_LINKAGE_KEY_ENV):
            raise RecoveryError("Hospital acceptance must use the existing process linkage secret")
        _isolated_restore_environment(source, hospital=True)
        manifest = verify_bundle(root, expected_manifest_sha256=expected_manifest_sha256,
                                 hospital_source_map=hospital_source_map,
                                 expected_hospital_source_map_sha256=source_pin,
                                 hospital_restore_map=hospital_restore_map,
                                 expected_hospital_restore_map_sha256=expected_hospital_restore_map_sha256)
        if (manifest["version"] != HOSPITAL_BUNDLE_VERSION or manifest["schema"] != settings.schema
                or manifest["source_database"]["database"].casefold() == expected_database.casefold()):
            raise RecoveryError("Hospital acceptance must match the restored release schema")
        _hospital_layout(json.loads(_json_bytes(manifest)), restored["roots"], mapping, source_pin,
                         expected=manifest["source_layout"])
    else:
        if any(value is not None for value in (workspace_id, hospital_restore_map, expected_hospital_source_map_sha256,
                                               expected_hospital_restore_map_sha256, bundle, expected_manifest_sha256)):
            raise RecoveryError("Hospital acceptance requires the complete independently approved map set")
        _isolated_restore_environment(source)
    if (source.get("DR_SUPPORT_CASE_STORE") != "postgres"
            or source.get("DR_SUPPORT_DATABASE_SCHEMA") != settings.schema
            or source.get("APP_PROFILE") != "review" or source.get("MODEL_RUNTIME") != "remote"
            or any(source.get(key) for key in ("DR_SUPPORT_STATE", "DR_SUPPORT_WORKSPACE_CATALOG"))):
        raise RecoveryError("Use an isolated PostgreSQL review-app environment without legacy state/catalog overrides")
    if hospital and any(value for key, value in source.items()
                        if key.startswith(("MODEL_API", "CVAT_", "DR_SUPPORT_MODEL_API", "REMOTE_MODEL"))):
        raise RecoveryError("Recovery acceptance must have no model API or CVAT connection configured")
    report = {"status": "ENVIRONMENT_VERIFIED", "application_reopen_export": "NOT_RUN"}
    if hospital:
        report["workspace_id"] = restored["workspace_id"]
    return report


def validate_restored_app_selection(app, settings: PostgresSettings, **acceptance) -> dict:
    """Read-only v3 harness gate after fixtures-disabled app construction.

    Revalidate the independently pinned process configuration, then prove the
    constructed app actually selected that PostgreSQL store. This is still not
    original-image HTTP, clinician-state readback or export acceptance.
    """
    report = validate_restored_app_environment(settings, **acceptance)
    selected = report.get("workspace_id")
    state = app.state
    store = getattr(state, "store", None)
    if (selected is None or not isinstance(store, PostgresCaseStore)
            or getattr(state, "case_store_mode", None) != "postgres"
            or getattr(state, "workspace_id", None) != selected or store.workspace_id != selected):
        raise RecoveryError("The acceptance app did not select the independently pinned restored PostgreSQL workspace")
    expected, actual = conninfo_to_dict(settings.dsn), conninfo_to_dict(store.database.settings.dsn)
    identity = lambda value: (value.get("dbname"), value.get("host"), value.get("hostaddr"), value.get("port", "5432"))
    if (identity(expected) != identity(actual) or actual.get("service")
            or store.database.settings.schema != settings.schema):
        raise RecoveryError("The acceptance app store did not select the verified restored target")
    return {**report, "status": "APP_SELECTION_VERIFIED"}


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


def _approved_map(path, pin: str | None, version: str) -> tuple[dict, str, Path]:
    if path is None or not isinstance(pin, str) or not _HASH.fullmatch(pin):
        raise RecoveryError("Hospital recovery requires an independently approved map and exact file pin")
    filename = _path(path, exists=True)
    raw = filename.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin:
        raise RecoveryError("The hospital map does not match its independently approved file pin")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RecoveryError("Hospital maps must not contain duplicate keys")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, TypeError) as error:
        raise RecoveryError("The independently pinned hospital map is invalid") from error
    if not isinstance(value, dict) or value.get("version") != version:
        raise RecoveryError("The hospital map version is not supported")
    return value, pin, filename


def _map_path(value) -> Path:
    # Source paths in an approved map are audit/deny-list metadata during restore.
    # Lexical normalization must not inspect an original root on another machine.
    if not isinstance(value, str) or not value or not Path(value).is_absolute() or ".." in Path(value).parts:
        raise RecoveryError("Hospital maps require absolute non-traversing paths")
    return Path(os.path.abspath(value))


def _map_roots(value, *, source: bool) -> list[dict]:
    if not isinstance(value, list) or len(value) != 2:
        raise RecoveryError("Hospital recovery requires exactly the ordered UWF and CFP roots")
    result = []
    for row, root_id, modality in zip(value, ("uwf", "cfp"), ("UWF", "CFP"), strict=True):
        fields = {"root_id", "modality", "path", "read_only_sids"}
        if source:
            fields.add("candidate_inventory_sha256")
        if (not isinstance(row, dict) or set(row) != fields
                or row["root_id"] != root_id or row["modality"] != modality):
            raise RecoveryError("Hospital root fields or fixed modality order do not match the contract")
        readers = row["read_only_sids"]
        if (not isinstance(readers, list) or len(readers) > 1
                or any(not isinstance(sid, str) or re.fullmatch(r"S-1-5-21-(?:[0-9]+-){3}[0-9]+", sid) is None
                       for sid in readers)):
            raise RecoveryError("Hospital reader bindings must name an approved existing read-only SID")
        if source and row["candidate_inventory_sha256"] is not None and (
                not isinstance(row["candidate_inventory_sha256"], str)
                or not _HASH.fullmatch(row["candidate_inventory_sha256"])):
            raise RecoveryError("Hospital candidate snapshot pins must be SHA-256 or plan-only null")
        result.append({**row, "path": str(_map_path(row["path"]))})
    paths = [Path(row["path"]) for row in result]
    if paths[0].is_relative_to(paths[1]) or paths[1].is_relative_to(paths[0]):
        raise RecoveryError("Hospital roots must be distinct and disjoint")
    return result


def _source_map(path, pin, *, require_snapshot: bool = True) -> tuple[dict, str, Path]:
    value, digest, filename = _approved_map(path, pin, SOURCE_MAP_VERSION)
    if set(value) != {"version", "approval_id", "workspace_id", "scope", "backup_destination", "linkage_key_ref", "roots"}:
        raise RecoveryError("Hospital source-map fields do not match the frozen contract")
    _map_common(value)
    value["backup_destination"] = str(_map_path(value["backup_destination"]))
    value["roots"] = _map_roots(value["roots"], source=True)
    if require_snapshot and any(row["candidate_inventory_sha256"] is None for row in value["roots"]):
        raise RecoveryError("Applying hospital backup requires approved non-null candidate snapshot pins")
    return value, digest, filename


def _map_common(value: dict) -> None:
    if (not isinstance(value["approval_id"], str) or not value["approval_id"].strip()
            or not isinstance(value["workspace_id"], str) or not value["workspace_id"].strip()
            or value["scope"] != source_policy.PRIVATE_PROJECT_SCOPE
            or (value["linkage_key_ref"] is not None and (
                not isinstance(value["linkage_key_ref"], str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", value["linkage_key_ref"]) is None))):
        raise RecoveryError("Hospital map approval, workspace, scope or existing-secret reference is invalid")


def _reader_bindings(roots: list[dict]) -> dict:
    return {row["path"]: row["read_only_sids"] for row in roots if row["read_only_sids"]}


def _private_recovery_root(root: Path, roots: list[dict]) -> None:
    readers = tuple(sorted({sid for row in roots for sid in row["read_only_sids"]}))
    if not source_policy.private_hospital_root(root, read_only_sids=readers):
        raise RecoveryError("Hospital bundle or restored output failed the unchanged private-storage gate; partial output retained")


def _source_binding_active(mapping: dict) -> None:
    configured = [(str(path), modality) for path, modality in source_policy.authorized_hospital_roots()]
    expected = [(row["path"], row["modality"]) for row in mapping["roots"]]
    try:
        readers = json.loads(os.environ.get(source_policy.HOSPITAL_WINDOWS_READERS_ENV) or "{}")
    except ValueError as error:
        raise RecoveryError("The source hospital reader configuration is invalid") from error
    if (configured != expected or readers != _reader_bindings(mapping["roots"])
            or os.environ.get("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL") != "1"
            or os.environ.get("DR_SUPPORT_HOSPITAL_SCOPE") != mapping["scope"]
            or os.environ.get("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOT")
            or os.environ.get("DR_SUPPORT_AUTHORIZED_HOSPITAL_MODALITY")
            or os.environ.get("DR_DEMO_FOLDER")
            or any(not source_policy.hospital_ingest_enabled(Path(row["path"])) for row in mapping["roots"])):
        raise RecoveryError("The independently approved source map does not match active authorized private roots")


@contextmanager
def _hospital_binding(roots: list[dict]):
    """Scoped configuration in this dedicated recovery command, never the app."""
    values = {
        "DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS": json.dumps({row["modality"]: row["path"] for row in roots}),
        "DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL": "1",
        "DR_SUPPORT_HOSPITAL_SCOPE": source_policy.PRIVATE_PROJECT_SCOPE,
        source_policy.HOSPITAL_WINDOWS_READERS_ENV: json.dumps(_reader_bindings(roots)) if _reader_bindings(roots) else None,
        "DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOT": None,
        "DR_SUPPORT_AUTHORIZED_HOSPITAL_MODALITY": None,
    }
    before = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if any(not source_policy.hospital_ingest_enabled(Path(row["path"])) for row in roots):
            raise RecoveryError("Hospital recovery roots failed the unchanged privacy/authorization gates")
        yield
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _linkage_binding(key_ref, *, expected: dict | None = None) -> dict:
    key = source_policy.hospital_linkage_key()
    if key_ref is None:
        if key is not None:
            raise RecoveryError("The approved hospital map requires explicit linkage-key absence")
        result = {"state": "ABSENT", "key_ref": None, "challenge": None, "response": None}
    else:
        if key is None:
            raise RecoveryError("The approved existing hospital linkage secret is required")
        challenge = expected.get("challenge") if expected is not None else secrets.token_hex(32)
        if not isinstance(challenge, str) or not _HASH.fullmatch(challenge):
            raise RecoveryError("Hospital linkage challenge is invalid")
        # A domain-separated recovery MAC is metadata, never a patient record.
        response = hmac.new(key, b"DR_RECOVERY_V3\x00" + challenge.encode("ascii"), hashlib.sha256).hexdigest()
        result = {"state": "BOUND", "key_ref": key_ref, "challenge": challenge, "response": response}
    if expected is not None and not hmac.compare_digest(_digest(result), _digest(expected)):
        raise RecoveryError("Hospital recovery requires the same existing linkage secret and state")
    return result


def _hospital_candidates(roots: list[dict]) -> tuple[list[dict], list[dict]]:
    inventory, summaries = [], []
    for row in roots:
        root = _path(row["path"], exists=True)
        if not root.is_dir():
            raise RecoveryError("An approved hospital root is unavailable")
        candidates = []
        paths = sorted((path for path in root.iterdir() if path.is_file()
                        and path.suffix.lower() not in hospital_admission.ANCILLARY_WORKSPACE_EXTENSIONS),
                       key=lambda path: (path.name.casefold(), path.name))
        names = set()
        for path in paths:
            path = _path(path, exists=True)
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                raise RecoveryError("Unsupported hospital candidates must not be omitted or renumbered")
            name = _relative(path.name).as_posix()
            if name.casefold() in names:
                raise RecoveryError("Hospital candidate names collide on the restore filesystem")
            names.add(name.casefold())
            item = {"basename": name, "size": path.stat().st_size, "sha256": _file_hash(path)}
            candidates.append(item)
            inventory.append({"path": f"{row['root_id']}/{name}", "root_id": row["root_id"], **item})
        summaries.append({"root_id": row["root_id"], "modality": row["modality"],
                          "candidate_inventory_sha256": _digest(candidates), "candidate_count": len(candidates)})
    return inventory, summaries


def _scanner_projection(scan) -> list[dict]:
    fields = ("image_id", "source_sha256", "source_origin", "source_reference", "filename",
              "file_extension", "file_size_bytes", "source_format", "source_media_type", "source_dimensions",
              "retinal_modality", "retinal_modality_state", "retinal_modality_method", "trusted_patient_key",
              "trusted_laterality", "trusted_capture_sequence", "trusted_identity_method", "integrity_status", "integrity")
    return [{key: scan.records[case_id].get(key) for key in fields} for case_id in sorted(scan.records)]


def _hospital_layout(state: dict, roots: list[dict], mapping: dict, mapping_pin: str,
                     *, expected: dict | None = None, require_snapshot: bool = True) -> tuple[list[dict], dict]:
    with _hospital_binding(roots):
        inventory, summaries = _hospital_candidates(roots)
        scan = hospital_admission.scan_authorized_hospital_roots()
        if set(scan.records) != set(scan.images) or not scan.records:
            raise RecoveryError("All hospital recovery candidates must decode through the existing scanner")
        if set(scan.records) != {case["case_id"] for case in state["cases"]}:
            raise RecoveryError("Hospital scanner and persisted case identities must match the complete candidate set")
        linkage = _linkage_binding(mapping["linkage_key_ref"], expected=expected["linkage"] if expected else None)
    for actual, approved in zip(summaries, mapping["roots"], strict=True):
        digest = approved["candidate_inventory_sha256"]
        if digest is not None and digest != actual["candidate_inventory_sha256"]:
            raise RecoveryError("Hospital candidate inventory changed from the independently approved snapshot")
        if require_snapshot and digest is None:
            raise RecoveryError("Applying hospital backup requires approved candidate snapshot pins")
    identities = {row["workspace_id"]: row for row in state["workspaces"]}
    if mapping["workspace_id"] not in identities or any(
            row["input_folder"] and row["workspace_id"] != mapping["workspace_id"] for row in state["workspaces"]):
        raise RecoveryError("This hospital increment supports one catalogued hospital workspace only")
    for workspace in state["workspaces"]:
        workspace["input_relative"] = "." if workspace["workspace_id"] == mapping["workspace_id"] else None
    for case in state["cases"]:
        admission = case.get("hospital_admission")
        record = scan.records[case["case_id"]]
        if (case["workspace_id"] != mapping["workspace_id"] or case["source_origin"] != source_policy.HOSPITAL_ORIGIN
                or case["case_id"] != case["source_sha256"] or not isinstance(admission, dict)
                or admission.get("source_origin") != source_policy.HOSPITAL_ORIGIN
                or admission.get("image_id") != case["case_id"]
                or admission.get("source_sha256") != case["source_sha256"]
                or admission.get("source_reference") != case["source_reference"]
                or (admission.get("integrity") or {}).get("aliases") != case["source_aliases"]
                or case["source_reference"] != record["source_reference"]
                or case["source_aliases"] != record["integrity"]["aliases"]
                or any(admission.get(key) != record.get(key) for key in (
                    "trusted_patient_key", "trusted_laterality", "trusted_capture_sequence", "trusted_identity_method"))):
            raise RecoveryError("Hospital case source references or trusted linkage do not match the existing scanner")
        if admission.get("retinal_modality_method") != "MANUAL" and any(
                admission.get(key) != record.get(key) for key in (
                    "retinal_modality", "retinal_modality_state", "retinal_modality_method")):
            raise RecoveryError("Hospital source modality conflicts with the preserved admission")
        case["image_paths"] = sorted(item["path"] for item in inventory if item["sha256"] == case["source_sha256"])
        if not case["image_paths"]:
            raise RecoveryError("Hospital cases require exact copied original-image hashes")
    layout = {"kind": "HOSPITAL_AUTHORIZED_TWO_ROOT", "workspace_id": mapping["workspace_id"],
              "source_map_sha256": mapping_pin, "scan_contract": "hospital-two-root.v1",
              "root_order": ["UWF", "CFP"], "roots": summaries,
              "scanner_identity_projection_sha256": _digest(_scanner_projection(scan)), "linkage": linkage}
    if expected is not None and layout != expected:
        raise RecoveryError("Hospital copied-root scanner identity or exact layout differs from the trusted backup")
    return inventory, layout


def _copy_roots(parent: Path, source_map: dict, *, restore_map: dict | None = None) -> list[dict]:
    permissions = restore_map["roots"] if restore_map else source_map["roots"]
    return [{"root_id": row["root_id"], "modality": row["modality"],
             "path": str(parent / row["root_id"]), "read_only_sids": row["read_only_sids"]}
            for row in permissions]


def _restore_map(path, pin, source_map: dict, source_pin: str, manifest_pin: str,
                 *, bundle: Path, database: str | None = None, images: Path | None = None,
                 outputs: Path | None = None) -> tuple[dict, str, Path]:
    value, digest, filename = _approved_map(path, pin, RESTORE_MAP_VERSION)
    if set(value) != {"version", "approval_id", "source_map_sha256", "expected_manifest_sha256",
                      "workspace_id", "scope", "target_database", "bundle_path", "image_destination",
                      "output_destination", "linkage_key_ref", "roots"}:
        raise RecoveryError("Hospital restore-map fields do not match the frozen contract")
    _map_common(value)
    if (not isinstance(value["target_database"], str)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,62}", value["target_database"])
            or "test" not in re.split(r"[^a-z0-9]+", value["target_database"].lower())):
        raise RecoveryError("Hospital restore maps require an exact visibly test-only database name")
    if (value["source_map_sha256"] != source_pin or value["expected_manifest_sha256"] != manifest_pin
            or value["workspace_id"] != source_map["workspace_id"]
            or value["linkage_key_ref"] != source_map["linkage_key_ref"]):
        raise RecoveryError("The approved hospital restore map does not bind this source map and trusted backup")
    for key in ("bundle_path", "image_destination", "output_destination"):
        value[key] = str(_map_path(value[key]))
    if (Path(value["bundle_path"]) != bundle or (database is not None and value["target_database"] != database)
            or (images is not None and Path(value["image_destination"]) != images)
            or (outputs is not None and Path(value["output_destination"]) != outputs)):
        raise RecoveryError("Hospital restore invocation differs from the independently approved target map")
    value["roots"] = _map_roots(value["roots"], source=False)
    for row in value["roots"]:
        if Path(row["path"]) != Path(value["image_destination"]) / row["root_id"]:
            raise RecoveryError("Hospital restored roots must use the exact approved image-parent layout")
    destinations = [Path(value[key]) for key in ("bundle_path", "image_destination", "output_destination")]
    for target in destinations:
        for original in source_map["roots"]:
            source = Path(original["path"])
            if target.is_relative_to(source) or source.is_relative_to(target):
                raise RecoveryError("Hospital recovery must never overlap or fall back to original roots")
    if any(left.is_relative_to(right) or right.is_relative_to(left)
           for index, left in enumerate(destinations) for right in destinations[index + 1:]):
        raise RecoveryError("Hospital bundle, restored images and output must be disjoint")
    if any(filename.is_relative_to(target) for target in destinations):
        raise RecoveryError("Hospital restore-map authority must be retained outside the supplied bundle")
    return value, digest, filename


def backup(database: PostgresDatabase, *, image_root: str | Path | None = None,
           destination: str | Path, release: str, apply: bool = False,
           pg_dump: str = "pg_dump", runner=subprocess.run,
           hospital_source_map: str | Path | None = None,
           expected_hospital_source_map_sha256: str | None = None) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", release):
        raise RecoveryError("Supply the exact release version or commit identity")
    if database.settings.schema == "public":
        raise RecoveryError("Recovery requires a dedicated application schema")
    hospital = hospital_source_map is not None
    mapping, mapping_pin, map_file = None, None, None
    if hospital:
        if image_root is not None:
            raise RecoveryError("Choose ordinary image-root or explicitly approved hospital source-map recovery")
        mapping, mapping_pin, map_file = _source_map(hospital_source_map, expected_hospital_source_map_sha256,
                                                  require_snapshot=apply)
        _source_binding_active(mapping)
        protected = [_path(row["path"], exists=True) for row in mapping["roots"]]
        target = _new_directory(destination, *protected, map_file)
        if target != Path(mapping["backup_destination"]):
            raise RecoveryError("Hospital backup destination differs from its independently approved source map")
        root = None
    else:
        if expected_hospital_source_map_sha256 is not None or image_root is None:
            raise RecoveryError("Ordinary backup requires an image root without hospital activation flags")
        root = _path(image_root, exists=True)
        target = _new_directory(destination, root)
    repository = Path(__file__).resolve().parents[2]
    if target.is_relative_to(repository):
        raise RecoveryError("Store private backups outside the source checkout")
    with _snapshot(database, export=apply, hospital=hospital) as (state, snapshot_id):
        if hospital:
            inventory, layout = _hospital_layout(state, mapping["roots"], mapping, mapping_pin,
                                                require_snapshot=apply)
        else:
            inventory, layout = _image_plan(state, root), None
        report = {"status": "PLAN_ONLY", "action": "backup", "schema": state["schema"],
                  "workspace_count": len(state["workspaces"]), "case_count": len(state["cases"]),
                  "image_count": len(inventory), "image_bytes": sum(x["size"] for x in inventory)}
        if hospital:
            report.update(hospital_candidate_snapshots=layout["roots"],
                          snapshot_approved=all(row["candidate_inventory_sha256"] is not None for row in mapping["roots"]))
        if not apply:
            return report
        target.mkdir(exist_ok=False)
        if hospital:
            _private_recovery_root(target, mapping["roots"])
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
        if hospital:
            for row in mapping["roots"]:
                (originals / row["root_id"]).mkdir()
        for item in inventory:
            if hospital:
                source_root = next(row["path"] for row in mapping["roots"] if row["root_id"] == item["root_id"])
                source = _path(Path(source_root) / item["basename"], exists=True)
            else:
                source = _path(root / item["path"], exists=True)
            copied = originals / item["path"]
            copied.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as incoming, copied.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)
            if (copied.stat().st_size != item["size"] or source.stat().st_size != item["size"]
                    or _file_hash(copied) != item["sha256"] or _file_hash(source) != item["sha256"]):
                raise RecoveryError("Original-image bytes changed during backup; partial output retained")
        if hospital:
            _hospital_layout(state, _copy_roots(originals, mapping), mapping, mapping_pin, expected=layout)
        version = HOSPITAL_BUNDLE_VERSION if hospital else BUNDLE_VERSION
        manifest = {"version": version, "release": release, **state,
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "images": inventory, "dump_sha256": _file_hash(dump),
                    "scope": "dedicated_schema_and_originals; historical_export_archives_not_included"}
        if hospital:
            manifest["source_layout"] = layout
        _write_json(target / "manifest.json", manifest)
        _write_json(target / "receipt.json", {"version": version, "status": "BACKUP_COMPLETE",
                    "manifest_sha256": _digest(manifest)})
    verify_bundle(target, hospital_source_map=hospital_source_map,
                  expected_hospital_source_map_sha256=expected_hospital_source_map_sha256)
    return {**report, "status": "BACKUP_VERIFIED", "inference_requests": 0,
            "manifest_sha256": _digest(manifest)}


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


def verify_bundle(bundle: str | Path, *, expected_manifest_sha256: str | None = None,
                  hospital_source_map: str | Path | None = None,
                  expected_hospital_source_map_sha256: str | None = None,
                  hospital_restore_map: str | Path | None = None,
                  expected_hospital_restore_map_sha256: str | None = None) -> dict:
    root = _path(bundle, exists=True)
    manifest, receipt = _load_json(root / "manifest.json"), _load_json(root / "receipt.json")
    version = manifest.get("version")
    hospital = version == HOSPITAL_BUNDLE_VERSION
    if (version not in {BUNDLE_VERSION, HOSPITAL_BUNDLE_VERSION} or receipt.get("version") != version
            or receipt.get("status") != "BACKUP_COMPLETE"
            or receipt.get("manifest_sha256") != _digest(manifest)):
        raise RecoveryError("Backup completion receipt does not match the manifest")
    if expected_manifest_sha256 is not None and (
            not isinstance(expected_manifest_sha256, str) or not _HASH.fullmatch(expected_manifest_sha256)
            or expected_manifest_sha256 != _digest(manifest)
            or expected_manifest_sha256 != _file_hash(_path(root / "manifest.json", exists=True))):
        raise RecoveryError("Backup manifest does not match the independently retained trusted pin")
    mapping, mapping_pin, restore_mapping = None, None, None
    if hospital:
        mapping, mapping_pin, map_file = _source_map(hospital_source_map, expected_hospital_source_map_sha256)
        if map_file.is_relative_to(root):
            raise RecoveryError("Hospital source-map authority must be retained outside the supplied bundle")
        if hospital_restore_map is not None:
            restore_mapping, _, _ = _restore_map(hospital_restore_map, expected_hospital_restore_map_sha256,
                                                mapping, mapping_pin, expected_manifest_sha256, bundle=root)
        elif root != Path(mapping["backup_destination"]) or expected_hospital_restore_map_sha256 is not None:
            raise RecoveryError("Transferred hospital bundles require an independently approved restore map")
        _private_recovery_root(root, restore_mapping["roots"] if restore_mapping else mapping["roots"])
    elif any(value is not None for value in (hospital_source_map, expected_hospital_source_map_sha256,
                                             hospital_restore_map, expected_hospital_restore_map_sha256)):
        raise RecoveryError("Hospital activation maps cannot silently change an ordinary v2 backup")
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
            if not hospital and bool(workspace["input_folder"]) != (relative is not None):
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
        if hospital:
            copied = json.loads(_json_bytes(manifest))
            found, _ = _hospital_layout(copied, _copy_roots(root / "originals", mapping, restore_map=restore_mapping),
                                        mapping, mapping_pin, expected=manifest["source_layout"])
            if found != images or copied["cases"] != cases or copied["workspaces"] != workspaces:
                raise RecoveryError("Hospital backup mapping does not match its complete copied scanner layout")
        else:
            bindings = _workspace_case_bindings(manifest, root / "originals")
            by_path = {item["path"]: item["sha256"] for item in images}
            for case, paths in zip(cases, bindings, strict=True):
                if (case["image_paths"] != paths
                        or any(by_path.get(path) != case["source_sha256"] for path in paths)):
                    raise RecoveryError("Backup case mapping does not match its workspace-visible originals")
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
    if (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,62}", expected_name)
            or expected_name != actual_name or "test" not in re.split(r"[^a-z0-9]+", expected_name.lower())
            or source_name.casefold() == actual_name.casefold()):
        raise RecoveryError("Restore requires an exact, separate, visibly test-only database name")
    with database.session(autocommit=False) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            if connection.execute("SELECT current_database()").fetchone()[0] != expected_name:
                raise RecoveryError("Connected restore database does not match the approved target")
            _reject_unqualified_entry_guard(connection, database.settings.schema)
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
            expected_manifest_sha256: str | None = None,
            image_destination: str | Path, output_destination: str | Path,
            apply: bool = False, target_quiesced: bool = False,
            pg_restore: str = "pg_restore", runner=subprocess.run,
            hospital_source_map: str | Path | None = None,
            expected_hospital_source_map_sha256: str | None = None,
            hospital_restore_map: str | Path | None = None,
            expected_hospital_restore_map_sha256: str | None = None) -> dict:
    if (not isinstance(expected_manifest_sha256, str)
            or not _HASH.fullmatch(expected_manifest_sha256)):
        raise RecoveryError("Restore requires the manifest SHA-256 retained independently from trusted backup creation; do not derive trust from the supplied bundle")
    hospital = hospital_source_map is not None
    _isolated_restore_environment(hospital=hospital)
    root = _path(bundle, exists=True)
    manifest = verify_bundle(root, expected_manifest_sha256=expected_manifest_sha256,
                             hospital_source_map=hospital_source_map,
                             expected_hospital_source_map_sha256=expected_hospital_source_map_sha256,
                             hospital_restore_map=hospital_restore_map,
                             expected_hospital_restore_map_sha256=expected_hospital_restore_map_sha256)
    if database.settings.schema != manifest["schema"]:
        raise RecoveryError("Restore schema does not match the explicitly configured target schema")
    images = _new_directory(image_destination, root)
    outputs = _new_directory(output_destination, root, images)
    mapping, source_pin, restored, restore_pin = None, None, None, None
    if hospital:
        mapping, source_pin, source_file = _source_map(hospital_source_map, expected_hospital_source_map_sha256)
        restored, restore_pin, restore_file = _restore_map(
            hospital_restore_map, expected_hospital_restore_map_sha256, mapping, source_pin,
            expected_manifest_sha256, bundle=root, database=expected_database, images=images, outputs=outputs)
        if any(filename.is_relative_to(target) for filename in (source_file, restore_file)
               for target in (images, outputs)):
            raise RecoveryError("Independent map authority must remain outside new recovery directories")
    _empty_target(database, expected_database, manifest["source_database"]["database"])
    report = {"status": "PLAN_ONLY", "action": "restore", "schema": manifest["schema"],
              "target_database": expected_database,
              "workspace_count": len(manifest["workspaces"]), "case_count": len(manifest["cases"]),
              "image_count": len(manifest["images"]), "paths_remapped_in_isolated_target": True}
    if hospital:
        report["workspace_id"] = restored["workspace_id"]
    if not apply:
        return report
    if not target_quiesced:
        raise RecoveryError("Confirm the isolated target has no concurrent writers before restore")
    images.mkdir(exist_ok=False)
    outputs.mkdir(exist_ok=False)
    if hospital:
        for row in restored["roots"]:
            (images / row["root_id"]).mkdir()
        _private_recovery_root(images, restored["roots"])
        _private_recovery_root(outputs, restored["roots"])
    for item in manifest["images"]:
        relative = _relative(item["path"])
        source = _path(root / "originals" / relative, exists=True)
        target = images / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as incoming, target.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        if target.stat().st_size != item["size"] or _file_hash(target) != item["sha256"]:
            raise RecoveryError("Restored original-image hash does not match; partial output retained")
    if hospital:
        _hospital_layout(json.loads(_json_bytes(manifest)), restored["roots"], mapping, source_pin,
                         expected=manifest["source_layout"])
    # Recheck after file copying, immediately before the first DB mutation.
    _empty_target(database, expected_database, manifest["source_database"]["database"])
    # Execute only a private, verified copy bound to the independent manifest
    # pin, never an archive that can be swapped in the supplied bundle later.
    restore_dump = outputs / "restore-database.dump"
    with _path(root / "database.dump", exists=True).open("rb") as incoming, restore_dump.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing)
    if _file_hash(restore_dump) != manifest["dump_sha256"]:
        raise RecoveryError("The database archive changed after verification; no restore was attempted")
    # pg_restore requires --dbname to execute; PGDATABASE alone selects no
    # connection mode. Only a restricted exact name goes in argv, never a DSN.
    _run([pg_restore, f"--dbname={expected_database}", "--no-password", "--exit-on-error", "--single-transaction",
          "--no-owner", "--no-privileges", str(restore_dump)],
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
    with _snapshot(database, hospital=hospital) as (state, _):
        if hospital:
            _hospital_layout(state, restored["roots"], mapping, source_pin, expected=manifest["source_layout"])
        else:
            _image_plan(state, images)
        if state["cases"] != manifest["cases"]:
            raise RecoveryError("Restored case identities, revisions or payload hashes differ")
        expected = expected_workspaces
        if state["workspaces"] != expected:
            raise RecoveryError("Restored workspace identities, revisions or mapped paths differ")
    receipt = {
        "version": manifest["version"], "status": "RESTORE_DATA_VERIFIED",
        "manifest_sha256": _digest(manifest), "release": manifest["release"],
        "target_database": expected_database,
        "application_reopen_export": "NOT_RUN", "inference": "NOT_RUN"}
    if hospital:
        receipt.update(source_map_sha256=source_pin, restore_map_sha256=restore_pin,
                       restored_roots=restored["roots"], scope=restored["scope"],
                       workspace_id=restored["workspace_id"])
        _private_recovery_root(outputs, restored["roots"])
    _write_json(outputs / "recovery-receipt.json", receipt)
    return {**report, "status": "RESTORE_DATA_VERIFIED", "application_reopen_export": "NOT_RUN"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "backup"):
        command = commands.add_parser(name)
        lane = command.add_mutually_exclusive_group(required=True)
        lane.add_argument("--image-root")
        lane.add_argument("--hospital-source-map")
        command.add_argument("--expected-hospital-source-map-sha256")
        command.add_argument("--destination", required=True)
        command.add_argument("--release", required=True)
        if name == "backup":
            command.add_argument("--apply", action="store_true")
            command.add_argument("--pg-dump", default="pg_dump")
    command = commands.add_parser("verify")
    command.add_argument("--bundle", required=True)
    command.add_argument("--expected-manifest-sha256")
    for flag in ("hospital-source-map", "expected-hospital-source-map-sha256",
                 "hospital-restore-map", "expected-hospital-restore-map-sha256"):
        command.add_argument("--" + flag)
    command = commands.add_parser("restore")
    command.add_argument("--bundle", required=True)
    command.add_argument("--expected-target-database", required=True)
    command.add_argument("--expected-manifest-sha256", required=True)
    command.add_argument("--image-destination", required=True)
    command.add_argument("--output-destination", required=True)
    command.add_argument("--apply", action="store_true")
    command.add_argument("--target-quiesced", action="store_true")
    command.add_argument("--pg-restore", default="pg_restore")
    for flag in ("hospital-source-map", "expected-hospital-source-map-sha256",
                 "hospital-restore-map", "expected-hospital-restore-map-sha256"):
        command.add_argument("--" + flag)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            manifest = verify_bundle(args.bundle, expected_manifest_sha256=args.expected_manifest_sha256,
                                     hospital_source_map=args.hospital_source_map,
                                     expected_hospital_source_map_sha256=args.expected_hospital_source_map_sha256,
                                     hospital_restore_map=args.hospital_restore_map,
                                     expected_hospital_restore_map_sha256=args.expected_hospital_restore_map_sha256)
            result = {"status": "BUNDLE_VERIFIED", "live_restore": "NOT_RUN",
                      "trust": "MATCHED_INDEPENDENT_PIN" if args.expected_manifest_sha256 else "INTEGRITY_ONLY_NO_ARCHIVE_TRUST",
                      "image_count": len(manifest["images"])}
        else:
            settings = PostgresSettings.from_env(
                url_variable=RESTORE_URL_ENV if args.command == "restore" else "DR_SUPPORT_DATABASE_URL")
            database = PostgresDatabase(settings)
            if args.command == "restore":
                result = restore(database, bundle=args.bundle,
                                 expected_manifest_sha256=args.expected_manifest_sha256,
                                 expected_database=args.expected_target_database,
                                 image_destination=args.image_destination,
                                 output_destination=args.output_destination, apply=args.apply,
                                 target_quiesced=args.target_quiesced, pg_restore=args.pg_restore,
                                 hospital_source_map=args.hospital_source_map,
                                 expected_hospital_source_map_sha256=args.expected_hospital_source_map_sha256,
                                 hospital_restore_map=args.hospital_restore_map,
                                 expected_hospital_restore_map_sha256=args.expected_hospital_restore_map_sha256)
            else:
                result = backup(database, image_root=args.image_root, destination=args.destination,
                                release=args.release, apply=getattr(args, "apply", False),
                                pg_dump=getattr(args, "pg_dump", "pg_dump"),
                                hospital_source_map=args.hospital_source_map,
                                expected_hospital_source_map_sha256=args.expected_hospital_source_map_sha256)
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
