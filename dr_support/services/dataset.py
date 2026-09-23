"""Derived dataset manifest and non-destructive workspace export."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .admission import legacy_admission
from ..presentation import annotation_set_hash, lesion_detection_id
from ..imaging import DerivativeError
from .resolver import normalize_patient_key


EXPORT_SCHEMA_VERSION = "s4.dataset-manifest.v2"
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


class DatasetManifestError(RuntimeError):
    """An expected dataset preview/export failure."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(SHA256_PATTERN.fullmatch(value))


def _pseudonymous_patient_key(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return normalize_patient_key(value)
    except ValueError:
        return None


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
    if case.get("state") == "ESCALATED" or review.get("review_action") == "ESCALATE":
        return "senior_review", None
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
    """Build S4 rows from authoritative in-memory admission and SQLite records."""

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
        grade = case.get("reviewed_grade")
        if grade is None:
            grade = review.get("final_grade")
        return grade, case.get("grade_review_source"), review

    @staticmethod
    def _case_eligibility(case: dict, image, admission: dict | None) -> tuple[bool, str]:
        image_sha256 = image.sha256 if image is not None else (
            admission.get("image_id") if admission else None
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

    def _rows(self) -> tuple[list[dict], list[dict]]:
        image_rows: list[dict] = []
        annotation_rows: list[dict] = []
        store = self.app.state.store
        with store.lock:
            for image_id in self._image_ids():
                case, image, admission = self._case_context(image_id, store)
                include, eligibility_reason = self._case_eligibility(case, image, admission)
                grade, grade_source, review = self._final_grade(case)
                grade_confirmation_status, grade_confirmed_by, grade_confirmed_at = self._grade_confirmation(
                    case, grade, review
                )
                image_confirmation_status, image_confirmed_by, image_confirmed_at = self._image_confirmation(case, admission)
                grade_reason = self._task_reason(case, admission, image, image_confirmation_status == "CONFIRMED", task="grade")
                annotation_confirmed, annotation_confirmation = self._annotation_confirmation(case)
                current_annotation_hash = case.get("annotation_hash") or annotation_set_hash(case)
                lesion_reason = self._task_reason(case, admission, image, image_confirmation_status == "CONFIRMED", task="lesion")
                grade_ready = grade_reason == "ELIGIBLE" and include
                lesion_ready = lesion_reason == "ELIGIBLE"
                patient_key = _pseudonymous_patient_key(case.get("patient_key"))
                global_result = case.get("global") or {}
                lesion_result = case.get("lesion") or {}
                human_annotations = case.get("human_annotations") or []
                imported_annotations = case.get("annotations") or []
                image_sha256 = image.sha256 if image is not None else (
                    admission.get("image_id") if admission else None
                )
                filename = (admission or {}).get("filename") or (image.filename if image is not None else image_id)
                row = {
                    "image_id": image_id,
                    "filename": filename,
                    "image_sha256": image_sha256 if _is_sha256(image_sha256) else None,
                    "width": (admission or {}).get("width"),
                    "height": (admission or {}).get("height"),
                    "modality": image.modality if image is not None else None,
                    "source_type": image.source_type if image is not None else None,
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
                    "review_status": "CLINICIAN_REVIEWED" if grade is not None else (
                        "AI_ONLY" if global_result or lesion_result else "UNVERIFIED"
                    ),
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
                    "training_group_key": f"patient:{patient_key}" if patient_key else None,
                }
                image_rows.append(row)
                annotation_rows.extend(
                    self._annotation_rows(case, row, global_result, lesion_result, human_annotations,
                                          imported_annotations, include, eligibility_reason, lesion_ready,
                                          annotation_confirmed, annotation_confirmation)
                )
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
            corrected_label = decision.get("corrected_label") if decision.get("action") == "CORRECT" else None
            annotation_source = "HUMAN_CORRECTION" if corrected_label else "AI"
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
                "score": None if corrected_label else lesion.get("score"),
                "verification_status": "CLINICIAN_CONFIRMED" if annotation_confirmed and active else ("REMOVED" if removed else "AI_ONLY"),
                "include_in_training": bool(lesion_ready and active),
                "eligibility_reason": "ELIGIBLE" if lesion_ready and active else (
                    "REMOVED_FROM_ACTIVE_SET" if removed else (image_reason if not image_include else "AI_ONLY_UNVERIFIED")
                ),
                "source_detection_id": detection_id if corrected_label else None,
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
        images, annotations = self._rows()
        workspace_id, workspace_name = self._workspace_context()
        response = self._response(images, annotations, workspace_id, workspace_name)
        if not include_annotations:
            response["annotations"] = []
        return response

    @staticmethod
    def _response(images: list[dict], annotations: list[dict], workspace_id, workspace_name) -> dict:
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
        }

    def export(self) -> dict:
        workspace = self._workspace()
        if workspace is None:
            raise DatasetManifestError("Open an active Workspace before exporting a dataset manifest.")
        images, annotations = self._rows()
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
        for name in [*(f"dr_grade_{grade}" for grade in range(5)), "ungradable", "needs_review", "senior_review"]:
            (grouped_root / name).mkdir(parents=True, exist_ok=True)
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
