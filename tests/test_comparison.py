from dr_support.comparison import compare_cases


def case(image_id: str, *, patient: str | None = "PATIENT-1", eye: str = "LEFT", patient_state: str = "RESOLVED", eye_state: str = "RESOLVED"):
    return {
        "image_id": image_id,
        "display_name": f"{image_id}.png",
        "image_url": f"/v1/images/{image_id}/display",
        "patient_key": patient,
        "patient_resolution_state": patient_state,
        "laterality": eye,
        "laterality_resolution_state": eye_state,
        "visit_context": {"visit_key": None, "captured_at": None, "capture_sequence": None, "device": None, "evidence_state": "UNKNOWN"},
        "grade_status": "CONFIRMED",
        "reviewed_grade": 2,
        "annotation_confirmation_status": "DRAFT",
        "clinician_review": {"reviewer": "Clinician"},
    }


def test_comparison_uses_neutral_visits_without_chronology_or_progression():
    result = compare_cases(case("one"), case("two"))

    assert result["eligible"] is True
    assert [visit["label"] for visit in result["visits"]] == ["Visit 1", "Visit 2"]
    assert result["chronology"] == "UNKNOWN"
    assert "progression" in result["limitation"]
    assert result["visits"][0]["grade"] == 2
    assert result["visits"][1]["grade"] == 2


def test_comparison_rejects_unknown_or_conflicting_identity():
    assert compare_cases(case("one", patient=None), case("two"))["reason"] == "IDENTITY_NOT_EXPLICITLY_RESOLVED"
    assert compare_cases(case("one"), case("two", patient="PATIENT-2"))["reason"] == "PATIENT_MISMATCH"
    assert compare_cases(case("one"), case("two", eye="RIGHT"))["reason"] == "EYE_MISMATCH"
    assert compare_cases(case("one", eye="UNKNOWN"), case("two", eye="UNKNOWN"))["reason"] == "IDENTITY_NOT_EXPLICITLY_RESOLVED"
