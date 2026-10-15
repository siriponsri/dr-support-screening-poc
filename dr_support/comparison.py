"""Privacy-safe longitudinal comparison projections.

Automatic pairing is intentionally conservative: it requires the private
admission linkage projection, same eye and modality, and an unambiguous
immediately preceding capture sequence.  It never infers chronology from list
order or from a display filename.
"""

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


def _sequence(case: dict[str, Any]) -> int | None:
    value = (case.get("visit_context") or {}).get("capture_sequence")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else None


def resolve_previous_case(current: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None | dict[str, str]:
    """Find the verified immediate prior same-patient/same-eye exam.

    ``None`` means no eligible earlier record.  A reason dictionary is used for
    ambiguity so the caller can report a safe aggregate state without exposing
    identifiers.
    """
    patient, eye = _resolved_identity(current)
    current_sequence = _sequence(current)
    modality = current.get("modality") or (current.get("admission") or {}).get("retinal_modality")
    if patient is None or eye is None or current_sequence is None or modality not in {"CFP", "UWF"}:
        return {"reason": "IDENTITY_OR_SEQUENCE_NOT_VERIFIED"}
    matches = []
    for candidate in candidates:
        candidate_patient, candidate_eye = _resolved_identity(candidate)
        candidate_modality = candidate.get("modality") or (candidate.get("admission") or {}).get("retinal_modality")
        candidate_sequence = _sequence(candidate)
        if (
            candidate_patient == patient
            and candidate_eye == eye
            and candidate_modality == modality
            and candidate_sequence == current_sequence - 1
        ):
            matches.append(candidate)
    if len(matches) > 1:
        return {"reason": "AMBIGUOUS_PREVIOUS_EXAM"}
    return matches[0] if matches else None


def compare_cases(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_patient, left_eye = _resolved_identity(left)
    right_patient, right_eye = _resolved_identity(right)
    if left_patient is None or right_patient is None:
        return {"eligible": False, "reason": "IDENTITY_NOT_EXPLICITLY_RESOLVED"}
    if left_patient != right_patient:
        return {"eligible": False, "reason": "PATIENT_MISMATCH"}
    if left_eye != right_eye:
        return {"eligible": False, "reason": "EYE_MISMATCH"}
    left_modality = left.get("modality") or (left.get("admission") or {}).get("retinal_modality")
    right_modality = right.get("modality") or (right.get("admission") or {}).get("retinal_modality")
    if left_modality != right_modality:
        return {"eligible": False, "reason": "MODALITY_MISMATCH"}
    left_sequence, right_sequence = _sequence(left), _sequence(right)
    chronology = "SEQUENCE_VERIFIED" if left_sequence is not None and right_sequence is not None else "UNKNOWN"
    return {
        "eligible": True,
        "patient_key": left.get("patient_key"),
        "laterality": left_eye,
        "modality": left_modality,
        "chronology": chronology,
        "limitation": "Side-by-side engineering comparison only; no pixel correspondence, progression, lesion resolution, or clinical conclusion is inferred.",
        "visits": [
            _visit(left, "PREVIOUS EXAM"),
            _visit(right, "CURRENT EXAM"),
        ],
    }


def _visit(case: dict[str, Any], label: str) -> dict[str, Any]:
    review = case.get("clinician_review") or {}
    return {
        "label": label,
        "image_id": case.get("image_id"),
        "display_name": case.get("display_name"),
        "image_url": case.get("image_url"),
        "width": case.get("width"),
        "height": case.get("height"),
        "visit_context": case.get("visit_context"),
        "laterality": case.get("laterality"),
        "modality": case.get("modality") or (case.get("admission") or {}).get("retinal_modality"),
        "grade": case.get("reviewed_grade") if case.get("grade_status") == "CONFIRMED" else None,
        "grade_status": case.get("grade_status"),
        "findings_reviewed": case.get("annotation_confirmation_status") == "CONFIRMED",
        "reviewer": review.get("reviewer"),
        "prism_processing": case.get("prism_processing"),
        "lesion": case.get("lesion"),
        "spatial_ai_display": case.get("spatial_ai_display"),
    }
