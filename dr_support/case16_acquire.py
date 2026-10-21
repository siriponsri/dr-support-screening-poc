"""Finite local QA ingestion command. No listener, inference or secret files.

Execution requires focused review first. Only an existing explicit test DSN
environment value is consumed; no env-file reader or credential fallback.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.errors import ProgrammingError

from .contracts.workspaces import WorkspaceProfile
from .persistence import PostgresDatabase, PostgresSettings, SchemaMigrator
from .persistence.workspaces import PostgresWorkspaceCatalog
from .services.admission import inspect_file
from .services.case16_qualification import Case16Authorization, SOURCE_SHA256
from .services.case16_snapshot import case16_metadata_json
from .store import new_case


MANIFEST = Path("C:/Users/User/Documents/Codex/2026-10-21/task/qa-comparison-workspace-20261021/input-map-private.json")
MANIFEST_SHA = "e863a62f0a11aff938bdb8e1b60453aea9a3d70bee04308c3f4ff43ffdd8ffa6"
SOURCE_ROOT = Path("C:/Users/User/Desktop/demoImages")
QA_ROOT = Path("C:/Users/User/Documents/Codex/2026-10-21/task-3/evidence")
DATABASE_NAME = "dr_support_model_api_test"
DSN_ENV = "DR_SUPPORT_TEST_DATABASE_URL"


class AcquisitionError(RuntimeError):
    pass


def approved_source():
    """Select one pinned manifest entry, no image read until reviewed execution."""
    raw = MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise AcquisitionError("APPROVED_MANIFEST_CHANGED")
    value = json.loads(raw)
    if Path(value["sample_root"]).resolve() != SOURCE_ROOT.resolve():
        raise AcquisitionError("APPROVED_SOURCE_ROOT_MISMATCH")
    matches = [entry for entry in value["files"] if entry.get("sha256") == SOURCE_SHA256]
    if len(matches) != 1:
        raise AcquisitionError("EXACT_SOURCE_ENTRY_REQUIRED")
    entry = matches[0]
    relative = Path(entry["relative_path"])
    if relative.is_absolute() or ".." in relative.parts or entry.get("modality") != "UWF":
        raise AcquisitionError("SOURCE_MANIFEST_METADATA_INVALID")
    source = SOURCE_ROOT / relative
    if (not source.is_file() or source.resolve() != source.absolute()
            or any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                   for p in (source, *source.parents))):
        raise AcquisitionError("REGULAR_APPROVED_SOURCE_REQUIRED")
    return source, entry


def test_settings(environ, schema):
    dsn = environ.get(DSN_ENV, "")
    if not dsn:
        raise AcquisitionError("EXISTING_TEST_DSN_ENV_REQUIRED")
    try:
        params = conninfo_to_dict(dsn)
    except ProgrammingError:
        raise AcquisitionError("EXACT_LOCAL_TEST_DSN_REQUIRED") from None
    if (params.get("dbname") != DATABASE_NAME or params.get("host") != "127.0.0.1"
            or params.get("port") != "54805"
            or not params.get("user") or not params.get("password")
            or set(params) - {"dbname", "host", "port", "user", "password", "sslmode"}
            or params.get("sslmode", "disable") not in {"disable", "prefer", "require"}):
        raise AcquisitionError("EXACT_LOCAL_TEST_DSN_REQUIRED")
    if not schema.startswith("dr_support_test_case16_") or len(schema) != 55:
        raise AcquisitionError("FRESH_TEST_SCHEMA_REQUIRED")
    return PostgresSettings(dsn, schema=schema, application_name="case16-local-acquisition")


@contextmanager
def isolated_environment(settings, workspace_id, directory):
    """Dedicated command only: restore inherited env even if bootstrap fails."""
    original = dict(os.environ)
    try:
        for key in list(os.environ):
            if key.startswith(("DR_", "REMOTE_MODEL", "MODEL_", "CVAT_", "PG")):
                del os.environ[key]
        os.environ.update(
            APP_PROFILE="review", MODEL_RUNTIME="remote", WORKERS="1",
            DR_SUPPORT_CASE_STORE="postgres", DR_SUPPORT_DATABASE_URL=settings.dsn,
            DR_SUPPORT_DATABASE_SCHEMA=settings.schema, DR_SUPPORT_WORKSPACE_ID=workspace_id,
            DR_SUPPORT_STATE=str(directory / "unused.sqlite"),
            DR_SUPPORT_WORKSPACE_CATALOG=str(directory / "unused-catalog.sqlite"),
        )
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def reserve_workspace(settings, workspace_id, directory):
    """Create a NEW schema exclusively; never migrate an existing namespace."""
    database = PostgresDatabase(settings)
    with database.transaction() as connection:
        if connection.execute("SELECT current_database()").fetchone() != (DATABASE_NAME,):
            raise AcquisitionError("CONNECTED_DATABASE_MISMATCH")
        # No IF NOT EXISTS: collision fails, never adopts/reuses prior state.
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(settings.schema)))
    SchemaMigrator(database).migrate()
    now = datetime.now(timezone.utc).isoformat()
    profile = WorkspaceProfile(
        id=workspace_id, name="TEST_ONLY case16 local acquisition",
        input_folder=str(directory / "empty-input"), output_folder=str(directory / "output"),
        note="Fresh engineering QA ingestion; no clinician confirmation or gold labels.",
        created_at=now, updated_at=now, last_opened=now,
    )
    PostgresWorkspaceCatalog(database).create_and_activate(profile)


def build_app(workspace_id):
    from .api._factory import create_app
    app = create_app(case_store_mode="postgres", workspace_id=workspace_id,
                     include_samples=False, include_demo_fixtures=False)
    if app.state.images or app.state.admissions or app.state.model_connection is not None:
        raise AcquisitionError("EMPTY_LOCAL_BOOTSTRAP_REQUIRED")
    app.state.providers.clear()
    return app


def ingest_and_snapshot(app, source, entry, settings, workspace_id):
    """Normal image inspector + actual workflow hydration, only in fresh scope."""
    record, image = inspect_file(
        source, source_origin="PUBLIC", source_reference=f"DR-DEMO/{source.name}",
        retinal_modality=entry["modality"], retinal_modality_method="AUTHORIZED_SOURCE",
    )
    if (image is None or image.image_id != SOURCE_SHA256 or image.sha256 != SOURCE_SHA256
            or len(image.data) != entry["bytes"]
            or record.get("source_sha256") != SOURCE_SHA256):
        raise AcquisitionError("INGESTED_SOURCE_IDENTITY_MISMATCH")
    store = app.state.store
    with app.state.workspace_manager.lock, store.lock:
        if (store.workspace_id != workspace_id or store.database.settings.schema != settings.schema
                or store.all_cases()):
            raise AcquisitionError("FRESH_EMPTY_CASE_STORE_REQUIRED")
        # This is a NEW test case using the standard application shape. Record
        # actual ingestion identities, never repair or copy an existing case.
        case = new_case(image.image_id)
        case.update(source_sha256=image.sha256, image_sha256=image.sha256)
        store.put(case)
        app.state.images[image.image_id] = image
        app.state.admissions[image.image_id] = record
        # Execute the actual normal GET case workflow in-process: persists its
        # automatic admission/history/resolver state, without HTTP or inference.
        route = next(route for route in app.routes
                     if getattr(route, "path", None) == "/v1/cases/{image_id}"
                     and "GET" in getattr(route, "methods", set()))
        route.endpoint(image.image_id)
        document = case16_metadata_json(
            app, workspace_id=workspace_id, database_schema=settings.schema, revision=0,
        )
    # Eligibility is a REPORT, never changed to make the driver run.
    try:
        Case16Authorization(owner_reference="Sentinel_d7d1e493dbd88191a76fad54af3abf37").input(
            image, json.loads(document)["case"], record,
        )
        eligibility = "PASS"
    except Exception:
        eligibility = "BLOCKED_ORIGINAL_ADMISSION_NOT_EXECUTION_ELIGIBLE"
    return document, eligibility


def acquire(output_root):
    source, entry = approved_source()
    # Verify exact original bytes BEFORE any filesystem/DB mutation.
    raw = source.read_bytes()
    if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise AcquisitionError("APPROVED_SOURCE_CHANGED")
    token = uuid4().hex
    schema, workspace_id = "dr_support_test_case16_" + token, "ws_case16_test_" + token
    settings = test_settings(os.environ, schema)
    output_root = Path(output_root)
    repo = Path(__file__).resolve().parents[1]
    if (not output_root.is_absolute() or not output_root.is_dir()
            or output_root.resolve() != output_root.absolute()
            or not output_root.resolve().is_relative_to(QA_ROOT.resolve())
            or output_root.resolve().is_relative_to(repo)
            or output_root.resolve().is_relative_to(SOURCE_ROOT.resolve())
            or any((p / ".git").exists() for p in (output_root, *output_root.parents))
            or any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                   for p in (output_root, *output_root.parents))):
        raise AcquisitionError("EXISTING_OUTSIDE_REPO_CONTROLLED_QA_ROOT_REQUIRED")
    directory = output_root / ("case16-local-" + token)
    directory.mkdir(exist_ok=False)
    (directory / "empty-input").mkdir()
    (directory / "output").mkdir()
    receipt = {"schema": "case16-local-ingestion.v1", "status": "INCOMPLETE",
               "test_schema": schema, "workspace_id": workspace_id,
               "snapshot_sha256": None, "model_calls": 0, "listener_started": False}
    try:
        receipt["stage"] = "RESERVE_NEW_SCHEMA"
        with isolated_environment(settings, workspace_id, directory):
            reserve_workspace(settings, workspace_id, directory)
            receipt["stage"] = "BUILD_LOCAL_APP"
            app = build_app(workspace_id)
            receipt["stage"] = "NORMAL_INGESTION_AND_SNAPSHOT"
            document, eligibility = ingest_and_snapshot(app, source, entry, settings, workspace_id)
        receipt["stage"] = "WRITE_NEW_SNAPSHOT"
        with (directory / "CASE16_INPUT_RECORD.json").open("xb") as target:
            target.write(document)
        receipt.update(status="SNAPSHOT_CAPTURED", snapshot_sha256=hashlib.sha256(document).hexdigest(),
                       snapshot_consistency="VERIFIED_BY_REVIEWED_HELPER",
                       execution_eligibility=eligibility, stage="COMPLETE")
    except Exception as exc:
        # Keep partial NEW schema/directory for review; never drop/reset/retry.
        receipt.update(status="FAILED_RETAINED", error_class=type(exc).__name__)
        failure = AcquisitionError("ACQUISITION_FAILED_RETAINED_EVIDENCE")
        failure.receipt_path = directory / "ACQUISITION_RECEIPT.json"
        raise failure from None
    finally:
        with (directory / "ACQUISITION_RECEIPT.json").open("x", encoding="utf-8") as target:
            json.dump(receipt, target, sort_keys=True, indent=2)
    return directory / "ACQUISITION_RECEIPT.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--execute-reviewed-local-ingestion", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute_reviewed_local_ingestion:
        parser.error("Explicit reviewed local-ingestion execution required")
    try:
        receipt = acquire(args.output_root)
    except Exception as exc:
        code = str(exc) if type(exc) is AcquisitionError else "LOCAL_ACQUISITION_FAILED"
        print("BLOCKED: " + code + "; no retry or inference permitted.")
        receipt = getattr(exc, "receipt_path", None)
        if receipt is not None and receipt.is_file():
            print(receipt.resolve().as_posix())
            print(hashlib.sha256(receipt.read_bytes()).hexdigest())
        return 2
    print(receipt.resolve().as_posix())
    print(hashlib.sha256(receipt.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
