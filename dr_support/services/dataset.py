"""Derived dataset manifest and non-destructive workspace export."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import shutil
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .admission import legacy_admission
from ..presentation import annotation_set_hash, lesion_detection_id, review_evidence_view
from ..imaging import DerivativeError
from .resolver import normalize_patient_key


EXPORT_SCHEMA_VERSION = "s4.dataset-manifest.v2"
SNAPSHOT_SCHEMA_VERSION = "s4.dataset-snapshot.v3"
LEGACY_ELIGIBILITY_POLICY_VERSION = "s8.2-task-specific-v1"
SNAPSHOT_ELIGIBILITY_POLICY_VERSION = "s8.2-task-specific-v2"
NEGATIVE_POLICY_VERSION = "p4-negative-training-deferred-v1"
SOURCE_STATE_DIGEST_VERSION = "p4-source-state-v1"
SOURCE_ORIGINS = frozenset({"PUBLIC", "SYNTHETIC", "WORKSPACE", "UNKNOWN"})
ENGINEERING_EXPORT_AUTHORIZATION = {
    "PUBLIC": "ALLOWED_ENGINEERING_PUBLIC",
    "SYNTHETIC": "ALLOWED_ENGINEERING_SYNTHETIC",
    "WORKSPACE": "BLOCKED_WORKSPACE_NOT_AUTHORIZED",
    "UNKNOWN": "BLOCKED_UNKNOWN_ORIGIN",
}
CANONICAL_LABELS = {
    "MICROANEURYSM",
    "HEMORRHAGE",
    "HARD_EXUDATE",
    "SOFT_EXUDATE",
}
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")

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
    "image_id", "filename", "source_sha256", "source_origin", "source_available",
    "source_integrity_status", "export_authorization", "modality", "width", "height",
    "laterality", "patient_key", "training_group_key", "case_revision", "visit_key",
    "visit_evidence_state", "captured_at", "capture_sequence", "image_confirmation_status",
    "dr_grade_confirmation_status", "dr_grade_confirmed_by", "dr_grade_confirmed_at",
    "clinician_grade", "grade_provenance", "dr_grade_training_ready", "grade_eligibility_reason",
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
    "case_revision", "training_group_key", "policy_version",
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
    return ENGINEERING_EXPORT_AUTHORIZATION.get(source_origin, "BLOCKED_UNKNOWN_ORIGIN")


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


GROUPED_EXPORT_FIELDS = [
    "image_id", "group", "final_grade", "source_sha256", "source_was_dicom",
    "rendered_derivative_sha256", "export_format", "export_sha256", "output_path", "status",
]


def _grade_group(case: dict, admission: dict | None) -> tuple[str, int | None]:
    if (admission or {}).get("quality_state") == "UNGRADABLE":
        return "ungradable", None
    review = case.get("clinician_review") or {}
    if case.get("grade_status") == "NEEDS_SECOND_REVIEW" or case.get("state") in {"ESCALATED", "NEEDS_SECOND_REVIEW"} or review.get("review_action") == "ESCALATE":
        return "senior_review", None
    if case.get("grade_status") == "UNGRADABLE" or review.get("review_action") == "MARK_UNGRADABLE":
        return "ungradable", None
    grade, source, _ = DatasetManifestService._final_grade(case)
    if isinstance(grade, int) and not isinstance(grade, bool) and grade in range(5) and source in {
        "AI_ACCEPTED", "AI_CORRECTED", "MANUAL",
    }:
        return f"dr_grade_{grade}", grade
    return "needs_review", None


def _grouped_image_bytes(image, output_format: str, quality: int, derivative_service) -> tuple[bytes, str, bool]:
    from PIL import Image

    source_was_dicom = image.media_type == "application/dicom" or Path(image.filename).suffix.lower() in {".dcm", ".dicom"}
    derivative = derivative_service.prepare_display(image)
    data = derivative.data
    rendered_sha256 = _sha256(data)
    if output_format == "PNG" and derivative.lineage.format == "PNG":
        return data, rendered_sha256, source_was_dicom
    try:
        with Image.open(io.BytesIO(data)) as decoded:
            decoded.load()
            rgb = decoded.convert("RGB")
            output = io.BytesIO()
            if output_format == "PNG":
                rgb.save(output, format="PNG", optimize=False, compress_level=9)
            else:
                rgb.save(output, format="JPEG", quality=quality, subsampling=0, optimize=False, progressive=False)
            return output.getvalue(), rendered_sha256, source_was_dicom
    except Exception as error:
        raise DatasetManifestError("The admitted image could not be rendered for grouped export.") from error


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


class DatasetManifestService:
    """Build compatible rows from the active workspace's durable review state."""

    def __init__(self, app):
        self.app = app

    def _workspace(self):
        return getattr(getattr(self.app.state, "workspace_manager", None), "active_workspace", None)

    def _workspace_context(self) -> tuple[str | None, str | None]:
        workspace = self._workspace()
        return (workspace.id, workspace.name) if workspace is not None else (None, None)

    def _image_ids(self) -> list[str]:
        manager = getattr(self.app.state, "workspace_manager", None)
        if manager is not None and manager.active_workspace is not None:
            ids = set(getattr(self.app.state, "workspace_admission_ids", set()))
            ids.update(getattr(self.app.state, "workspace_image_ids", set()))
        else:
            ids = set(getattr(self.app.state, "admissions", {}))
            ids.update(getattr(self.app.state, "images", {}))
        return sorted(ids, key=str.casefold)

    def _case_records(self) -> list[dict]:
        """Read durable cases once so previews and exports share one source set."""
        store = self.app.state.store
        with store.lock:
            cases = list(store.all_cases())
        return self._merge_case_records(cases)

    def _merge_case_records(self, cases: list[dict]) -> list[dict]:
        known = {str(case.get("image_id")): case for case in cases}
        store = self.app.state.store
        for image_id in self._image_ids():
            if image_id not in known:
                known[image_id] = store.get(image_id)
        return [known[image_id] for image_id in sorted(known, key=str.casefold)]

    @contextmanager
    def _read_snapshot_cases(self):
        store = self.app.state.store
        reader = getattr(store, "repeatable_read_cases", None)
        if reader is None:
            with nullcontext(self._case_records()) as cases:
                yield cases
            return
        with reader() as cases:
            # PostgreSQL is authoritative for persisted workspace cases. Do not
            # issue a second connection read while the repeatable-read snapshot
            # is open.
            yield list(cases)

    def _case_context(self, image_id: str, store):
        case = store.get(image_id)
        image = getattr(self.app.state, "images", {}).get(image_id)
        admission = case.get("admission") or getattr(self.app.state, "admissions", {}).get(image_id)
        if admission is None and image is not None:
            admission = legacy_admission(image)
        return case, image, admission

    @staticmethod
    def _final_grade(case: dict) -> tuple[object, object, dict]:
        review = case.get("clinician_review") or {}
        if case.get("grade_status") in {"NEEDS_SECOND_REVIEW", "UNGRADABLE"}:
            return None, case.get("grade_review_source"), review
        grade = case.get("reviewed_grade")
        if grade is None:
            grade = review.get("final_grade")
        return grade, case.get("grade_review_source"), review

    @staticmethod
    def _case_eligibility(case: dict, image, admission: dict | None) -> tuple[bool, str]:
        image_sha256 = image.sha256 if image is not None else (
            admission.get("source_sha256") if admission else None
        )
        if not _is_sha256(image_sha256):
            return False, "MISSING_PROVENANCE"
        if case.get("queue_state", "INCLUDED") == "EXCLUDED":
            return False, "QUEUE_EXCLUDED"
        if admission is None:
            return False, "ADMISSION_UNRESOLVED"
        modality = admission.get("modality_admission")
        if modality == "REJECTED_INVALID":
            return False, "INVALID_IMAGE"
        if modality == "REJECTED_NON_FUNDUS":
            return False, "NON_FUNDUS"
        if modality != "FUNDUS_ACCEPTED":
            return False, "ADMISSION_UNRESOLVED"
        quality = admission.get("quality_state")
        if quality == "UNGRADABLE":
            return False, "UNGRADABLE"
        if quality == "NEEDS_REVIEW":
            return False, "QUALITY_REVIEW_REQUIRED"
        if quality not in {"GRADABLE", "NOT_EVALUATED"}:
            return False, "QUALITY_REVIEW_REQUIRED"
        if case.get("grade_status") == "NEEDS_SECOND_REVIEW":
            return False, "NEEDS_SECOND_REVIEW"
        if case.get("grade_status") == "UNGRADABLE":
            return False, "UNGRADABLE"
        grade, source, review = DatasetManifestService._final_grade(case)
        if grade is None:
            return False, "NO_FINAL_CLINICIAN_GRADE"
        if source not in {"AI_ACCEPTED", "AI_CORRECTED", "MANUAL"}:
            return False, "MISSING_PROVENANCE"
        if not review.get("reviewer") or not review.get("timestamp"):
            return False, "MISSING_PROVENANCE"
        return True, "ELIGIBLE"

    @staticmethod
    def _dataset_status(case: dict, admission: dict | None, include: bool, image) -> str:
        if case.get("queue_state", "INCLUDED") == "EXCLUDED":
            return "Excluded"
        if admission and admission.get("modality_admission") in {"REJECTED_INVALID", "REJECTED_NON_FUNDUS"}:
            return "Excluded"
        if include:
            return "Ready for dataset"
        if case.get("grade_status") == "NEEDS_SECOND_REVIEW":
            return "Needs second review"
        if case.get("grade_status") == "UNGRADABLE":
            return "Ungradable"
        grade, _, _ = DatasetManifestService._final_grade(case)
        if grade is None and (case.get("global") or case.get("lesion")):
            return "AI only"
        return "Needs review"

    @staticmethod
    def _image_verification(case: dict, admission: dict | None, include: bool) -> str:
        if case.get("queue_state", "INCLUDED") == "EXCLUDED":
            return "EXCLUDED"
        if admission and admission.get("modality_admission") in {"REJECTED_INVALID", "REJECTED_NON_FUNDUS"}:
            return "EXCLUDED"
        if include:
            return "CLINICIAN_REVIEWED"
        if case.get("global") or case.get("lesion"):
            return "AI_ONLY"
        return "UNVERIFIED"

    @staticmethod
    def _image_confirmation(case: dict, admission: dict | None) -> tuple[str, str | None, str | None]:
        """Return explicit image confirmation without upgrading old records silently."""
        if admission and admission.get("reviewed_by") and admission.get("reviewed_at"):
            return "CONFIRMED", admission.get("reviewed_by"), admission.get("reviewed_at")
        # Legacy fixture/workspace records predate the explicit Confirm Image
        # milestone. Keep them readable and compatible without changing their
        # stored audit state.
        if admission and admission.get("admission_method") == "LEGACY_COMPAT":
            return "CONFIRMED", None, None
        return "DRAFT", None, None

    @staticmethod
    def _annotation_confirmation(case: dict) -> tuple[bool, dict]:
        confirmation = case.get("annotation_confirmation") or {}
        current_hash = case.get("annotation_hash") or annotation_set_hash(case)
        confirmed = bool(
            case.get("lesion_review_state") == "REVIEWED"
            and case.get("confirmed_annotation_hash") == current_hash
            and confirmation.get("reviewer")
            and confirmation.get("timestamp")
        )
        return confirmed, confirmation

    @staticmethod
    def _grade_confirmation(case: dict, grade: object, review: dict) -> tuple[str, str | None, str | None]:
        """Expose the final-grade milestone without changing historical review records."""
        if case.get("grade_status") == "UNGRADABLE":
            return "UNGRADABLE", review.get("reviewer"), review.get("timestamp")
        if case.get("grade_status") == "NEEDS_SECOND_REVIEW":
            return "NEEDS_SECOND_REVIEW", review.get("reviewer"), review.get("timestamp")
        if grade is not None and review.get("reviewer") and review.get("timestamp"):
            return "CONFIRMED", review.get("reviewer"), review.get("timestamp")
        return "DRAFT", None, None

    @staticmethod
    def _task_reason(case: dict, admission: dict | None, image, image_confirmed: bool, *, task: str) -> str:
        image_sha256 = image.sha256 if image is not None else ((admission or {}).get("source_sha256"))
        if not _is_sha256(image_sha256):
            return "MISSING_PROVENANCE"
        if case.get("queue_state", "INCLUDED") == "EXCLUDED":
            return "QUEUE_EXCLUDED"
        if admission is None or admission.get("modality_admission") != "FUNDUS_ACCEPTED":
            return "IMAGE_NOT_CONFIRMED" if task == "grade" and not image_confirmed else "ADMISSION_UNRESOLVED"
        if admission.get("quality_state") == "UNGRADABLE":
            return "UNGRADABLE"
        if admission.get("quality_state") == "NEEDS_REVIEW":
            return "QUALITY_REVIEW_REQUIRED"
        if not image_confirmed:
            return "IMAGE_NOT_CONFIRMED"
        if task == "grade":
            if case.get("grade_status") == "NEEDS_SECOND_REVIEW":
                return "NEEDS_SECOND_REVIEW"
            if case.get("grade_status") == "UNGRADABLE":
                return "UNGRADABLE"
            grade, source, review = DatasetManifestService._final_grade(case)
            if grade is None:
                return "NO_FINAL_CLINICIAN_GRADE"
            if source not in {"AI_ACCEPTED", "AI_CORRECTED", "MANUAL"}:
                return "MISSING_PROVENANCE"
            if not review.get("reviewer") or not review.get("timestamp"):
                return "MISSING_PROVENANCE"
        else:
            confirmed, confirmation = DatasetManifestService._annotation_confirmation(case)
            if not confirmed:
                return "NO_ANNOTATION_CONFIRMATION"
            if not confirmation.get("reviewer") or not confirmation.get("timestamp"):
                return "MISSING_PROVENANCE"
        return "ELIGIBLE"

    def _rows(self, cases: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
        image_rows: list[dict] = []
        annotation_rows: list[dict] = []
        cases = self._case_records() if cases is None else cases
        for case in cases:
            image_id = str(case.get("image_id"))
            image = getattr(self.app.state, "images", {}).get(image_id)
            admission = case.get("admission") or getattr(self.app.state, "admissions", {}).get(image_id)
            if admission is None and image is not None:
                admission = legacy_admission(image)
            include, eligibility_reason = self._case_eligibility(case, image, admission)
            grade, grade_source, review = self._final_grade(case)
            grade_confirmation_status, grade_confirmed_by, grade_confirmed_at = self._grade_confirmation(case, grade, review)
            image_confirmation_status, image_confirmed_by, image_confirmed_at = self._image_confirmation(case, admission)
            grade_reason = self._task_reason(case, admission, image, image_confirmation_status == "CONFIRMED", task="grade")
            annotation_confirmed, annotation_confirmation = self._annotation_confirmation(case)
            current_annotation_hash = case.get("annotation_hash") or annotation_set_hash(case)
            lesion_reason = self._task_reason(case, admission, image, image_confirmation_status == "CONFIRMED", task="lesion")
            grade_ready = grade_reason == "ELIGIBLE" and include
            lesion_ready = lesion_reason == "ELIGIBLE"
            global_result = case.get("global") or {}
            lesion_result = case.get("lesion") or {}
            human_annotations = case.get("human_annotations") or []
            imported_annotations = case.get("annotations") or []
            source_origin = _source_origin(case, image, admission)
            image_sha256 = image.sha256 if image is not None else (admission or {}).get("source_sha256")
            filename = (admission or {}).get("filename") or (image.filename if image is not None else image_id)
            core_completeness = _completeness_record(case, "CORE")
            advanced_completeness = _completeness_record(case, "ADVANCED")
            row = {
                "image_id": image_id,
                "filename": filename,
                "image_sha256": image_sha256 if _is_sha256(image_sha256) else None,
                "source_sha256": image_sha256 if _is_sha256(image_sha256) else None,
                "width": (admission or {}).get("width"),
                "height": (admission or {}).get("height"),
                "modality": (admission or {}).get("retinal_modality", "UNKNOWN") if image is not None else None,
                "source_type": image.source_type if image is not None else None,
                "source_origin": source_origin,
                "source_available": image is not None,
                "source_integrity_status": (admission or {}).get("integrity_status", "UNKNOWN"),
                "export_authorization": _export_authorization(source_origin),
                "patient_key": _pseudonymous_patient_key(case.get("patient_key")),
                "laterality": case.get("laterality", "UNKNOWN"),
                "patient_resolution_method": case.get("patient_resolution_method", "NONE"),
                "laterality_resolution_method": case.get("laterality_resolution_method", "NONE"),
                "modality_admission": (admission or {}).get("modality_admission"),
                "quality_state": (admission or {}).get("quality_state"),
                "queue_state": case.get("queue_state", "INCLUDED"),
                "ai_grade": global_result.get("grade"),
                "ai_model_id": global_result.get("model_id"),
                "ai_model_version": global_result.get("model_version"),
                "ai_confidence": global_result.get("confidence"),
                "clinician_grade": grade,
                "grade_review_source": grade_source,
                "review_status": "CLINICIAN_REVIEWED" if grade is not None else ("AI_ONLY" if global_result or lesion_result else "UNVERIFIED"),
                "reviewer": review.get("reviewer"),
                "reviewed_at": review.get("timestamp"),
                "human_annotation_count": len(human_annotations),
                "ai_lesion_count": len(lesion_result.get("lesions") or []),
                "cvat_annotation_count": len(imported_annotations),
                "verification_status": self._image_verification(case, admission, include),
                "include_in_training": include,
                "eligibility_reason": eligibility_reason,
                "dataset_status": self._dataset_status(case, admission, include, image),
                "image_confirmation_status": image_confirmation_status,
                "image_confirmed_by": image_confirmed_by,
                "image_confirmed_at": image_confirmed_at,
                "dr_grade_confirmation_status": grade_confirmation_status,
                "dr_grade_confirmed_by": grade_confirmed_by,
                "dr_grade_confirmed_at": grade_confirmed_at,
                "annotation_confirmation_status": "CONFIRMED" if annotation_confirmed else "DRAFT",
                "annotation_confirmed_by": annotation_confirmation.get("reviewer") if annotation_confirmed else None,
                "annotation_confirmed_at": annotation_confirmation.get("timestamp") if annotation_confirmed else None,
                "annotation_set_hash": current_annotation_hash,
                "confirmed_annotation_hash": case.get("confirmed_annotation_hash"),
                "dr_grade_training_ready": grade_ready,
                "grade_eligibility_reason": grade_reason,
                "lesion_training_ready": lesion_ready,
                "lesion_eligibility_reason": lesion_reason,
                "training_group_key": _confirmed_patient_group_key(case),
                "core_completeness_state": core_completeness.get("state", "NOT_REVIEWED"),
                "core_completeness_reviewer": core_completeness.get("reviewer"),
                "core_completeness_at": core_completeness.get("timestamp"),
                "core_completeness_taxonomy_version": core_completeness.get("taxonomy_version"),
                "advanced_completeness_state": advanced_completeness.get("state", "NOT_REVIEWED"),
                "advanced_completeness_reviewer": advanced_completeness.get("reviewer"),
                "advanced_completeness_at": advanced_completeness.get("timestamp"),
                "advanced_completeness_taxonomy_version": advanced_completeness.get("taxonomy_version"),
                "negative_training_authorized": False,
                "negative_eligibility_reason": "REVIEWED_NONE_FOUND_NOT_AUTHORIZED" if core_completeness.get("state") == "REVIEWED_NONE_FOUND" else "NO_EXPLICIT_NEGATIVE_POLICY",
                "case_revision": case.get("revision", 0),
                "grade_provenance": grade_source,
                "visit_key": (case.get("visit_context") or {}).get("visit_key"),
                "visit_evidence_state": (case.get("visit_context") or {}).get("evidence_state", "UNKNOWN"),
                "captured_at": (case.get("visit_context") or {}).get("captured_at"),
                "capture_sequence": (case.get("visit_context") or {}).get("capture_sequence"),
                "processing_representation_version": (case.get("analysis_derivative") or {}).get("representation_version"),
                "processing_analysis_sha256": (case.get("analysis_derivative") or {}).get("analysis_sha256"),
                "selected_ai_model_id": (case.get("selected_ai_evidence") or {}).get("model_id"),
                "selected_ai_invocation_id": (case.get("selected_ai_evidence") or {}).get("invocation_id"),
                "ai_evidence_status": "AVAILABLE" if global_result or lesion_result else "UNAVAILABLE",
            }
            case_annotations = self._annotation_rows(
                case, row, global_result, lesion_result, human_annotations,
                imported_annotations, include, eligibility_reason, lesion_ready,
                annotation_confirmed, annotation_confirmation,
            )
            row["lesion_positive_training_ready"] = any(
                item["include_in_training"]
                and item["annotation_source"] in {"HUMAN", "HUMAN_CORRECTION", "CVAT_IMPORTED"}
                for item in case_annotations
            )
            image_rows.append(row)
            annotation_rows.extend(case_annotations)
        return image_rows, annotation_rows

    @staticmethod
    def _annotation_rows(
        case: dict,
        image_row: dict,
        global_result: dict,
        lesion_result: dict,
        human_annotations: list[dict],
        imported_annotations: list[dict],
        image_include: bool,
        image_reason: str,
        lesion_ready: bool,
        annotation_confirmed: bool,
        annotation_confirmation: dict,
    ) -> list[dict]:
        image_id = image_row["image_id"]
        rows: list[dict] = []
        decisions = {}
        for decision in case.get("ai_annotation_reviews") or []:
            if decision.get("detection_id"):
                decisions[decision["detection_id"]] = decision
        for index, lesion in enumerate(lesion_result.get("lesions") or []):
            x1, y1, x2, y2 = lesion["rectangle"]
            detection_id = lesion.get("detection_id") or lesion_detection_id(lesion)
            decision = decisions.get(detection_id) or {}
            removed = decision.get("action") == "REJECT"
            correction = decision.get("action") == "CORRECT"
            corrected_label = decision.get("corrected_label") if correction else None
            annotation_source = "HUMAN_CORRECTION" if correction else "AI"
            active = not removed
            effective_label = corrected_label or lesion["canonical_label"]
            effective_geometry = decision.get("corrected_rectangle") or [x1, y1, x2, y2]
            ex1, ey1, ex2, ey2 = effective_geometry
            rows.append({
                "annotation_id": detection_id,
                "image_id": image_id,
                "label": effective_label,
                "shape_type": "rectangle",
                "geometry_json": _geometry_json({"x": ex1, "y": ey1, "width": ex2 - ex1, "height": ey2 - ey1}),
                "annotation_source": annotation_source,
                "reviewer": decision.get("reviewer") if decision else None,
                "created_at": decision.get("timestamp") if decision else None,
                "model_id": lesion_result.get("model_id") or global_result.get("model_id"),
                "model_version": lesion_result.get("model_version") or global_result.get("model_version"),
                "score": None if correction else lesion.get("score"),
                "verification_status": "CLINICIAN_CONFIRMED" if annotation_confirmed and active else ("REMOVED" if removed else "AI_ONLY"),
                # Case-level annotation confirmation does not confirm an untouched
                # AI proposal. Only the explicit correction path can become gold.
                "include_in_training": bool(correction and lesion_ready and active),
                "eligibility_reason": "ELIGIBLE" if correction and lesion_ready and active else (
                    "REMOVED_FROM_ACTIVE_SET" if removed else "AI_ONLY_UNVERIFIED"
                ),
                "source_detection_id": detection_id if correction else None,
                "original_label": lesion["canonical_label"],
                "original_score": lesion.get("score"),
                "original_geometry_json": _geometry_json({"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}),
            })
        for index, annotation in enumerate(human_annotations):
            label = annotation.get("label")
            if label not in CANONICAL_LABELS:
                raise DatasetManifestError("Human annotation uses a non-canonical lesion label")
            human_ready = bool(lesion_ready)
            rows.append({
                "annotation_id": annotation.get("shape_id") or f"human-{image_id}-{index}",
                "image_id": image_id,
                "label": label,
                "shape_type": annotation.get("type"),
                "geometry_json": _geometry_json(annotation.get("geometry")),
                "annotation_source": "HUMAN",
                "reviewer": annotation.get("reviewer") or None,
                "created_at": annotation.get("created_at"),
                "model_id": None,
                "model_version": None,
                "score": None,
                "verification_status": "CLINICIAN_CONFIRMED" if annotation_confirmed else "HUMAN_DRAFT",
                "include_in_training": human_ready,
                "eligibility_reason": "ELIGIBLE" if human_ready else (
                    image_reason if not image_include else "ANNOTATION_NOT_VERIFIED"
                ),
                "source_detection_id": annotation.get("source_detection_id"),
                "original_label": None,
                "original_score": None,
                "original_geometry_json": None,
            })
        confirmation = next(
            (event for event in reversed(case.get("review_history") or [])
             if event.get("review_action") == "CONFIRM_ANNOTATIONS"),
            None,
        )
        imported_ready = bool(annotation_confirmed and annotation_confirmation.get("reviewer") and annotation_confirmation.get("timestamp"))
        for index, annotation in enumerate(imported_annotations):
            label = annotation.get("canonical_label")
            if label not in CANONICAL_LABELS:
                raise DatasetManifestError("Imported annotation uses a non-canonical lesion label")
            shape_type, geometry = _imported_geometry(annotation.get("geometry") or {})
            ready = bool(imported_ready and image_include)
            remote_id = annotation.get("remote_id")
            annotation_id = remote_id if remote_id is not None else index
            rows.append({
                "annotation_id": f"cvat-{image_id}-{annotation_id}",
                "image_id": image_id,
                "label": label,
                "shape_type": shape_type,
                "geometry_json": _geometry_json(geometry),
                "annotation_source": "CVAT_IMPORTED",
                "reviewer": confirmation.get("reviewer") if confirmation else None,
                "created_at": confirmation.get("timestamp") if confirmation else None,
                "model_id": None,
                "model_version": None,
                "score": None,
                "verification_status": "CLINICIAN_CONFIRMED" if imported_ready else "UNVERIFIED",
                "include_in_training": ready,
                "eligibility_reason": "ELIGIBLE" if ready else (
                    image_reason if not image_include else "ANNOTATION_NOT_VERIFIED"
                ),
                "source_detection_id": None,
                "original_label": None,
                "original_score": None,
                "original_geometry_json": None,
            })
        return rows

    def preview(self, *, include_annotations: bool = True) -> dict:
        with self._read_snapshot_cases() as snapshot_cases:
            cases = self._merge_case_records(snapshot_cases) if not hasattr(self.app.state.store, "repeatable_read_cases") else list(snapshot_cases)
            images, annotations = self._rows(cases)
            source_state = _source_state_receipt(self._workspace_context()[0], cases)
        workspace_id, workspace_name = self._workspace_context()
        response = self._response(
            images,
            annotations,
            workspace_id,
            workspace_name,
            source_state=source_state,
        )
        if not include_annotations:
            response["annotations"] = []
        return response

    @staticmethod
    def _response(
        images: list[dict],
        annotations: list[dict],
        workspace_id,
        workspace_name,
        *,
        source_state: dict | None = None,
    ) -> dict:
        ready_count = sum(bool(row["include_in_training"]) for row in images)
        dr_ready_count = sum(bool(row["dr_grade_training_ready"]) for row in images)
        lesion_ready_count = sum(bool(row["lesion_training_ready"]) for row in images)
        lesion_annotation_count = sum(bool(row["include_in_training"]) for row in annotations)
        excluded_count = sum(row["dataset_status"] == "Excluded" for row in images)
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "export_id": None,
            "created_at": _utc_now(),
            "workspace_id": workspace_id,
            "workspace_name": workspace_name,
            "image_count": len(images),
            "annotation_count": len(annotations),
            "training_ready_count": ready_count,
            "dr_grade_ready_count": dr_ready_count,
            "lesion_ready_image_count": lesion_ready_count,
            "lesion_ready_annotation_count": lesion_annotation_count,
            "needs_review_count": len(images) - ready_count - excluded_count,
            "excluded_count": excluded_count,
            "can_export": workspace_id is not None,
            "images": images,
            "annotations": annotations,
            "coordinate_system": "original_image_pixels",
            "lesion_taxonomy": sorted(CANONICAL_LABELS),
            "eligibility_policy_version": "s8.2-task-specific-v1",
            "source_state_digest_version": SOURCE_STATE_DIGEST_VERSION,
            "source_state_digest": (source_state or {}).get("digest"),
            "source_case_count": (source_state or {}).get("case_count", len(images)),
            "negative_policy_version": NEGATIVE_POLICY_VERSION,
        }

    @staticmethod
    def _source_summary(images: list[dict]) -> dict:
        summary: dict[str, int] = {}
        for row in images:
            origin = row.get("source_origin") or "UNKNOWN"
            summary[origin] = summary.get(origin, 0) + 1
        return summary

    @staticmethod
    def _authorization_summary(images: list[dict]) -> dict:
        summary: dict[str, int] = {}
        for row in images:
            authorization = row.get("export_authorization") or "BLOCKED_UNKNOWN_ORIGIN"
            summary[authorization] = summary.get(authorization, 0) + 1
        return summary

    @staticmethod
    def _readiness_match(row: dict, readiness: str) -> bool:
        if readiness in {"all", ""}:
            return True
        if readiness in {"dr-ready", "DR_READY"}:
            return bool(row.get("dr_grade_training_ready"))
        if readiness in {"lesion-positive-ready", "lesion-ready", "LESION_POSITIVE_READY"}:
            return bool(row.get("lesion_positive_training_ready"))
        if readiness in {"needs-review", "NEEDS_REVIEW"}:
            return not row.get("dr_grade_training_ready") and row.get("dataset_status") != "Excluded"
        if readiness in {"excluded", "EXCLUDED"}:
            return row.get("dataset_status") == "Excluded"
        if readiness in {"blocked", "BLOCKED"}:
            return str(row.get("export_authorization", "")).startswith("BLOCKED_")
        return False

    def _workspace_data_context(self) -> tuple[list[dict], list[dict], list[dict], dict, str | None, str | None]:
        with self._read_snapshot_cases() as snapshot_cases:
            if hasattr(self.app.state.store, "repeatable_read_cases"):
                cases = list(snapshot_cases)
            else:
                cases = self._merge_case_records(snapshot_cases)
            images, annotations = self._rows(cases)
            workspace_id, workspace_name = self._workspace_context()
            source_state = _source_state_receipt(workspace_id, cases)
        return images, annotations, cases, source_state, workspace_id, workspace_name

    def workspace_data_records(
        self,
        *,
        page: int = 1,
        limit: int = 25,
        readiness: str = "all",
        review_status: str | None = None,
        laterality: str | None = None,
        modality: str | None = None,
        source_origin: str | None = None,
        patient_grouped: bool | None = None,
        q: str | None = None,
    ) -> dict:
        page = max(1, int(page))
        limit = min(100, max(1, int(limit)))
        images, _annotations, _cases, source_state, workspace_id, workspace_name = self._workspace_data_context()
        query = (q or "").strip().casefold()
        filtered = []
        for row in images:
            if not self._readiness_match(row, readiness):
                continue
            if review_status and row.get("review_status") != review_status:
                continue
            if laterality and row.get("laterality") != laterality:
                continue
            if modality and row.get("modality") != modality:
                continue
            if source_origin and row.get("source_origin") != source_origin:
                continue
            if patient_grouped is True and not row.get("training_group_key"):
                continue
            if patient_grouped is False and row.get("training_group_key"):
                continue
            if query and not any(query in str(row.get(key) or "").casefold() for key in ("image_id", "filename", "patient_key", "training_group_key")):
                continue
            filtered.append(row)
        start = (page - 1) * limit
        records = filtered[start:start + limit]
        return {
            "schema_version": "s4.workspace-data.v1",
            "workspace_id": workspace_id,
            "workspace_name": workspace_name,
            "page": page,
            "limit": limit,
            "total": len(filtered),
            "has_next": start + limit < len(filtered),
            "filters": {
                "readiness": readiness,
                "review_status": review_status,
                "laterality": laterality,
                "modality": modality,
                "source_origin": source_origin,
                "patient_grouped": patient_grouped,
                "q": q,
            },
            "source_state_digest": source_state["digest"],
            "source_state_digest_version": SOURCE_STATE_DIGEST_VERSION,
            "source_origin_summary": self._source_summary(images),
            "export_authorization_summary": self._authorization_summary(images),
            "records": records,
        }

    def _record_detail(self, image_id: str) -> dict:
        images, annotations, cases, source_state, workspace_id, workspace_name = self._workspace_data_context()
        row = next((item for item in images if item["image_id"] == image_id), None)
        if row is None:
            raise DatasetManifestError("The requested Workspace record was not found.")
        case = next((item for item in cases if str(item.get("image_id")) == image_id), None)
        if case is None:
            raise DatasetManifestError("The requested Workspace record was not found.")
        case_annotations = [item for item in annotations if item.get("image_id") == image_id]
        evidence = review_evidence_view(case)
        review = case.get("clinician_review") or {}
        completeness = []
        for group in ("CORE", "ADVANCED"):
            value = _completeness_record(case, group)
            completeness.append({
                "group": group,
                "state": value.get("state", "NOT_REVIEWED"),
                "reviewer": value.get("reviewer"),
                "timestamp": value.get("timestamp"),
                "taxonomy_version": value.get("taxonomy_version"),
                "negative_training_authorized": False,
                "negative_eligibility_reason": "REVIEWED_NONE_FOUND_NOT_AUTHORIZED" if value.get("state") == "REVIEWED_NONE_FOUND" else "NO_EXPLICIT_NEGATIVE_POLICY",
            })
        return {
            "schema_version": "s4.workspace-data-record.v1",
            "workspace_id": workspace_id,
            "workspace_name": workspace_name,
            "source_state_digest": source_state["digest"],
            "record": row,
            "review_milestones": {
                "image_confirmation": {"status": row.get("image_confirmation_status"), "reviewer": row.get("image_confirmed_by"), "timestamp": row.get("image_confirmed_at")},
                "dr_grade": {"status": row.get("dr_grade_confirmation_status"), "reviewer": row.get("dr_grade_confirmed_by"), "timestamp": row.get("dr_grade_confirmed_at"), "provenance": row.get("grade_provenance")},
                "annotation_set": {"status": row.get("annotation_confirmation_status"), "reviewer": row.get("annotation_confirmed_by"), "timestamp": row.get("annotation_confirmed_at"), "hash": row.get("confirmed_annotation_hash")},
                "latest_review": {"reviewer": review.get("reviewer"), "timestamp": review.get("timestamp"), "action": review.get("review_action")},
            },
            "completeness": completeness,
            "gold_label_counts": {
                "dr_grade": int(bool(row.get("dr_grade_training_ready"))),
                "lesion_positive": sum(bool(item.get("include_in_training")) for item in case_annotations),
                "lesion_negative": 0,
            },
            "ai_evidence_counts": {
                "items": len(evidence.get("items", [])),
                "unresolved": evidence.get("unresolved_count", 0),
            },
            "processing": self._processing_detail(case, row),
            "explainability": self._explainability_detail(case, evidence),
        }

    @staticmethod
    def _processing_detail(case: dict, row: dict) -> dict:
        derivative = case.get("analysis_derivative") or {}
        preparation = case.get("analysis_preparation") or {}
        return {
            "status": "AVAILABLE" if derivative or preparation else "UNAVAILABLE",
            "source_sha256": row.get("source_sha256"),
            "analysis_sha256": derivative.get("analysis_sha256"),
            "representation_version": derivative.get("representation_version"),
            "transform_id": derivative.get("transform_id"),
            "coordinate_mapping": derivative.get("coordinate_mapping"),
            "model_input_identity": preparation.get("model_input_identity"),
            "preparation_status": preparation.get("status"),
        }

    @staticmethod
    def _explainability_detail(case: dict, evidence: dict) -> dict:
        explanation = case.get("explainability")
        if not isinstance(explanation, dict):
            return {
                "status": "UNAVAILABLE",
                "evidence_identity": None,
                "note": "Explainability evidence is unavailable. No new explanation was created by Phase 4.",
                "ai_evidence": evidence,
            }
        return {"status": explanation.get("status", "AVAILABLE"), "evidence_identity": explanation.get("evidence_identity"), "record": explanation, "ai_evidence": evidence}

    def workspace_data_detail(self, image_id: str) -> dict:
        return self._record_detail(image_id)

    def workspace_data_processing(self, image_id: str) -> dict:
        return self._record_detail(image_id)["processing"] | {"schema_version": "s4.workspace-data-processing.v1", "image_id": image_id}

    def workspace_data_explainability(self, image_id: str) -> dict:
        return self._record_detail(image_id)["explainability"] | {"schema_version": "s4.workspace-data-explainability.v1", "image_id": image_id}

    def snapshot_preview(self) -> dict:
        images, annotations, _cases, source_state, workspace_id, workspace_name = self._workspace_data_context()
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "workspace_id": workspace_id,
            "workspace_name": workspace_name,
            "source_state_digest": source_state,
            "case_count": len(images),
            "row_counts": {
                "records.csv": len(images),
                "dr_labels.csv": sum(bool(row.get("dr_grade_training_ready")) for row in images),
                "lesion_labels.csv": sum(bool(item.get("include_in_training")) for item in annotations),
                "review_completeness.csv": len(images) * 2,
                "ai_evidence.csv": sum(bool(row.get("ai_evidence_status") == "AVAILABLE") for row in images),
            },
            "source_origin_summary": self._source_summary(images),
            "export_authorization_summary": self._authorization_summary(images),
            "blocked_record_count": sum(str(row.get("export_authorization", "")).startswith("BLOCKED_") for row in images),
            "negative_policy_version": NEGATIVE_POLICY_VERSION,
            "can_export": workspace_id is not None and not any(str(row.get("export_authorization", "")).startswith("BLOCKED_") for row in images),
        }

    @staticmethod
    def _snapshot_records(images: list[dict]) -> list[dict]:
        return [{field: row.get(field) for field in SNAPSHOT_RECORD_FIELDS} for row in images]

    @staticmethod
    def _snapshot_completeness(images: list[dict]) -> list[dict]:
        rows = []
        for image in images:
            for group in ("CORE", "ADVANCED"):
                prefix = group.lower() + "_completeness_"
                rows.append({
                    "image_id": image.get("image_id"),
                    "group": group,
                    "state": image.get(prefix + "state"),
                    "reviewer": image.get(prefix + "reviewer"),
                    "timestamp": image.get(prefix + "at"),
                    "taxonomy_version": image.get(prefix + "taxonomy_version"),
                    "case_revision": image.get("case_revision"),
                    "annotation_set_hash": image.get("annotation_set_hash"),
                    "negative_training_authorized": False,
                    "negative_eligibility_reason": image.get("negative_eligibility_reason"),
                })
        return rows

    def _snapshot_ai_evidence(self, cases: list[dict], images: list[dict]) -> list[dict]:
        rows = []
        image_by_id = {row["image_id"]: row for row in images}
        for case in cases:
            image_id = str(case.get("image_id"))
            image = image_by_id.get(image_id)
            if image is None:
                continue
            evidence = review_evidence_view(case)
            for item in evidence.get("items", []):
                if item.get("source") != "AI":
                    continue
                rows.append({
                    "image_id": image_id,
                    "source_sha256": image.get("source_sha256"),
                    "ai_kind": "LESION_SUGGESTION",
                    "annotation_id": item.get("annotation_id"),
                    "model_id": item.get("model_id"),
                    "model_version": item.get("model_version"),
                    "score": item.get("score"),
                    "status": item.get("status"),
                    "geometry_json": _geometry_json(item.get("corrected_rectangle") or item.get("original_rectangle")) if item.get("original_rectangle") else None,
                    "source_detection_id": item.get("annotation_id"),
                    "invocation_id": (case.get("selected_ai_evidence") or {}).get("invocation_id"),
                    "analysis_sha256": evidence.get("analysis_sha256"),
                    "provenance_status": "NON_GOLD_AI_EVIDENCE",
                })
        return rows

    def export_snapshot(self) -> dict:
        workspace = self._workspace()
        if workspace is None:
            raise DatasetManifestError("Open an active Workspace before creating a canonical snapshot.")
        with self._read_snapshot_cases() as snapshot_cases:
            cases = list(snapshot_cases) if hasattr(self.app.state.store, "repeatable_read_cases") else self._merge_case_records(snapshot_cases)
            images, annotations = self._rows(cases)
            source_state = _source_state_receipt(workspace.id, cases)
            blocked = [row for row in images if str(row.get("export_authorization", "")).startswith("BLOCKED_")]
            if blocked:
                raise DatasetManifestError("Canonical snapshot is blocked because one or more records lack approved engineering export authorization.")
        snapshot_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        export_dir = Path(workspace.output_folder) / f"dataset-snapshot-{snapshot_id}"
        completeness = self._snapshot_completeness(images)
        ai_evidence = self._snapshot_ai_evidence(cases, images)
        dr_labels = [{field: row.get(field) for field in DR_LABEL_FIELDS} for row in images if row.get("dr_grade_training_ready")]
        row_by_id = {row["image_id"]: row for row in images}
        lesion_labels = []
        for item in annotations:
            if not item.get("include_in_training") or item.get("annotation_source") not in {"HUMAN", "HUMAN_CORRECTION", "CVAT_IMPORTED"}:
                continue
            row = row_by_id.get(item.get("image_id"), {})
            lesion_labels.append({
                "annotation_id": item.get("annotation_id"),
                "image_id": item.get("image_id"),
                "source_sha256": row.get("source_sha256"),
                "label": item.get("label"),
                "shape_type": item.get("shape_type"),
                "geometry_json": item.get("geometry_json"),
                "annotation_source": item.get("annotation_source"),
                "reviewer": item.get("reviewer"),
                "reviewed_at": item.get("created_at"),
                "source_detection_id": item.get("source_detection_id"),
                "case_revision": row.get("case_revision"),
                "annotation_set_hash": row.get("annotation_set_hash"),
                "confirmed_annotation_hash": row.get("confirmed_annotation_hash"),
                "policy_version": SNAPSHOT_ELIGIBILITY_POLICY_VERSION,
            })
        files = {
            "records.csv": _csv_bytes(self._snapshot_records(images), SNAPSHOT_RECORD_FIELDS),
            "dr_labels.csv": _csv_bytes(dr_labels, DR_LABEL_FIELDS),
            "lesion_labels.csv": _csv_bytes(lesion_labels, LESION_LABEL_FIELDS),
            "review_completeness.csv": _csv_bytes(completeness, COMPLETENESS_FIELDS),
            "ai_evidence.csv": _csv_bytes(ai_evidence, AI_EVIDENCE_FIELDS),
        }
        file_hashes = {name: _sha256(data) for name, data in files.items()}
        source_origins = self._source_summary(images)
        authorizations = self._authorization_summary(images)
        manifest = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "created_at": _utc_now(),
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "application_version": getattr(self.app, "version", None),
            "git_commit": None,
            "eligibility_policy_version": SNAPSHOT_ELIGIBILITY_POLICY_VERSION,
            "taxonomy_versions": {"lesion": "canonical-v1", "completeness": "phase2-core-advanced-v1"},
            "coordinate_system": "original_image_pixels",
            "source_state_digest": source_state,
            "case_count": len(images),
            "files": ["manifest.json", *files.keys(), "receipt.json"],
            "file_sha256": file_hashes,
            "row_counts": {"records.csv": len(images), "dr_labels.csv": len(dr_labels), "lesion_labels.csv": len(lesion_labels), "review_completeness.csv": len(completeness), "ai_evidence.csv": len(ai_evidence)},
            "source_origin_summary": source_origins,
            "export_authorization_summary": authorizations,
            "negative_policy": {"version": NEGATIVE_POLICY_VERSION, "training_negative_authorized": False, "reviewed_none_found_is_completeness_only": True},
            "patient_grouping_policy": "confirmed_resolved_pseudonymous_identity_only; no automatic split",
            "model_evidence_inclusion_policy": "ai_evidence.csv is NON_GOLD and never required to discover human labels",
            "limitations": ["Snapshot contains metadata and labels; source images are not copied.", "Live PostgreSQL qualification is environment-dependent."],
            "status": "SUCCESS",
        }
        receipt = {
            "snapshot_id": snapshot_id,
            "workspace_id": workspace.id,
            "created_at": manifest["created_at"],
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "policy_version": SNAPSHOT_ELIGIBILITY_POLICY_VERSION,
            "source_state_digest": source_state,
            "case_revisions": source_state["case_revisions"],
            "file_sha256": file_hashes,
            "row_counts": manifest["row_counts"],
            "source_origin_summary": source_origins,
            "authorization_status": authorizations,
            "status": "SUCCESS",
        }
        try:
            export_dir.mkdir(parents=False, exist_ok=False)
            (export_dir / "manifest.json").write_bytes(_canonical_json_bytes(manifest))
            for name, data in files.items():
                (export_dir / name).write_bytes(data)
            (export_dir / "receipt.json").write_bytes(_canonical_json_bytes(receipt))
        except Exception:
            if export_dir.exists():
                shutil.rmtree(export_dir)
            raise
        return {"schema_version": SNAPSHOT_SCHEMA_VERSION, "snapshot_id": snapshot_id, "workspace_id": workspace.id, "workspace_name": workspace.name, "directory_name": export_dir.name, "manifest": manifest, "receipt": receipt}

    def snapshot_detail(self, snapshot_id: str) -> dict:
        if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}", snapshot_id):
            raise DatasetManifestError("The requested snapshot identifier is invalid.")
        workspace = self._workspace()
        if workspace is None:
            raise DatasetManifestError("Open an active Workspace before inspecting a snapshot.")
        directory = (Path(workspace.output_folder) / f"dataset-snapshot-{snapshot_id}").resolve()
        root = Path(workspace.output_folder).resolve()
        if not directory.is_relative_to(root):
            raise DatasetManifestError("The requested snapshot is outside the Workspace output folder.")
        manifest_path = directory / "manifest.json"
        receipt_path = directory / "receipt.json"
        if not manifest_path.is_file() or not receipt_path.is_file():
            raise DatasetManifestError("The requested snapshot was not found.")
        try:
            return {"manifest": json.loads(manifest_path.read_text(encoding="utf-8")), "receipt": json.loads(receipt_path.read_text(encoding="utf-8"))}
        except (OSError, ValueError) as error:
            raise DatasetManifestError("The requested snapshot could not be read.") from error

    def export(self) -> dict:
        workspace = self._workspace()
        if workspace is None:
            raise DatasetManifestError("Open an active Workspace before exporting a dataset manifest.")
        with self._read_snapshot_cases() as snapshot_cases:
            cases = list(snapshot_cases) if hasattr(self.app.state.store, "repeatable_read_cases") else self._merge_case_records(snapshot_cases)
            images, annotations = self._rows(cases)
            source_state = _source_state_receipt(workspace.id, cases)
        created_at = _utc_now()
        export_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        output_root = Path(workspace.output_folder)
        output_root.mkdir(parents=True, exist_ok=True)
        export_dir = output_root / f"dataset-export-{export_id}"
        try:
            export_dir.mkdir(exist_ok=False)
            images_bytes = _csv_bytes(images, IMAGE_FIELDS)
            annotations_bytes = _csv_bytes(annotations, ANNOTATION_FIELDS)
            manifest = {
                "schema_version": EXPORT_SCHEMA_VERSION,
                "export_id": export_id,
                "created_at": created_at,
                "workspace_id": workspace.id,
                "workspace_name": workspace.name,
                "application_version": getattr(self.app, "version", None),
                "image_count": len(images),
                "annotation_count": len(annotations),
                "training_ready_count": sum(bool(row["include_in_training"]) for row in images),
                "dr_grade_ready_count": sum(bool(row["dr_grade_training_ready"]) for row in images),
                "lesion_ready_image_count": sum(bool(row["lesion_training_ready"]) for row in images),
                "lesion_ready_annotation_count": sum(bool(row["include_in_training"]) for row in annotations),
                "coordinate_system": "original_image_pixels",
                "lesion_taxonomy": sorted(CANONICAL_LABELS),
                "eligibility_policy_version": "s8.2-task-specific-v1",
                "source_state_digest_version": SOURCE_STATE_DIGEST_VERSION,
                "source_state_digest": source_state,
                "negative_policy_version": NEGATIVE_POLICY_VERSION,
                "grouping_policy": "patient_key_only; no automatic train-validation-test split",
                "excluded_count": sum(row["dataset_status"] == "Excluded" for row in images),
                "files": ["manifest.json", "images.csv", "annotations.csv"],
                "file_sha256": {
                    "images.csv": _sha256(images_bytes),
                    "annotations.csv": _sha256(annotations_bytes),
                },
            }
            manifest["images_csv_sha256"] = manifest["file_sha256"]["images.csv"]
            manifest["annotations_csv_sha256"] = manifest["file_sha256"]["annotations.csv"]
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            (export_dir / "manifest.json").write_bytes(manifest_bytes)
            (export_dir / "images.csv").write_bytes(images_bytes)
            (export_dir / "annotations.csv").write_bytes(annotations_bytes)
        except Exception:
            if export_dir.exists():
                shutil.rmtree(export_dir)
            raise
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "export_id": export_id,
            "created_at": created_at,
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "directory_name": export_dir.name,
            "image_count": len(images),
            "annotation_count": len(annotations),
            "training_ready_count": sum(bool(row["include_in_training"]) for row in images),
            "files": ["manifest.json", "images.csv", "annotations.csv"],
        }

    def export_grouped(self, *, image_format: str = "PNG", jpeg_quality: int = 90) -> dict:
        workspace = self._workspace()
        if workspace is None:
            raise DatasetManifestError("Open an active Workspace before exporting reviewed images.")
        if image_format not in {"PNG", "JPEG"}:
            raise DatasetManifestError("Choose PNG or JPEG for grouped image export.")

        grouped_root = Path(workspace.output_folder) / "grouped_by_grade"
        manifest_dir = grouped_root / "_manifest"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / "grouped_export_manifest.json"
        csv_path = manifest_dir / "grouped_images.csv"

        prior_items: list[dict] = []
        if manifest_path.is_file():
            try:
                previous = json.loads(manifest_path.read_text(encoding="utf-8"))
                for entry in previous.get("items", []):
                    relative = Path(entry.get("output_path", ""))
                    candidate = (grouped_root / relative).resolve()
                    if (relative.is_absolute() or ".." in relative.parts
                            or not candidate.is_relative_to(grouped_root.resolve())
                            or not candidate.is_file()):
                        continue
                    if _sha256(candidate.read_bytes()) == entry.get("export_sha256"):
                        prior_items.append(entry)
            except (OSError, ValueError, TypeError, AttributeError):
                prior_items = []

        run_items: list[dict] = []
        copied_count = 0
        identical_count = 0
        skipped_count = 0
        store = self.app.state.store
        with store.lock:
            snapshots = [
                (image_id, *self._case_context(image_id, store))
                for image_id in self._image_ids()
            ]

        for image_id, case, image, admission in snapshots:
            group, grade = _grade_group(case, admission)
            source_sha256 = image.sha256 if image is not None else (admission or {}).get("source_sha256")
            item = {
                "image_id": image_id,
                "group": group,
                "final_grade": grade,
                "source_sha256": source_sha256 if _is_sha256(source_sha256) else None,
                "source_was_dicom": bool(
                    (image and (image.media_type == "application/dicom"
                                or Path(image.filename).suffix.lower() in {".dcm", ".dicom"}))
                    or (admission or {}).get("source_format") == "DICOM"
                    or (admission or {}).get("source_media_type") == "application/dicom"
                ),
                "rendered_derivative_sha256": None,
                "export_format": image_format,
                "export_sha256": None,
                "output_path": None,
                "status": "SKIPPED_SOURCE_UNAVAILABLE",
            }
            if (admission or {}).get("modality_admission") != "FUNDUS_ACCEPTED":
                item["status"] = "SKIPPED_NOT_FUNDUS_ACCEPTED"
                skipped_count += 1
                run_items.append(item)
                continue
            if image is None:
                skipped_count += 1
                run_items.append(item)
                continue

            try:
                image_bytes, rendered_sha256, source_was_dicom = _grouped_image_bytes(
                    image, image_format, jpeg_quality, self.app.state.derivatives
                )
            except DerivativeError as error:
                item["status"] = f"SKIPPED_UNSUPPORTED_{error.status.value}"
                skipped_count += 1
                run_items.append(item)
                continue
            except DatasetManifestError:
                item["status"] = "SKIPPED_DECODE_FAILED"
                skipped_count += 1
                run_items.append(item)
                continue

            export_sha256 = _sha256(image_bytes)
            item["source_was_dicom"] = source_was_dicom
            item["rendered_derivative_sha256"] = rendered_sha256
            item["export_sha256"] = export_sha256
            extension = "png" if image_format == "PNG" else "jpg"
            base = f"case_{source_sha256[:24]}__{group}"
            target_dir = grouped_root / group
            target_dir.mkdir(parents=True, exist_ok=True)
            suffix = 1
            while True:
                name = f"{base}.{extension}" if suffix == 1 else f"{base}__{suffix}.{extension}"
                target = target_dir / name
                try:
                    with target.open("xb") as output:
                        output.write(image_bytes)
                    item["status"] = "COPIED"
                    copied_count += 1
                    break
                except FileExistsError:
                    if _sha256(target.read_bytes()) == export_sha256:
                        item["status"] = "IDENTICAL_EXISTING"
                        identical_count += 1
                        break
                    suffix += 1
            item["output_path"] = target.relative_to(grouped_root).as_posix()
            run_items.append(item)

        merged = {entry["output_path"]: entry for entry in prior_items if entry.get("output_path")}
        skipped = [entry for entry in prior_items if not entry.get("output_path")]
        for item in run_items:
            if item["output_path"]:
                merged[item["output_path"]] = item
            else:
                skipped.append(item)
        items = [*merged.values(), *skipped]
        items.sort(key=lambda entry: (str(entry.get("group", "")), str(entry.get("image_id", "")), str(entry.get("output_path", ""))))
        csv_bytes = _csv_bytes(items, GROUPED_EXPORT_FIELDS)
        file_hashes = {
            entry["output_path"]: entry["export_sha256"]
            for entry in items if entry.get("output_path") and entry.get("export_sha256")
        }
        manifest = {
            "schema_version": "s1.grouped-grade-export.v1",
            "created_at": _utc_now(),
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "grouping_policy": "final clinician grade; unresolved cases are separated without changing source files",
            "source_immutability": "copy_only",
            "format": image_format,
            "jpeg_quality": jpeg_quality if image_format == "JPEG" else None,
            "item_count": len(items),
            "copied_count": copied_count,
            "identical_existing_count": identical_count,
            "skipped_count": skipped_count,
            "items": items,
            "files": {
                "grouped_images.csv": _sha256(csv_bytes),
                "images": file_hashes,
            },
        }
        csv_path.write_bytes(csv_bytes)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return {
            "directory_name": "grouped_by_grade",
            "image_format": image_format,
            "copied_count": copied_count,
            "identical_existing_count": identical_count,
            "skipped_count": skipped_count,
            "manifest": "_manifest/grouped_export_manifest.json",
        }
