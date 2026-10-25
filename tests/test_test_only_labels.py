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
    assert rows[test_only]["include_in_training"] is False
    assert rows[test_only]["eligibility_reason"] == "TEST_ONLY_LABEL"
    assert rows[clinician]["grade_eligibility_reason"] == "ELIGIBLE"
    assert rows[clinician]["dr_grade_training_ready"] is True and rows[clinician]["include_in_training"] is True
    manifest = client.get("/v1/dataset/manifest").json()
    assert manifest["training_ready_count"] == 1

    # Workspace-origin records are export-blocked by design; give them an allowed decision here.
    from dr_support.services import dataset
    monkeypatch.setattr(dataset, "_export_authorization", lambda origin: "ALLOWED_ENGINEERING_SYNTHETIC")
    grouped = client.post("/v1/dataset/export/grouped-by-grade", json={})
    assert grouped.status_code == 200, grouped.text
    root = tmp_path / "output" / "grouped_by_grade"
    assert any((root / "dr_grade_2").iterdir())
    assert not any(test_only[:12] in path.name for path in (root / "dr_grade_2").iterdir())
    assert (root / "test_only").is_dir() and any((root / "test_only").iterdir())


def test_test_only_shapes_make_the_lesion_labels_test_only():
    clinical = SimpleNamespace(id="ws_1", name="Hospital review")
    case = {"annotation_confirmation": {"reviewer": "Dr. Synthetic"},
            "human_annotations": [{"reviewer": "TEST_ONLY_A", "label": "HEMORRHAGE"}]}
    assert label_class(case, None, clinical) == "TEST_ONLY"
    case = {"clinician_review": {"reviewer": "Dr. Synthetic"},
            "ai_annotation_reviews": [{"reviewer": "TEST_ONLY_B", "action": "REJECT"}]}
    assert label_class(case, None, clinical) == "TEST_ONLY"
    # Superseded grade history does not taint the current physician grade.
    case = {"clinician_review": {"reviewer": "Dr. Synthetic"}, "grade_reviews": [{"reviewer": "TEST_ONLY_C"}]}
    assert label_class(case, None, clinical) == "CLINICIAN"
