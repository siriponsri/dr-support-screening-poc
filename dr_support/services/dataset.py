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


EXPORT_SCHEMA_VERSION = "s4.dataset-manifest.v1"
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
]


class DatasetManifestError(RuntimeError):
    """An expected dataset preview/export failure."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(SHA256_PATTERN.fullmatch(value))


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

    def _rows(self) -> tuple[list[dict], list[dict]]:
        image_rows: list[dict] = []
        annotation_rows: list[dict] = []
        store = self.app.state.store
        with store.lock:
            for image_id in self._image_ids():
                case, image, admission = self._case_context(image_id, store)
                include, eligibility_reason = self._case_eligibility(case, image, admission)
                grade, grade_source, review = self._final_grade(case)
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
                    "patient_key": case.get("patient_key"),
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
                }
                image_rows.append(row)
                annotation_rows.extend(
                    self._annotation_rows(case, row, global_result, lesion_result, human_annotations,
                                          imported_annotations, include, eligibility_reason)
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
    ) -> list[dict]:
        image_id = image_row["image_id"]
        rows: list[dict] = []
        for index, lesion in enumerate(lesion_result.get("lesions") or []):
            x1, y1, x2, y2 = lesion["rectangle"]
            rows.append({
                "annotation_id": f"ai-{image_id}-{index}",
                "image_id": image_id,
                "label": lesion["canonical_label"],
                "shape_type": "rectangle",
                "geometry_json": _geometry_json({"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}),
                "annotation_source": "AI",
                "reviewer": None,
                "created_at": None,
                "model_id": lesion_result.get("model_id") or global_result.get("model_id"),
                "model_version": lesion_result.get("model_version") or global_result.get("model_version"),
                "score": lesion.get("score"),
                "verification_status": "AI_ONLY",
                "include_in_training": False,
                "eligibility_reason": image_reason if not image_include else "AI_ONLY_UNVERIFIED",
            })
        for index, annotation in enumerate(human_annotations):
            label = annotation.get("label")
            if label not in CANONICAL_LABELS:
                raise DatasetManifestError("Human annotation uses a non-canonical lesion label")
            human_ready = False  # The current editor has no finality flag for human drafts.
            rows.append({
                "annotation_id": annotation.get("shape_id") or f"human-{image_id}-{index}",
                "image_id": image_id,
                "label": label,
                "shape_type": annotation.get("type"),
                "geometry_json": _geometry_json(annotation.get("geometry")),
                "annotation_source": "HUMAN",
                "reviewer": annotation.get("reviewer"),
                "created_at": annotation.get("created_at"),
                "model_id": None,
                "model_version": None,
                "score": None,
                "verification_status": "HUMAN_AUTHORED",
                "include_in_training": human_ready,
                "eligibility_reason": image_reason if not image_include else "ANNOTATION_NOT_VERIFIED",
            })
        confirmation = next(
            (event for event in reversed(case.get("review_history") or [])
             if event.get("review_action") == "CONFIRM_ANNOTATIONS"),
            None,
        )
        confirmed = bool(
            case.get("lesion_review_state") == "REVIEWED"
            and case.get("annotation_hash")
            and case.get("annotation_hash") == case.get("confirmed_annotation_hash")
        )
        imported_ready = confirmed and bool(confirmation and confirmation.get("reviewer") and confirmation.get("timestamp"))
        for index, annotation in enumerate(imported_annotations):
            label = annotation.get("canonical_label")
            if label not in CANONICAL_LABELS:
                raise DatasetManifestError("Imported annotation uses a non-canonical lesion label")
            shape_type, geometry = _imported_geometry(annotation.get("geometry") or {})
            ready = bool(imported_ready and image_include)
            rows.append({
                "annotation_id": f"cvat-{image_id}-{annotation.get('remote_id', index)}",
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
                "verification_status": "CONFIRMED" if confirmed else "UNVERIFIED",
                "include_in_training": ready,
                "eligibility_reason": "ELIGIBLE" if ready else (
                    image_reason if not image_include else "ANNOTATION_NOT_VERIFIED"
                ),
            })
        return rows

    def preview(self) -> dict:
        images, annotations = self._rows()
        workspace_id, workspace_name = self._workspace_context()
        return self._response(images, annotations, workspace_id, workspace_name)

    @staticmethod
    def _response(images: list[dict], annotations: list[dict], workspace_id, workspace_name) -> dict:
        ready_count = sum(bool(row["include_in_training"]) for row in images)
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
            "needs_review_count": len(images) - ready_count - excluded_count,
            "excluded_count": excluded_count,
            "can_export": workspace_id is not None,
            "images": images,
            "annotations": annotations,
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
