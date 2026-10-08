"""Safe, non-longitudinal side-by-side eligibility projection."""

from __future__ import annotations

from typing import Any


def _resolved_identity(case: dict[str, Any]) -> tuple[str | None, str | None]:
    patient = case.get("patient_key")
    eye = case.get("laterality")
    if case.get("patient_resolution_state") != "RESOLVED" or not isinstance(patient, str) or not patient.strip():
        return None, None
    if case.get("laterality_resolution_state") != "RESOLVED" or eye not in {"LEFT", "RIGHT"}:
        return None, None
    return patient.strip().casefold(), eye


def compare_cases(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_patient, left_eye = _resolved_identity(left)
    right_patient, right_eye = _resolved_identity(right)
    if left_patient is None or right_patient is None:
        return {"eligible": False, "reason": "IDENTITY_NOT_EXPLICITLY_RESOLVED"}
    if left_patient != right_patient:
        return {"eligible": False, "reason": "PATIENT_MISMATCH"}
    if left_eye != right_eye:
        return {"eligible": False, "reason": "EYE_MISMATCH"}
    return {
        "eligible": True,
        "patient_key": left.get("patient_key"),
        "laterality": left_eye,
        "chronology": "UNKNOWN",
        "limitation": "Visit labels separate records only; chronology, registration, progression, and lesion matching are not inferred.",
        "visits": [
            _visit(left, "Visit 1"),
            _visit(right, "Visit 2"),
        ],
    }


def _visit(case: dict[str, Any], label: str) -> dict[str, Any]:
    review = case.get("clinician_review") or {}
    return {
        "label": label,
        "image_id": case.get("image_id"),
        "display_name": case.get("display_name"),
        "image_url": case.get("image_url"),
        "visit_context": case.get("visit_context"),
        "grade": case.get("reviewed_grade") if case.get("grade_status") == "CONFIRMED" else None,
        "grade_status": case.get("grade_status"),
        "findings_reviewed": case.get("annotation_confirmation_status") == "CONFIRMED",
        "reviewer": review.get("reviewer"),
    }
