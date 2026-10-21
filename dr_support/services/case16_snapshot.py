"""Explicit local metadata helper; no endpoint, startup, eligibility or inference.

Use only on an already authorized single-worker app and designated workspace.
Output may contain private context: retain under existing owner-controlled local
storage, never print/upload. Original JSON values (including absent/null) survive.
"""

from copy import deepcopy
import json
import os

from ..persistence.cases import CaseConflictError, PostgresCaseStore
from .case16_qualification import SOURCE_SHA256


class Case16SnapshotError(RuntimeError):
    """Bounded errors intentionally omit metadata, paths and connection details."""


def case16_metadata_snapshot(app, *, workspace_id, database_schema, revision):
    """Return the three original objects from a single captured app generation.

    No app factory/DB initialization, no other rows, and no get()/defaulting.
    PostgreSQL row consistency uses one REPEATABLE READ READ ONLY transaction.
    Manager/store locks serialize supported same-process workspace mutations;
    copied registered projections must match the durable admission exactly.
    This does not lock arbitrary external image writers or other app processes.
    It is a point-in-time snapshot, not authorization to execute a later plan.
    """
    if (type(revision) is not int or revision < 0
            or not isinstance(workspace_id, str) or not workspace_id
            or not isinstance(database_schema, str) or not database_schema):
        raise Case16SnapshotError("EXPLICIT_SNAPSHOT_SCOPE_REQUIRED")
    if os.environ.get("WORKERS", "1") != "1":
        raise Case16SnapshotError("SINGLE_WORKER_SNAPSHOT_REQUIRED")
    state = app.state
    manager = getattr(state, "workspace_manager", None)
    if manager is None:
        raise Case16SnapshotError("WORKSPACE_MANAGER_REQUIRED")
    with manager.lock:
        store = state.store
        if (type(store) is not PostgresCaseStore or manager.store is not store
                or store.workspace_id != workspace_id
                or getattr(state, "workspace_id", None) != workspace_id
                or store.database.settings.schema != database_schema):
            raise Case16SnapshotError("SNAPSHOT_SCOPE_MISMATCH")
        with store.lock:
            # Registered BridgeImage is frozen. Copy projections before the DB
            # read and verify them again before release; never load source files.
            image = state.images.get(SOURCE_SHA256)
            admission = deepcopy(state.admissions.get(SOURCE_SHA256))
            if image is None or not isinstance(admission, dict):
                raise Case16SnapshotError("REGISTERED_METADATA_REQUIRED")
            try:
                case = store.read_original_case(SOURCE_SHA256)
            except CaseConflictError:
                raise Case16SnapshotError("ORIGINAL_CASE_UNAVAILABLE_OR_INCONSISTENT") from None
            if case["revision"] != revision:
                raise Case16SnapshotError("SNAPSHOT_REVISION_MISMATCH")
            required = ("image_id", "source_sha256", "source_origin", "retinal_modality",
                        "modality_admission", "quality_state", "integrity_status")
            if any(key not in admission or admission[key] is None for key in required):
                raise Case16SnapshotError("ADMISSION_METADATA_INCOMPLETE")
            if "admission" in case and case["admission"] != admission:
                raise Case16SnapshotError("ADMISSION_PROJECTION_MISMATCH")
            if (image.image_id != SOURCE_SHA256 or admission["image_id"] != SOURCE_SHA256
                    or any(value != SOURCE_SHA256 for value in (
                        case.get("source_sha256"), case.get("image_sha256"),
                        admission["source_sha256"], image.sha256))):
                raise Case16SnapshotError("RECORDED_SOURCE_IDENTITY_MISMATCH")
            metadata = admission.get("source_metadata")
            if metadata is not None:
                if not isinstance(metadata, dict):
                    raise Case16SnapshotError("SOURCE_METADATA_INVALID")
                if ("source_sha256" in metadata
                        and metadata["source_sha256"] != SOURCE_SHA256):
                    raise Case16SnapshotError("RECORDED_SOURCE_IDENTITY_MISMATCH")
            keys = ("source_type", "source_origin", "source", "modality", "media_type")
            image_metadata = {key: deepcopy(getattr(image, key, None)) for key in keys}
            if any(not isinstance(value, str) or not value for value in image_metadata.values()):
                raise Case16SnapshotError("IMAGE_METADATA_INCOMPLETE")
            if (image.source_origin != admission["source_origin"]
                    or image.modality != admission["retinal_modality"]):
                raise Case16SnapshotError("IMAGE_ADMISSION_METADATA_MISMATCH")
            if (state.store is not store or manager.store is not store
                    or state.workspace_id != workspace_id
                    or state.images.get(SOURCE_SHA256) is not image
                    or state.admissions.get(SOURCE_SHA256) != admission):
                raise Case16SnapshotError("APP_PROJECTION_CHANGED")
            # No eligibility filtering: uncertainty/source-change/clinical values
            # remain original evidence for the qualification guard to reject.
            return deepcopy({"case": case, "admission": admission, "image": image_metadata})


def case16_metadata_json(app, *, workspace_id, database_schema, revision):
    """Serialize locally, without writing a file or emitting metadata to logs."""
    value = case16_metadata_snapshot(
        app, workspace_id=workspace_id, database_schema=database_schema, revision=revision,
    )
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")
