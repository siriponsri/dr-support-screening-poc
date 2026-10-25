"""DT-06: TEST_ONLY labels are tagged and never training-ready (owner decision, 2026-10-25)."""
import hashlib
from types import SimpleNamespace

from dr_support.services.dataset import label_class
from test_admission import _workspace_client, _write_image


def test_label_class_marks_test_workspaces_and_reviewers():
    clinical = SimpleNamespace(id="ws_1", name="Hospital review")
    assert label_class({"clinician_review": {"reviewer": "Dr. Synthetic"}}, None, clinical) == "CLINICIAN"
    assert label_class({"clinician_review": {"reviewer": "test_only_engineering"}}, None, clinical) == "TEST_ONLY"
    assert label_class({"annotation_confirmation": {"reviewer": "TEST_ONLY_A"}}, None, clinical) == "TEST_ONLY"
    assert label_class({}, {"reviewed_by": "TEST_ONLY_B"}, clinical) == "TEST_ONLY"
    assert label_class({"clinician_review": {"reviewer": "Dr. Synthetic"}}, None,
                       SimpleNamespace(id="ws_2", name="TEST_ONLY showcase")) == "TEST_ONLY"
    assert label_class({}, None, clinical) is None


def _confirm_and_grade(client, image_id, reviewer):
    case = client.get(f"/v1/cases/{image_id}").json()
    confirmed = client.post(f"/v1/cases/{image_id}/confirm-image", json={
        "revision": case["revision"], "reviewer": reviewer, "laterality": "LEFT", "retinal_modality": "CFP"})
    assert confirmed.status_code == 200, confirmed.text
    graded = client.post(f"/v1/cases/{image_id}/review", json={
        "revision": confirmed.json()["revision"], "action": "CORRECT_GRADE", "reviewer": reviewer, "grade": 2})
    assert graded.status_code == 200, graded.text


def test_test_only_grades_are_tagged_and_not_training_ready(tmp_path, monkeypatch):
    client, folder = _workspace_client(tmp_path, monkeypatch)
    _write_image(folder / "clinician.png", fundus=True, size=(400, 300))
    _write_image(folder / "test-only.png", fundus=True, size=(420, 310))
    assert client.post("/v1/admissions/scan").status_code == 200
    clinician = hashlib.sha256((folder / "clinician.png").read_bytes()).hexdigest()
    test_only = hashlib.sha256((folder / "test-only.png").read_bytes()).hexdigest()
    _confirm_and_grade(client, clinician, "Dr. Synthetic")
    _confirm_and_grade(client, test_only, "TEST_ONLY_ENGINEERING")

    rows = {row["image_id"]: row for row in client.get("/v1/dataset/manifest").json()["images"]}
    assert rows[clinician]["label_class"] == "CLINICIAN"
    assert rows[clinician]["grade_eligibility_reason"] != "TEST_ONLY_LABEL"
    assert rows[test_only]["label_class"] == "TEST_ONLY"
    assert rows[test_only]["dr_grade_training_ready"] is False
    assert rows[test_only]["grade_eligibility_reason"] == "TEST_ONLY_LABEL"
    # The clinician row is not blocked by the test-only rule; any other reason stays its own.
    if rows[clinician]["grade_eligibility_reason"] == "ELIGIBLE":
        assert rows[clinician]["dr_grade_training_ready"] is True
