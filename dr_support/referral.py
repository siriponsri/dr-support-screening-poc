"""Owner-confirmed M1 referral derivation from explicit human grade reviews."""

from __future__ import annotations

from typing import Any


REFERRAL_RULE_ID = "M1_DR_GRADE_4_REFERRAL"
REFERRAL_RULE_VERSION = "1.0.0"
_FINAL_GRADE_ACTIONS = frozenset({"ACCEPT", "CORRECT_GRADE", "ADJUDICATE_GRADE"})


def _undetermined(reason: str) -> dict[str, Any]:
    return {
        "status": "UNDETERMINED",
        "rule_id": REFERRAL_RULE_ID,
        "rule_version": REFERRAL_RULE_VERSION,
        "source_grade": None,
        "source_grade_revision": None,
        "reviewer": None,
        "timestamp": None,
        "reason": reason,
    }


def derive_referral(case: dict[str, Any]) -> dict[str, Any]:
    """Derive only from a current, explicitly confirmed numeric physician grade."""
    review = case.get("clinician_review") or {}
    grade = review.get("final_grade")
    if case.get("grade_status") != "CONFIRMED":
        return _undetermined("NO_CURRENT_CONFIRMED_GRADE")
    if review.get("review_action") not in _FINAL_GRADE_ACTIONS:
        return _undetermined("NO_CURRENT_CONFIRMED_GRADE")
    if isinstance(grade, bool) or not isinstance(grade, int) or grade not in range(5):
        return _undetermined("NO_CURRENT_CONFIRMED_GRADE")
    if not review.get("reviewer") or not review.get("timestamp"):
        return _undetermined("MISSING_REVIEW_PROVENANCE")
    revision = review.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        return _undetermined("MISSING_REVIEW_PROVENANCE")
    return {
        "status": "REFER" if grade == 4 else "NOT_REFER",
        "rule_id": REFERRAL_RULE_ID,
        "rule_version": REFERRAL_RULE_VERSION,
        "source_grade": grade,
        "source_grade_revision": revision,
        "reviewer": review["reviewer"],
        "timestamp": review["timestamp"],
        "reason": "CURRENT_CLINICIAN_CONFIRMED_GRADE",
    }


def current_referral(case: dict[str, Any]) -> dict[str, Any]:
    """Expose persisted derivations only while they still match the current review."""
    persisted = case.get("referral_current")
    if not isinstance(persisted, dict):
        return _undetermined("NO_CURRENT_DERIVATION")
    derived = derive_referral(case)
    if derived["status"] == "UNDETERMINED":
        return derived
    keys = ("status", "rule_id", "rule_version", "source_grade", "source_grade_revision", "reviewer", "timestamp")
    if any(persisted.get(key) != derived.get(key) for key in keys):
        return _undetermined("NO_CURRENT_DERIVATION")
    return {**derived, "reason": "CURRENT_CLINICIAN_CONFIRMED_GRADE"}
