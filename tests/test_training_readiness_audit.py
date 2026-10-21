"""Synthetic, in-memory exporter audit: no app factory, DB, model calls or real images."""
import copy
import csv
import hashlib
import io
import json
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from dr_support.presentation import annotation_set_hash, lesion_detection_id
from dr_support.services.dataset import DatasetManifestError, DatasetManifestService, _source_state_receipt

STAMP = "2026-10-21T00:00:00Z"


def fixture_case():
    return {
        "image_id": "synthetic-audit", "revision": 3, "state": "REVIEWED",
        "source_origin": "SYNTHETIC", "queue_state": "INCLUDED",
        "grade_status": "CONFIRMED", "reviewed_grade": 2, "grade_review_source": "MANUAL",
        "clinician_review": {"final_grade": 2, "review_action": "CORRECT_GRADE", "reviewer": "Synthetic annotator", "timestamp": STAMP, "revision": 2},
        "human_annotations": [], "annotations": [], "global": None, "lesion": None,
        "patient_key": "SYNTHETIC01", "patient_resolution_state": "RESOLVED", "laterality": "LEFT",
        "visit_context": {"visit_key": "synthetic-exam-1", "evidence_state": "CONFIRMED", "capture_sequence": 1},
        "admission": {"source_origin": "SYNTHETIC", "source_sha256": hashlib.sha256(b"synthetic fixture only").hexdigest(), "filename": "synthetic.png", "width": 800, "height": 600, "retinal_modality": "CFP", "modality_admission": "FUNDUS_ACCEPTED", "quality_state": "GRADABLE", "reviewed_by": "Synthetic annotator", "reviewed_at": STAMP},
    }


def human():
    return {"shape_id": "human-fixture", "type": "rectangle", "label": "HEMORRHAGE", "geometry": {"x": 10, "y": 20, "width": 30, "height": 40}, "source": "HUMAN", "reviewer": "Synthetic annotator", "created_at": STAMP}


def confirm_annotations(case):
    case["lesion_review_state"] = "REVIEWED"
    case["annotation_hash"] = annotation_set_hash(case)
    case["confirmed_annotation_hash"] = case["annotation_hash"]
    case["annotation_confirmation"] = {"reviewer": "Synthetic annotator", "timestamp": STAMP}
    return case


def service_for(case, tmp_path):
    class MemoryStore:
        lock = threading.RLock()

        def all_cases(self):
            return [copy.deepcopy(case)]

        @contextmanager
        def repeatable_read_cases(self):
            yield self.all_cases()

    image = SimpleNamespace(sha256=case["admission"]["source_sha256"], filename="synthetic.png", source_type="SYNTHETIC", source_origin=case["admission"]["source_origin"])
    state = SimpleNamespace(store=MemoryStore(), images={case["image_id"]: image}, admissions={}, workspace_manager=SimpleNamespace(active_workspace=SimpleNamespace(id="synthetic-workspace", name="Synthetic exporter audit", output_folder=str(tmp_path))))
    return DatasetManifestService(SimpleNamespace(state=state, version="fixture"))


def rows(service, case):
    return service._rows([case])


@pytest.mark.parametrize("invalid", [True, -1, 5, "2", 2.0, "UNGRADABLE"])
def test_invalid_or_nonnumeric_grades_are_never_training_labels(invalid, tmp_path):
    case = fixture_case()
    case["reviewed_grade"] = invalid
    case["clinician_review"]["final_grade"] = invalid
    image = rows(service_for(case, tmp_path), case)[0][0]
    assert image["dr_grade_training_ready"] is False
    assert image["clinician_grade"] is None


@pytest.mark.parametrize("status", ["NOT_REVIEWED", "UNKNOWN", "UNGRADABLE", "NEEDS_SECOND_REVIEW"])
def test_nonconfirmed_grade_status_cannot_reuse_a_numeric_cache(status, tmp_path):
    case = fixture_case()
    case["grade_status"] = status
    assert rows(service_for(case, tmp_path), case)[0][0]["dr_grade_training_ready"] is False


def test_annotation_hash_is_derived_from_active_geometry_not_a_cached_field(tmp_path):
    case = fixture_case()
    case["human_annotations"] = [human()]
    confirm_annotations(case)
    case["human_annotations"][0]["geometry"]["width"] = 50
    image, annotations = rows(service_for(case, tmp_path), case)
    assert image[0]["lesion_training_ready"] is False
    assert annotations[0]["include_in_training"] is False


def test_grade_and_lesion_readiness_are_independent(tmp_path):
    case = fixture_case()
    service = service_for(case, tmp_path)
    image = rows(service, case)[0][0]
    assert image["dr_grade_training_ready"] is True
    assert image["lesion_training_ready"] is False
    case["reviewed_grade"] = None
    case["clinician_review"] = None
    case["grade_status"] = "NOT_REVIEWED"
    case["human_annotations"] = [human()]
    confirm_annotations(case)
    image, annotations = rows(service, case)
    assert image[0]["dr_grade_training_ready"] is False
    assert image[0]["lesion_positive_training_ready"] is True
    assert annotations[0]["include_in_training"] is True


def test_reviewed_none_is_explicit_completeness_and_never_a_gold_negative(tmp_path):
    case = fixture_case()
    service = service_for(case, tmp_path)
    image = rows(service, case)[0][0]
    assert image["core_completeness_state"] == "NOT_REVIEWED"
    assert image["lesion_training_ready"] is False
    case["annotation_completeness"] = {"CORE": {"state": "REVIEWED_NONE_FOUND", "reviewer": "Synthetic annotator", "timestamp": STAMP, "taxonomy_version": "core-fixture"}}
    confirm_annotations(case)
    image, annotations = rows(service, case)
    assert image[0]["core_completeness_state"] == "REVIEWED_NONE_FOUND"
    assert image[0]["negative_training_authorized"] is False
    assert image[0]["lesion_positive_training_ready"] is False
    assert not annotations


def add_ai(case):
    case["lesion"] = {"model_id": "prism-dr-5fold", "model_version": "fixture", "modality": "CFP", "state": "AI_SUGGESTION", "width": 800, "height": 600, "provenance": {"image_sha256": case["admission"]["source_sha256"], "source_type": "SYNTHETIC", "preprocessing": "fixture", "source_revision": "fixture"}, "lesions": [{"source_label": "HE", "canonical_label": "HEMORRHAGE", "rectangle": [10.0, 20.0, 40.0, 60.0], "score": 0.9, "state": "AI_SUGGESTION"}], "warnings": []}


def test_snapshot_separates_ai_evidence_and_gold_and_hashes_every_output(tmp_path):
    case = fixture_case()
    add_ai(case)
    confirm_annotations(case)
    before = copy.deepcopy(case)
    result = service_for(case, tmp_path).export_snapshot()
    directory = tmp_path / result["directory_name"]
    labels = list(csv.DictReader(io.StringIO((directory / "lesion_labels.csv").read_text())))
    evidence = list(csv.DictReader(io.StringIO((directory / "ai_evidence.csv").read_text())))
    grading = list(csv.DictReader(io.StringIO((directory / "dr_labels.csv").read_text())))
    assert not labels
    assert evidence[0]["model_id"] == "prism-dr-5fold"
    assert grading[0]["dr_grade"] == "2"
    assert grading[0]["source_sha256"] == case["admission"]["source_sha256"]
    assert grading[0]["case_revision"] == "3"
    assert grading[0]["training_group_key"] == "patient:SYNTHETIC01"
    assert result["manifest"]["coordinate_system"] == "original_image_pixels"
    for name, digest in result["manifest"]["file_sha256"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
    assert case == before
    assert str(tmp_path) not in (directory / "manifest.json").read_text()


def test_corrected_ai_preserves_original_score_only_as_audit_evidence(tmp_path):
    case = fixture_case()
    add_ai(case)
    case["ai_annotation_reviews"] = [{"detection_id": lesion_detection_id(case["lesion"]["lesions"][0]), "action": "CORRECT", "corrected_label": "HARD_EXUDATE", "corrected_rectangle": [11, 21, 41, 61], "reviewer": "Synthetic annotator", "timestamp": STAMP}]
    confirm_annotations(case)
    annotation = rows(service_for(case, tmp_path), case)[1][0]
    assert annotation["annotation_source"] == "HUMAN_CORRECTION"
    assert annotation["include_in_training"] is True
    assert annotation["score"] is None
    assert annotation["original_score"] == 0.9
    assert json.loads(annotation["geometry_json"]) == {"x": 11, "y": 21, "width": 30, "height": 40}


def test_hospital_export_guard_writes_nothing_even_with_complete_synthetic_labels(tmp_path):
    case = fixture_case()
    case["admission"]["source_origin"] = "HOSPITAL_AUTHORIZED"
    service = service_for(case, tmp_path)
    assert rows(service, case)[0][0]["export_authorization"] == "BLOCKED_HOSPITAL_EXPORT_NOT_AUTHORIZED"
    with pytest.raises(DatasetManifestError, match="lack approved engineering export authorization"):
        service.export_snapshot()
    assert list(tmp_path.iterdir()) == []


def test_patient_group_requires_confirmed_link_and_digest_tracks_revisions(tmp_path):
    case = fixture_case()
    case["patient_resolution_state"] = "UNRESOLVED"
    assert rows(service_for(case, tmp_path), case)[0][0]["training_group_key"] is None
    original = _source_state_receipt("fixture", [case])
    assert original == _source_state_receipt("fixture", [copy.deepcopy(case)])
    case["revision"] += 1
    assert original["digest"] != _source_state_receipt("fixture", [case])["digest"]


def test_repeated_snapshot_has_reproducible_label_bytes_and_source_digest(tmp_path):
    case = fixture_case()
    case["human_annotations"] = [human()]
    confirm_annotations(case)
    service = service_for(case, tmp_path)
    first, second = service.export_snapshot(), service.export_snapshot()
    assert first["snapshot_id"] != second["snapshot_id"]
    assert first["manifest"]["source_state_digest"] == second["manifest"]["source_state_digest"]
    assert first["manifest"]["file_sha256"] == second["manifest"]["file_sha256"]


@pytest.mark.parametrize("invalid", [True, 1.0, "1"])
def test_review_grade_type_cannot_be_hidden_by_an_integer_cache(invalid, tmp_path):
    case = fixture_case()
    case["reviewed_grade"] = 1
    case["clinician_review"]["final_grade"] = invalid
    assert rows(service_for(case, tmp_path), case)[0][0]["dr_grade_training_ready"] is False


@pytest.mark.parametrize("action", ["MARK_UNGRADABLE", "REQUEST_SECOND_REVIEW", "ESCALATE", "CONFIRM_ANNOTATIONS"])
def test_non_grade_actions_cannot_establish_a_grade_training_label(action, tmp_path):
    case = fixture_case()
    case["clinician_review"]["review_action"] = action
    assert rows(service_for(case, tmp_path), case)[0][0]["dr_grade_training_ready"] is False


@pytest.mark.parametrize("grade", range(5))
def test_all_five_valid_confirmed_grades_remain_eligible(grade, tmp_path):
    case = fixture_case()
    case["reviewed_grade"] = case["clinician_review"]["final_grade"] = grade
    row = rows(service_for(case, tmp_path), case)[0][0]
    assert row["dr_grade_training_ready"] is True
    assert row["clinician_grade"] == grade


def test_legacy_missing_status_and_action_remain_compatible(tmp_path):
    case = fixture_case()
    case.pop("grade_status")
    case["clinician_review"].pop("review_action")
    assert rows(service_for(case, tmp_path), case)[0][0]["dr_grade_training_ready"] is True


def test_grade_cache_disagreement_is_not_a_final_human_label(tmp_path):
    case = fixture_case()
    case["clinician_review"]["final_grade"] = 3
    assert rows(service_for(case, tmp_path), case)[0][0]["dr_grade_training_ready"] is False


@pytest.mark.parametrize("revision", [0, True, 99])
def test_invalid_or_future_review_revision_is_ineligible(revision, tmp_path):
    case = fixture_case()
    case["clinician_review"]["revision"] = revision
    assert rows(service_for(case, tmp_path), case)[0][0]["dr_grade_training_ready"] is False


@pytest.mark.parametrize("missing", ["null", "absent"])
def test_explicit_missing_physician_grade_never_uses_the_cache(missing, tmp_path):
    case = fixture_case()
    if missing == "null":
        case["clinician_review"]["final_grade"] = None
    else:
        case["clinician_review"].pop("final_grade")
    record = rows(service_for(case, tmp_path), case)[0][0]
    assert record["dr_grade_training_ready"] is False
    assert record["clinician_grade"] is None


@pytest.mark.parametrize("failure", ["different_hash", "failed_integrity", "failed_nested_integrity", "missing_image"])
def test_source_identity_failure_blocks_both_training_tasks(failure, tmp_path):
    case = fixture_case()
    case["human_annotations"] = [human()]
    confirm_annotations(case)
    service = service_for(case, tmp_path)
    if failure == "different_hash":
        service.app.state.images[case["image_id"]].sha256 = "f" * 64
    elif failure == "failed_integrity":
        case["admission"]["integrity_status"] = "SOURCE_CHANGED"
    elif failure == "failed_nested_integrity":
        case["admission"]["integrity"] = {"status": "SOURCE_MISSING"}
    else:
        service.app.state.images.clear()
    images, annotations = rows(service, case)
    assert images[0]["dr_grade_training_ready"] is False
    assert images[0]["lesion_training_ready"] is False
    assert not any(annotation["include_in_training"] for annotation in annotations)
    # Metadata stays readable; the source is not silently rebound to a new label.
    assert images[0]["source_sha256"]
    result = service.export_snapshot()
    directory = tmp_path / result["directory_name"]
    assert not list(csv.DictReader(io.StringIO((directory / "dr_labels.csv").read_text())))
    assert not list(csv.DictReader(io.StringIO((directory / "lesion_labels.csv").read_text())))


def test_linked_current_human_annotation_is_the_only_gold_representation(tmp_path):
    case = fixture_case()
    add_ai(case)
    detection = lesion_detection_id(case["lesion"]["lesions"][0])
    case["ai_annotation_reviews"] = [{"detection_id": detection, "action": "CORRECT", "corrected_label": "HARD_EXUDATE", "corrected_rectangle": [11, 21, 41, 61], "reviewer": "Synthetic annotator", "timestamp": STAMP}]
    derived = human()
    derived.update(source_detection_id=detection, label="SOFT_EXUDATE", geometry={"x": 50, "y": 60, "width": 70, "height": 80})
    case["human_annotations"] = [derived]
    confirm_annotations(case)
    service = service_for(case, tmp_path)
    annotations = rows(service, case)[1]
    gold = [row for row in annotations if row["include_in_training"]]
    assert len(gold) == 1
    assert gold[0]["annotation_id"] == derived["shape_id"]
    assert gold[0]["label"] == "SOFT_EXUDATE"
    assert json.loads(gold[0]["geometry_json"]) == derived["geometry"]
    audit = next(row for row in annotations if row["annotation_source"] == "HUMAN_CORRECTION")
    assert audit["original_score"] == 0.9
    assert audit["include_in_training"] is False
    result = service.export_snapshot()
    labels = list(csv.DictReader(io.StringIO((tmp_path / result["directory_name"] / "lesion_labels.csv").read_text())))
    assert len(labels) == 1 and labels[0]["label"] == "SOFT_EXUDATE"


@pytest.mark.parametrize("operation", ["lesion-review", "annotations/from-ai"])
def test_stale_roi_cannot_reach_a_mutation_without_any_database(operation, tmp_path, monkeypatch):
    from fastapi import HTTPException
    from dr_support import workflow

    case = fixture_case()
    add_ai(case)
    case["lesion"]["provenance"]["image_sha256"] = "f" * 64
    writes = []

    class Store:
        lock = threading.RLock()

        def get(self, _image_id):
            return copy.deepcopy(case)

        def put(self, value):
            writes.append(value)
            raise AssertionError("Stale ROI reached a write")

    class Routes:
        state = SimpleNamespace(images={case["image_id"]: SimpleNamespace(sha256=case["admission"]["source_sha256"], size=(800, 600), source_type="SYNTHETIC")})

        def __init__(self):
            self.routes = {}

        def register(self, path):
            def decorator(function):
                self.routes[path] = function
                return function
            return decorator

        get = post = put = register

    monkeypatch.setattr(workflow, "CVATOnline", lambda: SimpleNamespace())
    app = Routes()
    workflow.install_workflow(app, Store())
    detection = lesion_detection_id(case["lesion"]["lesions"][0])
    if operation == "lesion-review":
        request = workflow.LesionReviewAction(revision=case["revision"], reviewer="Synthetic reviewer", detection_id=detection, action="CONFIRM")
    else:
        request = workflow.HumanAnnotationDerive(revision=case["revision"], reviewer="Synthetic reviewer", detection_id=detection, intent="USE_AS_HUMAN")
    with pytest.raises(HTTPException) as blocked:
        app.routes[f"/v1/cases/{{image_id}}/{operation}"](case["image_id"], request)
    assert blocked.value.status_code == 409
    assert writes == []


@pytest.mark.parametrize("prepared", [False, True])
def test_roi_mutation_guard_keeps_matching_source_and_analysis_lineage_usable(prepared):
    from dr_support import workflow
    case = fixture_case()
    add_ai(case)
    source = case["admission"]["source_sha256"]
    image = SimpleNamespace(sha256=source, size=(800, 600), source_type="SYNTHETIC")
    if prepared:
        analysis = "d" * 64
        transform = sorted(workflow.KNOWN_ANALYSIS_TRANSFORMS)[0]
        case["lesion"]["provenance"]["image_sha256"] = analysis
        case["analysis_derivative"] = {
            "source_sha256": source, "source_origin": "SYNTHETIC",
            "analysis_sha256": analysis, "derivative_sha256": analysis,
            "representation_version": workflow.ANALYSIS_REPRESENTATION_VERSION,
            "transform_id": transform, "analysis_coordinate_space": workflow.ANALYSIS_COORDINATE_SPACE,
            "original_coordinate_space": workflow.ORIGINAL_COORDINATE_SPACE,
            "spatial_mapping_version": "analysis-to-original-v1",
            "source_dimensions": {"width": 800, "height": 600},
            "analysis_dimensions": {"width": 400, "height": 300},
            "coordinate_mapping": {"kind": "SCALE", "canonical_width": 800, "canonical_height": 600, "analysis_width": 400, "analysis_height": 300, "scale_x": 2, "scale_y": 2},
            "lineage": {"purpose": "ANALYSIS", "source_sha256": source, "derivative_sha256": analysis, "transform_id": transform, "coordinate_space": workflow.ANALYSIS_COORDINATE_SPACE, "width": 400, "height": 300},
        }
    workflow._require_current_spatial_ai(case, image, case["admission"])


def test_conflicting_multiple_human_copies_are_held_out_without_guessing(tmp_path):
    case = fixture_case()
    add_ai(case)
    detection = lesion_detection_id(case["lesion"]["lesions"][0])
    first, second = human(), human()
    first["source_detection_id"] = second["source_detection_id"] = detection
    second.update(shape_id="other-copy", label="SOFT_EXUDATE")
    case["human_annotations"] = [first, second]
    confirm_annotations(case)
    annotations = rows(service_for(case, tmp_path), case)[1]
    assert not any(row["include_in_training"] for row in annotations)
    assert all(row["eligibility_reason"] == "DUPLICATE_SOURCE_DETECTION_LINK" for row in annotations if row["annotation_source"] == "HUMAN")


@pytest.mark.parametrize("task", ["grade", "lesion"])
def test_explicit_confirmation_source_binding_must_match_current_image(task, tmp_path):
    case = fixture_case()
    confirm_annotations(case)
    if task == "grade":
        case["clinician_review"]["source_sha256"] = "f" * 64
    else:
        case["annotation_confirmation"]["source_sha256"] = "f" * 64
    record = rows(service_for(case, tmp_path), case)[0][0]
    assert record["dr_grade_training_ready" if task == "grade" else "lesion_training_ready"] is False
