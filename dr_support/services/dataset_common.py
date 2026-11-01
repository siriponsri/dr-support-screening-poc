"""Shared constants, field lists and small helpers of the dataset manifest and exports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime, timezone

from .resolver import normalize_patient_key
from .source_policy import EXPORT_AUTHORIZATION, export_authorization

EXPORT_SCHEMA_VERSION = "s4.dataset-manifest.v3"


SNAPSHOT_SCHEMA_VERSION = "s4.dataset-snapshot.v5"


LEGACY_ELIGIBILITY_POLICY_VERSION = "s8.2-task-specific-v1.1-test-only-excluded"


SNAPSHOT_ELIGIBILITY_POLICY_VERSION = "s8.2-task-specific-v3"


NEGATIVE_POLICY_VERSION = "p4-negative-training-deferred-v1"


SOURCE_STATE_DIGEST_VERSION = "p4-source-state-v1"


SOURCE_ORIGINS = frozenset({"PUBLIC", "SYNTHETIC", "WORKSPACE", "HOSPITAL_AUTHORIZED", "UNKNOWN"})


# The single rule lives in source_policy; this name is kept for existing imports.
ENGINEERING_EXPORT_AUTHORIZATION = EXPORT_AUTHORIZATION


CANONICAL_LABELS = {
    "MICROANEURYSM",
    "HEMORRHAGE",
    "HARD_EXUDATE",
    "SOFT_EXUDATE",
}


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


# DT-06 (owner decision, 2026-10-25): labels from a TEST_ONLY workspace or reviewer
# are tagged and never count as training-ready or as physician grade folders.
TEST_ONLY_MARKER = "TEST_ONLY"


def label_class(case: dict, admission: dict | None, workspace) -> str | None:
    """TEST_ONLY, CLINICIAN, or None when no human reviewer is recorded.

    Uses the reviewers of the current labels (grade, annotation set, shapes, AI-box
    decisions, image confirmation), not superseded grade history.
    """
    reviewers = [
        (case.get("clinician_review") or {}).get("reviewer"),
        (case.get("annotation_confirmation") or {}).get("reviewer"),
        (admission or {}).get("reviewed_by"),
        *((entry or {}).get("reviewer") for entry in case.get("human_annotations") or []),
        # Only the latest decision per AI box counts; earlier decisions are superseded.
        *(entry.get("reviewer") for entry in {
            (entry or {}).get("detection_id"): entry or {} for entry in case.get("ai_annotation_reviews") or []
        }.values()),
    ]
    reviewers = [str(name).strip() for name in reviewers if name and str(name).strip()]
    workspace_text = " ".join(str(getattr(workspace, key, "") or "") for key in ("id", "name")).upper()
    if TEST_ONLY_MARKER in workspace_text or any(name.upper().startswith(TEST_ONLY_MARKER) for name in reviewers):
        return "TEST_ONLY"
    return "CLINICIAN" if reviewers else None


IMAGE_FIELDS = [
    "image_id",
    "filename",
    "image_sha256",
    "width",
    "height",
    "modality",
    "source_type",
    "patient_key",
    "laterality",
    "patient_resolution_method",
    "laterality_resolution_method",
    "modality_admission",
    "quality_state",
    "queue_state",
    "ai_grade",
    "ai_model_id",
    "ai_model_version",
    "ai_confidence",
    "clinician_grade",
    "grade_review_source",
    "review_status",
    "reviewer",
    "reviewed_at",
    "human_annotation_count",
    "ai_lesion_count",
    "cvat_annotation_count",
    "verification_status",
    "include_in_training",
    "label_class",
    "eligibility_reason",
    "image_confirmation_status",
    "image_confirmed_by",
    "image_confirmed_at",
    "dr_grade_confirmation_status",
    "dr_grade_confirmed_by",
    "dr_grade_confirmed_at",
    "annotation_confirmation_status",
    "annotation_confirmed_by",
    "annotation_confirmed_at",
    "annotation_set_hash",
    "confirmed_annotation_hash",
    "dr_grade_training_ready",
    "grade_eligibility_reason",
    "lesion_training_ready",
    "lesion_eligibility_reason",
    "training_group_key",
]


ANNOTATION_FIELDS = [
    "annotation_id",
    "image_id",
    "label",
    "shape_type",
    "geometry_json",
    "annotation_source",
    "reviewer",
    "created_at",
    "model_id",
    "model_version",
    "score",
    "verification_status",
    "include_in_training",
    "eligibility_reason",
    "source_detection_id",
    "original_label",
    "original_score",
    "original_geometry_json",
]


SNAPSHOT_RECORD_FIELDS = [
    "image_id", "filename", "source_sha256", "source_origin", "label_class", "source_available",
    "source_integrity_status", "export_authorization", "modality", "width", "height",
    "laterality", "patient_key", "training_group_key", "case_revision", "visit_key",
    "visit_evidence_state", "captured_at", "capture_sequence", "image_confirmation_status",
    "dr_grade_confirmation_status", "dr_grade_confirmed_by", "dr_grade_confirmed_at",
    "clinician_grade", "grade_provenance", "dr_grade_training_ready", "grade_eligibility_reason",
    "referral_status", "referral_rule_id", "referral_rule_version",
    "referral_source_grade_revision", "referral_reviewer", "referral_reviewed_at",
    "lesion_training_ready", "lesion_positive_training_ready", "lesion_eligibility_reason",
    "core_completeness_state", "core_completeness_reviewer", "core_completeness_at",
    "core_completeness_taxonomy_version", "advanced_completeness_state",
    "advanced_completeness_reviewer", "advanced_completeness_at",
    "advanced_completeness_taxonomy_version", "negative_training_authorized",
    "negative_eligibility_reason", "annotation_set_hash", "confirmed_annotation_hash",
    "processing_representation_version", "processing_analysis_sha256", "selected_ai_model_id",
    "selected_ai_invocation_id", "ai_evidence_status",
]


DR_LABEL_FIELDS = [
    "image_id", "source_sha256", "dr_grade", "grade_provenance", "reviewer", "reviewed_at",
    "case_revision", "training_group_key", "referral_status", "referral_rule_id",
    "referral_rule_version", "referral_source_grade_revision", "referral_reviewer",
    "referral_reviewed_at", "policy_version",
]


LESION_LABEL_FIELDS = [
    "annotation_id", "image_id", "source_sha256", "label", "shape_type", "geometry_json",
    "annotation_source", "reviewer", "reviewed_at", "source_detection_id", "case_revision",
    "annotation_set_hash", "confirmed_annotation_hash", "policy_version",
]


COMPLETENESS_FIELDS = [
    "image_id", "group", "state", "reviewer", "timestamp", "taxonomy_version", "case_revision",
    "annotation_set_hash", "negative_training_authorized", "negative_eligibility_reason",
]


AI_EVIDENCE_FIELDS = [
    "image_id", "source_sha256", "ai_kind", "annotation_id", "model_id", "model_version", "score",
    "status", "geometry_json", "source_detection_id", "invocation_id", "analysis_sha256",
    "provenance_status",
]


class DatasetManifestError(RuntimeError):
    """An expected dataset preview/export failure."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _source_state_receipt(workspace_id: str | None, cases: list[dict]) -> dict:
    """Build a durable digest from case revisions and canonical payload hashes."""
    entries = []
    for case in cases:
        payload = dict(case)
        image_id = str(payload.pop("image_id", ""))
        revision = payload.pop("revision", 0)
        entries.append({
            "case_id": image_id,
            "revision": revision,
            "payload_sha256": _sha256(_canonical_json_bytes(payload)),
        })
    entries.sort(key=lambda item: item["case_id"])
    material = {
        "algorithm": SOURCE_STATE_DIGEST_VERSION,
        "workspace_id": workspace_id,
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "eligibility_policy_version": SNAPSHOT_ELIGIBILITY_POLICY_VERSION,
        "negative_policy_version": NEGATIVE_POLICY_VERSION,
        "cases": entries,
    }
    return {
        "version": SOURCE_STATE_DIGEST_VERSION,
        "digest": _sha256(_canonical_json_bytes(material)),
        "case_count": len(entries),
        "case_revisions": entries,
    }


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(SHA256_PATTERN.fullmatch(value))


def _pseudonymous_patient_key(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return normalize_patient_key(value)
    except ValueError:
        return None


def _confirmed_patient_group_key(case: dict) -> str | None:
    """Require resolver-confirmed identity before deriving a training group."""
    if case.get("patient_resolution_state") != "RESOLVED":
        return None
    patient_key = _pseudonymous_patient_key(case.get("patient_key"))
    return f"patient:{patient_key}" if patient_key else None


def _source_origin(case: dict, image, admission: dict | None) -> str:
    for candidate in (
        (admission or {}).get("source_origin"),
        case.get("source_origin"),
        getattr(image, "source_origin", None) if image is not None else None,
    ):
        if candidate in SOURCE_ORIGINS:
            return candidate
    return "UNKNOWN"


def _export_authorization(source_origin: str) -> str:
    return export_authorization(source_origin)


def _completeness_record(case: dict, group: str) -> dict:
    value = (case.get("annotation_completeness") or {}).get(group) or {}
    if not isinstance(value, dict):
        return {"state": "NOT_REVIEWED"}
    return value


def _csv_bytes(rows: list[dict], fields: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows({field: "" if row.get(field) is None else row.get(field) for field in fields} for row in rows)
    return stream.getvalue().encode("utf-8")


def _geometry_json(geometry: object) -> str:
    return json.dumps(geometry, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise DatasetManifestError("Imported annotation geometry is not finite")
    return float(value)


def _imported_geometry(shape: dict) -> tuple[str, object]:
    """Normalize known CVAT geometry without changing its original coordinates."""
    raw_type = shape.get("type")
    points = shape.get("points")
    if not isinstance(points, list) or len(points) % 2:
        raise DatasetManifestError("Imported annotation geometry is invalid")
    values = [_float(value) for value in points]
    if raw_type in ("rectangle", "ellipse") and len(values) == 4:
        x1, y1, x2, y2 = values
        if x2 < x1 or y2 < y1:
            raise DatasetManifestError("Imported annotation rectangle is invalid")
        if raw_type == "rectangle":
            return "rectangle", {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}
        # CVAT ellipses are retained as ellipses unless they are circles. This
        # avoids silently changing non-circular imported geometry.
        if math.isclose(x2 - x1, y2 - y1):
            return "circle", {"cx": (x1 + x2) / 2, "cy": (y1 + y2) / 2, "radius": (x2 - x1) / 2}
        return "ellipse", {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}
    if raw_type in ("polygon", "polyline") and len(values) >= 6:
        return raw_type, {"points": [[values[index], values[index + 1]] for index in range(0, len(values), 2)]}
    if raw_type == "points" and len(values) == 2:
        return "point", {"x": values[0], "y": values[1]}
    raise DatasetManifestError(f"Unsupported imported annotation shape: {raw_type or 'unknown'}")
