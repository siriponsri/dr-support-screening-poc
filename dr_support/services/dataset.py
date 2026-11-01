"""Derived dataset manifest and non-destructive workspace export."""

from __future__ import annotations

import json
import shutil
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .admission import legacy_admission
from .source_identity import source_identity_reason
from .source_policy import (
    LOCAL_ONLY_EXPORTS,
    local_export_destination_reason,
)
from ..presentation import annotation_set_hash, lesion_detection_id, review_evidence_view
from ..referral import current_referral


def _grade_group(case: dict, admission: dict | None) -> tuple[str, int | None]:
    if (admission or {}).get("quality_state") == "UNGRADABLE":
        return "ungradable", None
    review = case.get("clinician_review") or {}
    if (
        case.get("grade_status") == "NEEDS_SECOND_REVIEW"
        or case.get("state") in {"ESCALATED", "NEEDS_SECOND_REVIEW"}
        or review.get("review_action") == "ESCALATE"
    ):
        return "senior_review", None
    if case.get("grade_status") == "UNGRADABLE" or review.get("review_action") == "MARK_UNGRADABLE":
        return "ungradable", None
    grade, source, _ = DatasetManifestService._final_grade(case)
    if isinstance(grade, int) and not isinstance(grade, bool) and grade in range(5) and source in {
        "AI_ACCEPTED", "AI_CORRECTED", "MANUAL",
    }:
        return f"dr_grade_{grade}", grade
    return "needs_review", None


def _ai_grade_group(case: dict, admission: dict | None) -> tuple[str, int | None]:
    """Archive sorting by the AI-predicted grade only: never a clinical grade or a training label."""
    if (admission or {}).get("quality_state") == "UNGRADABLE":
        return "ungradable", None   # A person judged it ungradable; never filed as a grade, never as normal.
    grade = (case.get("global") or {}).get("grade")
    if isinstance(grade, int) and not isinstance(grade, bool) and grade in range(5):
        return f"ai_grade_{grade}", grade
    return "no_ai_result", None


# Shared helpers and the grouped/snapshot halves live in dataset_common.py, dataset_snapshot.py and
# dataset_grouped.py. They are imported here so existing `from ...services.dataset import X` keeps working.
from .dataset_common import (  # noqa: F401
    _canonical_json_bytes,
    _completeness_record,
    _confirmed_patient_group_key,
    _csv_bytes,
    _export_authorization,
    _float,
    _geometry_json,
    _imported_geometry,
    _is_sha256,
    _pseudonymous_patient_key,
    _sha256,
    _source_origin,
    _source_state_receipt,
    _utc_now,
    AI_EVIDENCE_FIELDS,
    ANNOTATION_FIELDS,
    CANONICAL_LABELS,
    COMPLETENESS_FIELDS,
    DatasetManifestError,
    DR_LABEL_FIELDS,
    ENGINEERING_EXPORT_AUTHORIZATION,
    EXPORT_SCHEMA_VERSION,
    IMAGE_FIELDS,
    label_class,
    LEGACY_ELIGIBILITY_POLICY_VERSION,
    LESION_LABEL_FIELDS,
    NEGATIVE_POLICY_VERSION,
    SHA256_PATTERN,
    SNAPSHOT_ELIGIBILITY_POLICY_VERSION,
    SNAPSHOT_RECORD_FIELDS,
    SNAPSHOT_SCHEMA_VERSION,
    SOURCE_ORIGINS,
    SOURCE_STATE_DIGEST_VERSION,
    TEST_ONLY_MARKER,
)
from .dataset_grouped import (  # noqa: F401
    _grouped_image_bytes,
    AI_PREDICTED_DIRECTORY,
    GROUPED_EXPORT_FIELDS,
    GroupedExportMixin,
)
from .dataset_snapshot import SnapshotExportMixin


class DatasetManifestService(SnapshotExportMixin, GroupedExportMixin):
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
        status = case.get("grade_status")
        if status is not None and status != "CONFIRMED":
            return None, case.get("grade_review_source"), review
        grade = case.get("reviewed_grade")
        if grade is None:
            grade = review.get("final_grade")
        # Export boundaries must not trust numeric caches from malformed or
        # historical records more than the explicit physician decision.
        if type(grade) is not int or grade not in range(5):
            return None, case.get("grade_review_source"), review
        final_grade = review.get("final_grade")
        # A cache is never a substitute for an explicit physician decision,
        # including historical records whose status/action fields are absent.
        if type(final_grade) is not int or final_grade not in range(5) or final_grade != grade:
            return None, case.get("grade_review_source"), review
        action = review.get("review_action")
        if action is not None and action not in {"ACCEPT", "CORRECT_GRADE", "ADJUDICATE_GRADE"}:
            return None, case.get("grade_review_source"), review
        revision = review.get("revision")
        case_revision = case.get("revision")
        if revision is not None and (
            type(revision) is not int or revision < 1
            or (type(case_revision) is int and revision > case_revision)
        ):
            return None, case.get("grade_review_source"), review
        return grade, case.get("grade_review_source"), review

    @staticmethod
    def _case_eligibility(case: dict, image, admission: dict | None) -> tuple[bool, str]:
        source_failure = source_identity_reason(case, image, admission)
        if source_failure:
            return False, source_failure
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
        if review.get("source_sha256") not in {None, image.sha256}:
            return False, "SOURCE_HASH_MISMATCH"
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
        current_hash = annotation_set_hash(case)
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
        source_failure = source_identity_reason(case, image, admission)
        if source_failure:
            return source_failure
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
            if review.get("source_sha256") not in {None, image.sha256}:
                return "SOURCE_HASH_MISMATCH"
        else:
            confirmed, confirmation = DatasetManifestService._annotation_confirmation(case)
            if not confirmed:
                return "NO_ANNOTATION_CONFIRMATION"
            if not confirmation.get("reviewer") or not confirmation.get("timestamp"):
                return "MISSING_PROVENANCE"
            if confirmation.get("source_sha256") not in {None, image.sha256}:
                return "SOURCE_HASH_MISMATCH"
        return "ELIGIBLE"

    def _rows(self, cases: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
        image_rows: list[dict] = []
        annotation_rows: list[dict] = []
        cases = self._case_records() if cases is None else cases
        workspace = self._workspace()
        for case in cases:
            image_id = str(case.get("image_id"))
            image = getattr(self.app.state, "images", {}).get(image_id)
            admission = case.get("admission") or getattr(self.app.state, "admissions", {}).get(image_id)
            if admission is None and image is not None:
                admission = legacy_admission(image)
            include, eligibility_reason = self._case_eligibility(case, image, admission)
            labels = label_class(case, admission, workspace)
            if labels == "TEST_ONLY" and include:
                include, eligibility_reason = False, "TEST_ONLY_LABEL"
            grade, grade_source, review = self._final_grade(case)
            grade_confirmation_status, grade_confirmed_by, grade_confirmed_at = self._grade_confirmation(
                case, grade, review
            )
            image_confirmation_status, image_confirmed_by, image_confirmed_at = self._image_confirmation(
                case, admission
            )
            grade_reason = self._task_reason(
                case, admission, image, image_confirmation_status == "CONFIRMED", task="grade"
            )
            annotation_confirmed, annotation_confirmation = self._annotation_confirmation(case)
            current_annotation_hash = annotation_set_hash(case)
            lesion_reason = self._task_reason(
                case, admission, image, image_confirmation_status == "CONFIRMED", task="lesion"
            )
            if labels == "TEST_ONLY":
                grade_reason = "TEST_ONLY_LABEL" if grade_reason == "ELIGIBLE" else grade_reason
                lesion_reason = "TEST_ONLY_LABEL" if lesion_reason == "ELIGIBLE" else lesion_reason
            grade_ready = grade_reason == "ELIGIBLE" and include
            lesion_ready = lesion_reason == "ELIGIBLE"
            global_result = case.get("global") or {}
            lesion_result = case.get("lesion") or {}
            human_annotations = case.get("human_annotations") or []
            imported_annotations = case.get("annotations") or []
            source_origin = _source_origin(case, image, admission)
            export_authorization = _export_authorization(source_origin)
            if source_origin == "HOSPITAL_AUTHORIZED" and (
                image is None or getattr(image, "source_origin", None) != source_origin
                or (admission or {}).get("source_origin") != source_origin
                or source_identity_reason(case, image, admission) is not None
                or any(case.get(key) not in {None, image.sha256}
                       for key in ("image_sha256", "source_sha256"))
            ):
                export_authorization = "BLOCKED_SOURCE_IDENTITY_OR_AUTHORIZATION_MISMATCH"
            image_sha256 = image.sha256 if image is not None else (admission or {}).get("source_sha256")
            filename = (admission or {}).get("filename") or (image.filename if image is not None else image_id)
            core_completeness = _completeness_record(case, "CORE")
            advanced_completeness = _completeness_record(case, "ADVANCED")
            referral = current_referral(case)
            row = {
                "image_id": image_id,
                "filename": filename,
                "image_sha256": image_sha256 if _is_sha256(image_sha256) else None,
                "source_sha256": image_sha256 if _is_sha256(image_sha256) else None,
                "width": (admission or {}).get("width"),
                "height": (admission or {}).get("height"),
                "modality": (admission or {}).get("retinal_modality", "UNKNOWN")
                if image is not None
                else None,
                "source_type": image.source_type if image is not None else None,
                "source_origin": source_origin,
                "source_available": image is not None,
                "source_integrity_status": (admission or {}).get("integrity_status", "UNKNOWN"),
                "export_authorization": export_authorization,
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
                "referral_status": referral["status"],
                "referral_rule_id": referral["rule_id"],
                "referral_rule_version": referral["rule_version"],
                "referral_source_grade_revision": referral["source_grade_revision"],
                "referral_reviewer": referral["reviewer"],
                "referral_reviewed_at": referral["timestamp"],
                "review_status": "CLINICIAN_REVIEWED"
                if grade is not None
                else ("AI_ONLY" if global_result or lesion_result else "UNVERIFIED"),
                "reviewer": review.get("reviewer"),
                "reviewed_at": review.get("timestamp"),
                "human_annotation_count": len(human_annotations),
                "ai_lesion_count": len(lesion_result.get("lesions") or []),
                "cvat_annotation_count": len(imported_annotations),
                "verification_status": self._image_verification(case, admission, include),
                "include_in_training": include,
                "label_class": labels,
                "eligibility_reason": eligibility_reason,
                "dataset_status": (
                    "Test data (not for training)"
                    if labels == "TEST_ONLY" and eligibility_reason == "TEST_ONLY_LABEL"
                    else self._dataset_status(case, admission, include, image)
                ),
                "image_confirmation_status": image_confirmation_status,
                "image_confirmed_by": image_confirmed_by,
                "image_confirmed_at": image_confirmed_at,
                "dr_grade_confirmation_status": grade_confirmation_status,
                "dr_grade_confirmed_by": grade_confirmed_by,
                "dr_grade_confirmed_at": grade_confirmed_at,
                "annotation_confirmation_status": "CONFIRMED" if annotation_confirmed else "DRAFT",
                "annotation_confirmed_by": annotation_confirmation.get("reviewer")
                if annotation_confirmed
                else None,
                "annotation_confirmed_at": annotation_confirmation.get("timestamp")
                if annotation_confirmed
                else None,
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
                "negative_eligibility_reason": "REVIEWED_NONE_FOUND_NOT_AUTHORIZED"
                if core_completeness.get("state") == "REVIEWED_NONE_FOUND"
                else "NO_EXPLICIT_NEGATIVE_POLICY",
                "case_revision": case.get("revision", 0),
                "grade_provenance": grade_source,
                "visit_key": (case.get("visit_context") or {}).get("visit_key"),
                "visit_evidence_state": (case.get("visit_context") or {}).get("evidence_state", "UNKNOWN"),
                "captured_at": (case.get("visit_context") or {}).get("captured_at"),
                "capture_sequence": (case.get("visit_context") or {}).get("capture_sequence"),
                "processing_representation_version": (case.get("analysis_derivative") or {}).get(
                    "representation_version"
                ),
                "processing_analysis_sha256": (case.get("analysis_derivative") or {}).get("analysis_sha256"),
                "selected_ai_model_id": (case.get("selected_ai_evidence") or {}).get("model_id"),
                "selected_ai_invocation_id": (case.get("selected_ai_evidence") or {}).get("invocation_id"),
                "ai_evidence_status": "AVAILABLE" if global_result or lesion_result else "UNAVAILABLE",
            }
            case_annotations = self._annotation_rows(
                case, row, global_result, lesion_result, human_annotations,
                imported_annotations, lesion_ready, lesion_reason,
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
        lesion_ready: bool,
        lesion_reason: str,
        annotation_confirmed: bool,
        annotation_confirmation: dict,
    ) -> list[dict]:
        image_id = image_row["image_id"]
        rows: list[dict] = []
        decisions = {}
        linked_counts = {}
        for annotation in human_annotations:
            detection_id = annotation.get("source_detection_id")
            if detection_id:
                linked_counts[detection_id] = linked_counts.get(detection_id, 0) + 1
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
            rows.append(
                {
                    "annotation_id": detection_id,
                    "image_id": image_id,
                    "label": effective_label,
                    "shape_type": "rectangle",
                    "geometry_json": _geometry_json(
                        {"x": ex1, "y": ey1, "width": ex2 - ex1, "height": ey2 - ey1}
                    ),
                    "annotation_source": annotation_source,
                    "reviewer": decision.get("reviewer") if decision else None,
                    "created_at": decision.get("timestamp") if decision else None,
                    "model_id": lesion_result.get("model_id") or global_result.get("model_id"),
                    "model_version": lesion_result.get("model_version") or global_result.get("model_version"),
                    "score": None if correction else lesion.get("score"),
                    "verification_status": "CLINICIAN_CONFIRMED"
                    if annotation_confirmed and active
                    else ("REMOVED" if removed else "AI_ONLY"),
                    # Case-level annotation confirmation does not confirm an untouched
                    # AI proposal. Only the explicit correction path can become gold.
                    "include_in_training": bool(
                        correction and lesion_ready and active and detection_id not in linked_counts
                    ),
                    "eligibility_reason": "SUPERSEDED_BY_HUMAN_ANNOTATION"
                    if detection_id in linked_counts
                    else (
                        "ELIGIBLE"
                        if correction and lesion_ready and active
                        else ("REMOVED_FROM_ACTIVE_SET" if removed else "AI_ONLY_UNVERIFIED")
                    ),
                    "source_detection_id": detection_id if correction else None,
                    "original_label": lesion["canonical_label"],
                    "original_score": lesion.get("score"),
                    "original_geometry_json": _geometry_json(
                        {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}
                    ),
                }
            )
        for index, annotation in enumerate(human_annotations):
            label = annotation.get("label")
            if label not in CANONICAL_LABELS:
                raise DatasetManifestError("Human annotation uses a non-canonical lesion label")
            duplicate_link = linked_counts.get(annotation.get("source_detection_id"), 0) > 1
            human_ready = bool(lesion_ready and not duplicate_link)
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
                "eligibility_reason": "DUPLICATE_SOURCE_DETECTION_LINK" if duplicate_link else (
                    "ELIGIBLE" if human_ready else lesion_reason
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
        imported_ready = bool(
            annotation_confirmed
            and annotation_confirmation.get("reviewer")
            and annotation_confirmation.get("timestamp")
        )
        for index, annotation in enumerate(imported_annotations):
            label = annotation.get("canonical_label")
            if label not in CANONICAL_LABELS:
                raise DatasetManifestError("Imported annotation uses a non-canonical lesion label")
            shape_type, geometry = _imported_geometry(annotation.get("geometry") or {})
            ready = bool(imported_ready and lesion_ready)
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
                    lesion_reason
                ),
                "source_detection_id": None,
                "original_label": None,
                "original_score": None,
                "original_geometry_json": None,
            })
        return rows

    def preview(self, *, include_annotations: bool = True) -> dict:
        with self._read_snapshot_cases() as snapshot_cases:
            cases = (
                self._merge_case_records(snapshot_cases)
                if not hasattr(self.app.state.store, "repeatable_read_cases")
                else list(snapshot_cases)
            )
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
            "can_export": workspace_id is not None and not any(
                str(row.get("export_authorization", "")).startswith("BLOCKED_") for row in images
            ),
            "images": images,
            "annotations": annotations,
            "coordinate_system": "original_image_pixels",
            "lesion_taxonomy": sorted(CANONICAL_LABELS),
            "eligibility_policy_version": LEGACY_ELIGIBILITY_POLICY_VERSION,
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
    def _assert_export_authorized(images: list[dict]) -> None:
        if any(str(row.get("export_authorization", "")).startswith("BLOCKED_") for row in images):
            raise DatasetManifestError(
                "Export is blocked because one or more records lack approved engineering export authorization."
            )

    @staticmethod
    def _assert_local_destination(images: list[dict], folder: str | Path) -> None:
        hospital = any(row.get("export_authorization") in LOCAL_ONLY_EXPORTS for row in images)
        if hospital and local_export_destination_reason(folder) is not None:
            raise DatasetManifestError(
                "Hospital records can be exported only to a local folder on this computer. "
                "In Settings, choose a Workspace output folder that is not on a network share "
                "or synced to a cloud service.")

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
            if query and not any(
                query in str(row.get(key) or "").casefold()
                for key in ("image_id", "filename", "patient_key", "training_group_key")
            ):
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
            completeness.append(
                {
                    "group": group,
                    "state": value.get("state", "NOT_REVIEWED"),
                    "reviewer": value.get("reviewer"),
                    "timestamp": value.get("timestamp"),
                    "taxonomy_version": value.get("taxonomy_version"),
                    "negative_training_authorized": False,
                    "negative_eligibility_reason": "REVIEWED_NONE_FOUND_NOT_AUTHORIZED"
                    if value.get("state") == "REVIEWED_NONE_FOUND"
                    else "NO_EXPLICIT_NEGATIVE_POLICY",
                }
            )
        return {
            "schema_version": "s4.workspace-data-record.v1",
            "workspace_id": workspace_id,
            "workspace_name": workspace_name,
            "source_state_digest": source_state["digest"],
            "record": row,
            "review_milestones": {
                "image_confirmation": {
                    "status": row.get("image_confirmation_status"),
                    "reviewer": row.get("image_confirmed_by"),
                    "timestamp": row.get("image_confirmed_at"),
                },
                "dr_grade": {
                    "status": row.get("dr_grade_confirmation_status"),
                    "reviewer": row.get("dr_grade_confirmed_by"),
                    "timestamp": row.get("dr_grade_confirmed_at"),
                    "provenance": row.get("grade_provenance"),
                },
                "annotation_set": {
                    "status": row.get("annotation_confirmation_status"),
                    "reviewer": row.get("annotation_confirmed_by"),
                    "timestamp": row.get("annotation_confirmed_at"),
                    "hash": row.get("confirmed_annotation_hash"),
                },
                "latest_review": {
                    "reviewer": review.get("reviewer"),
                    "timestamp": review.get("timestamp"),
                    "action": review.get("review_action"),
                },
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
        return {
            "status": explanation.get("status", "AVAILABLE"),
            "evidence_identity": explanation.get("evidence_identity"),
            "record": explanation,
            "ai_evidence": evidence,
        }

    def workspace_data_detail(self, image_id: str) -> dict:
        return self._record_detail(image_id)

    def workspace_data_processing(self, image_id: str) -> dict:
        return self._record_detail(image_id)["processing"] | {
            "schema_version": "s4.workspace-data-processing.v1",
            "image_id": image_id,
        }

    def workspace_data_explainability(self, image_id: str) -> dict:
        return self._record_detail(image_id)["explainability"] | {
            "schema_version": "s4.workspace-data-explainability.v1",
            "image_id": image_id,
        }

    def export(self) -> dict:
        workspace = self._workspace()
        if workspace is None:
            raise DatasetManifestError("Open an active Workspace before exporting a dataset manifest.")
        with self._read_snapshot_cases() as snapshot_cases:
            cases = (
                list(snapshot_cases)
                if hasattr(self.app.state.store, "repeatable_read_cases")
                else self._merge_case_records(snapshot_cases)
            )
            images, annotations = self._rows(cases)
            source_state = _source_state_receipt(workspace.id, cases)
        self._assert_export_authorized(images)
        self._assert_local_destination(images, workspace.output_folder)
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
                "eligibility_policy_version": LEGACY_ELIGIBILITY_POLICY_VERSION,
                "source_state_digest_version": SOURCE_STATE_DIGEST_VERSION,
                "source_state_digest": source_state,
                "negative_policy_version": NEGATIVE_POLICY_VERSION,
                "referral_policy": {
                    "rule_id": "M1_DR_GRADE_4_REFERRAL",
                    "rule_version": "1.0.0",
                    "source": "current_clinician_confirmed_grade_only",
                    "statuses": sorted({str(row.get("referral_status")) for row in images}),
                },
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
