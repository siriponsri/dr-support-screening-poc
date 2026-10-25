"""Disposable synthetic files and MemoryStore only; no app factory/DB/models."""
from copy import deepcopy
from datetime import datetime, timezone
from dataclasses import replace
import csv
import hashlib
import json
from pathlib import Path
from threading import RLock
from types import SimpleNamespace

from PIL import Image
import pytest

from dr_support.images import BridgeImage
from dr_support.services import dataset
from dr_support.services.dataset import DatasetManifestService
from dr_support.services.dataset import DatasetManifestError


class MemoryStore:
    def __init__(self, cases):
        self.cases = cases
        self.lock = RLock()

    def get(self, image_id):
        return deepcopy(self.cases[image_id])

    def all_cases(self):
        return deepcopy(list(self.cases.values()))


@pytest.fixture
def rig(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("DB access forbidden"))
    source = tmp_path / "input"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    path = source / "synthetic-private-name.png"
    Image.new("RGB", (32, 24), (80, 40, 20)).save(path)
    image = BridgeImage("synthetic-folder", path.read_bytes(), "SYNTHETIC", "fixture", modality="CFP",
                        filename=path.name, media_type="image/png", source_origin="SYNTHETIC")
    admission = {"source_origin": "SYNTHETIC", "source_sha256": image.sha256,
                 "modality_admission": "FUNDUS_ACCEPTED", "quality_state": "GRADABLE",
                 "retinal_modality": "CFP", "width": 32, "height": 24,
                 "reviewed_by": "Synthetic clinician", "reviewed_at": "2026-10-21T00:00:00Z"}
    case = {"image_id": image.image_id, "revision": 3, "source_sha256": image.sha256,
            "grade_status": "CONFIRMED", "reviewed_grade": 2, "grade_review_source": "MANUAL",
            "clinician_review": {"final_grade": 2, "review_action": "CORRECT_GRADE", "revision": 2,
                                 "reviewer": "Synthetic clinician", "timestamp": "2026-10-21T00:00:00Z",
                                 "source_sha256": image.sha256},
            "admission": admission, "human_annotations": [], "global": None, "lesion": None,
            "state": "REVIEWED", "queue_state": "INCLUDED", "grade_reviews": [], "events": []}
    store = MemoryStore({image.image_id: case})
    workspace = SimpleNamespace(id="synthetic-workspace", name="Synthetic fixture", input_folder=str(source), output_folder=str(output))
    state = SimpleNamespace(store=store, images={image.image_id: image}, admissions={image.image_id: admission},
                            workspace_manager=SimpleNamespace(active_workspace=workspace),
                            workspace_image_ids={image.image_id}, workspace_admission_ids={image.image_id})
    app = SimpleNamespace(state=state, version="synthetic-test")
    return SimpleNamespace(app=app, service=DatasetManifestService(app), store=store,
                           image=image, case=case, source=source, output=output, source_path=path)


def test_snapshot_collision_preserves_existing_owner_directory(rig, monkeypatch):
    class FixedTime:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 10, 21, tzinfo=timezone.utc)
    monkeypatch.setattr(dataset, "datetime", FixedTime)
    monkeypatch.setattr(dataset, "uuid4", lambda: SimpleNamespace(hex="f" * 32))
    existing = rig.output / "dataset-snapshot-20261021T000000Z-ffffffff"
    existing.mkdir()
    keep = existing / "owner.txt"
    keep.write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError):
        rig.service.export_snapshot()
    assert keep.read_text(encoding="utf-8") == "preserve"


def preview_and_export(rig):
    preview = rig.service.snapshot_preview(include_grade_folders=True)
    return rig.service.export_snapshot(include_grade_folders=True, expected_workspace_id=preview["workspace_id"],
                                       expected_source_state_digest=preview["source_state_digest"]["digest"],
                                       expected_grading_plan_sha256=preview["grading_folders"]["plan_sha256"])


def folder_manifest(rig, result):
    return json.loads((rig.output / result["directory_name"] / "grading_folders/manifest.json").read_text())


@pytest.mark.parametrize("grade", range(5))
def test_current_confirmed_grade_copies_exact_original_and_hash_revision_manifest(rig, grade):
    rig.case["reviewed_grade"] = rig.case["clinician_review"]["final_grade"] = grade
    before = deepcopy(rig.store.cases)
    source = rig.source_path.read_bytes()
    result = preview_and_export(rig)
    root = rig.output / result["directory_name"]
    manifest = folder_manifest(rig, result)
    item = manifest["items"][0]
    assert item["group"] == f"Grade{grade}" and item["case_revision"] == 3 and item["review_revision"] == 2
    assert (root / item["output_path"]).read_bytes() == source
    assert item["output_sha256"] == hashlib.sha256(source).hexdigest()
    assert rig.source_path.read_bytes() == source and rig.store.cases == before
    assert rig.source_path.name not in item["output_path"]
    for relative, expected in result["receipt"]["file_sha256"].items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected
    assert manifest["role_verification"] == "NOT_ESTABLISHED_BY_FOLDER_ORGANIZATION"
    assert result["manifest"]["negative_policy"]["training_negative_authorized"] is False


@pytest.mark.parametrize("state,group", [("NOT_REVIEWED", "UNREVIEWED"), ("UNGRADABLE", "UNGRADABLE"), ("NEEDS_SECOND_REVIEW", "UNDETERMINED")])
def test_non_numeric_states_never_assign_ai_suggestion_to_grade_folder(rig, state, group):
    rig.case.update(grade_status=state, reviewed_grade=None, clinician_review=None,
                    **{"global": {"model_id": "retfound-aptos5", "model_version": "fixture", "grade": 4}})
    result = preview_and_export(rig)
    item = folder_manifest(rig, result)["items"][0]
    assert item["group"] == group and item["confirmed_grade"] is None
    assert not list((rig.output / result["directory_name"] / "grading_folders").glob("Grade*"))


@pytest.mark.parametrize("defect", ["missing_source_hash", "future_review", "wrong_grade", "bool_grade", "no_action", "naive_time"])
def test_incomplete_confirmed_review_is_explicitly_undetermined(rig, defect):
    review = rig.case["clinician_review"]
    if defect == "missing_source_hash":
        review.pop("source_sha256")
    elif defect == "future_review":
        review["revision"] = 10
    elif defect == "wrong_grade":
        review["final_grade"] = 3
    elif defect == "bool_grade":
        review["final_grade"] = True
    elif defect == "no_action":
        review.pop("review_action")
    else:
        review["timestamp"] = "2026-10-21T00:00:00"
    item = folder_manifest(rig, preview_and_export(rig))["items"][0]
    assert item["group"] == "UNDETERMINED" and item["confirmed_grade"] is None
    assert all(not list(csv.DictReader(path.open(encoding="utf-8"))) for path in rig.output.glob("dataset-snapshot-*/dr_labels.csv"))


def test_regrading_creates_new_snapshot_and_preserves_old_bytes_and_labels(rig):
    first = preview_and_export(rig)
    old_root = rig.output / first["directory_name"]
    old = {p.relative_to(old_root): p.read_bytes() for p in old_root.rglob("*") if p.is_file()}
    rig.case.update(revision=4, reviewed_grade=3)
    rig.case["clinician_review"].update(revision=4, final_grade=3)
    second = preview_and_export(rig)
    assert first["snapshot_id"] != second["snapshot_id"]
    assert folder_manifest(rig, second)["items"][0]["group"] == "Grade3"
    assert {p.relative_to(old_root): p.read_bytes() for p in old_root.rglob("*") if p.is_file()} == old


@pytest.mark.parametrize("change", ["revision", "source", "workspace", "plan"])
def test_stale_preview_is_rejected_before_directory_creation(rig, change):
    preview = rig.service.snapshot_preview(include_grade_folders=True)
    if change == "revision":
        rig.case["revision"] += 1
    elif change == "source":
        rig.app.state.images[rig.image.image_id] = replace(rig.image, data=b"changed synthetic bytes")
    elif change == "workspace":
        preview["workspace_id"] = "other"
    else:
        preview["grading_folders"]["plan_sha256"] = "f" * 64
    with pytest.raises(DatasetManifestError):
        rig.service.export_snapshot(include_grade_folders=True, expected_workspace_id=preview["workspace_id"],
                                    expected_source_state_digest=preview["source_state_digest"]["digest"],
                                    expected_grading_plan_sha256=preview["grading_folders"]["plan_sha256"])
    assert list(rig.output.iterdir()) == []


def alias(rig, grade=2, patient=None):
    name = "synthetic-alias"
    case = deepcopy(rig.case)
    case.update(image_id=name, reviewed_grade=grade)
    case["clinician_review"]["final_grade"] = grade
    if patient:
        case.update(patient_key=patient, patient_resolution_state="RESOLVED")
    rig.store.cases[name] = case
    rig.app.state.images[name] = replace(rig.image, image_id=name)
    rig.app.state.admissions[name] = deepcopy(case["admission"])
    rig.app.state.workspace_image_ids.add(name)


def test_duplicate_content_same_grade_has_one_file_and_two_revision_records(rig):
    alias(rig)
    manifest = folder_manifest(rig, preview_and_export(rig))
    assert manifest["file_count"] == 1 and manifest["record_count"] == 2
    assert manifest["duplicate_record_count"] == 1
    assert len({item["output_path"] for item in manifest["items"]}) == 1


@pytest.mark.parametrize("conflict", ["grade", "patient"])
def test_duplicate_content_conflicts_are_held_out_of_numeric_groups(rig, conflict):
    if conflict == "patient":
        rig.case.update(patient_key="PAT0001", patient_resolution_state="RESOLVED")
    alias(rig, grade=3 if conflict == "grade" else 2, patient="PAT0002" if conflict == "patient" else None)
    manifest = folder_manifest(rig, preview_and_export(rig))
    assert all(item["group"] == "UNDETERMINED" and item["confirmed_grade"] is None for item in manifest["items"])
    assert all(not list(csv.DictReader(path.open(encoding="utf-8"))) for path in rig.output.glob("dataset-snapshot-*/dr_labels.csv"))


@pytest.mark.parametrize("origin", ["WORKSPACE", "UNKNOWN"])
def test_unauthorized_source_cannot_write_any_directory_or_file(rig, origin):
    rig.case["admission"]["source_origin"] = origin
    rig.app.state.images[rig.image.image_id] = replace(rig.image, source_origin=origin)
    preview = rig.service.snapshot_preview(include_grade_folders=True)
    assert preview["can_export"] is False
    with pytest.raises(DatasetManifestError):
        rig.service.export_snapshot(include_grade_folders=True, expected_workspace_id=preview["workspace_id"],
                                    expected_source_state_digest=preview["source_state_digest"]["digest"],
                                    expected_grading_plan_sha256="0" * 64)
    assert list(rig.output.iterdir()) == [] and rig.source_path.is_file()


@pytest.mark.parametrize("grade", range(5))
def test_consented_hospital_current_grade_copies_original_without_new_clinical_labels(rig, grade):
    rig.case['admission']['source_origin'] = 'HOSPITAL_AUTHORIZED'
    rig.app.state.images[rig.image.image_id] = replace(rig.image,
        source_origin='HOSPITAL_AUTHORIZED', source_type='HOSPITAL_AUTHORIZED')
    rig.case['reviewed_grade'] = rig.case['clinician_review']['final_grade'] = grade
    before = deepcopy(rig.store.cases)
    original = rig.source_path.read_bytes()
    result = preview_and_export(rig)
    item = folder_manifest(rig, result)['items'][0]
    assert item['group'] == f'Grade{grade}'
    assert (rig.output/result['directory_name']/item['output_path']).read_bytes() == original
    assert rig.source_path.read_bytes() == original and rig.store.cases == before
    assert result['manifest']['export_authorization_summary'] == {'ALLOWED_LOCAL_AUTHORIZED_HOSPITAL': 1}


def test_consented_hospital_ai_grade_is_not_a_physician_folder_or_gold(rig):
    rig.case['admission']['source_origin'] = 'HOSPITAL_AUTHORIZED'
    rig.app.state.images[rig.image.image_id] = replace(rig.image,
        source_origin='HOSPITAL_AUTHORIZED', source_type='HOSPITAL_AUTHORIZED')
    rig.case.update(clinician_review=None, grade_status='NOT_REVIEWED', reviewed_grade=None,
                    **{'global': {'model_id':'fixture','model_version':'NO_MODEL_EXECUTED','grade':4}})
    result = preview_and_export(rig)
    assert folder_manifest(rig, result)['items'][0]['group'] == 'UNREVIEWED'
    assert result['manifest']['row_counts']['dr_labels.csv'] == 0
    assert result['manifest']['row_counts']['lesion_labels.csv'] == 0


def test_physician_folder_organization_does_not_claim_training_readiness(rig):
    rig.case['admission']['source_origin'] = 'HOSPITAL_AUTHORIZED'
    rig.case['admission']['quality_state'] = 'NEEDS_REVIEW'
    rig.app.state.images[rig.image.image_id] = replace(rig.image,
        source_origin='HOSPITAL_AUTHORIZED', source_type='HOSPITAL_AUTHORIZED')
    before = deepcopy(rig.store.cases)
    preview = rig.service.snapshot_preview(include_grade_folders=True)
    assert preview['grading_folders']['group_counts']['Grade2'] == 1
    assert preview['row_counts']['dr_labels.csv'] == 0
    result = preview_and_export(rig)
    assert folder_manifest(rig, result)['items'][0]['group'] == 'Grade2'
    assert result['manifest']['row_counts']['dr_labels.csv'] == 0
    assert result['manifest']['row_counts']['lesion_labels.csv'] == 0
    assert rig.store.cases == before


def test_origin_edit_alone_does_not_authorize_hospital_export(rig):
    rig.case['admission']['source_origin'] = 'HOSPITAL_AUTHORIZED'
    preview = rig.service.snapshot_preview(include_grade_folders=True)
    assert not preview['can_export']
    assert preview['export_authorization_summary'] == {'BLOCKED_SOURCE_IDENTITY_OR_AUTHORIZATION_MISMATCH':1}
    with pytest.raises(DatasetManifestError):
        rig.service.export_snapshot(include_grade_folders=True,
            expected_workspace_id=preview['workspace_id'],
            expected_source_state_digest=preview['source_state_digest']['digest'],
            expected_grading_plan_sha256='0'*64)
    assert list(rig.output.iterdir()) == []


@pytest.mark.parametrize("defect", ["missing", "source_changed", "conflicting_hash", "metadata_changed", "unsupported_format", "excluded"])
def test_invalid_source_has_explicit_skip_reason_and_no_output(rig, defect):
    if defect == "missing":
        rig.app.state.images.pop(rig.image.image_id)
    elif defect == "source_changed":
        rig.case["admission"]["integrity_status"] = "SOURCE_CHANGED"
    elif defect == "conflicting_hash":
        rig.case.update(image_sha256=rig.image.sha256, source_sha256="f" * 64)
    elif defect == "metadata_changed":
        rig.case["admission"]["source_metadata"] = {"integrity_status": "SOURCE_CHANGED"}
    elif defect == "unsupported_format":
        rig.app.state.images[rig.image.image_id] = replace(rig.image, media_type="unknown/format")
    else:
        rig.case["queue_state"] = "EXCLUDED"
    preview = rig.service.snapshot_preview(include_grade_folders=True)
    assert preview["grading_folders"]["status"] == "NO_COPYABLE_SOURCES"
    assert preview["grading_folders"]["skipped_count"] == 1
    with pytest.raises(DatasetManifestError):
        preview_and_export(rig)
    assert list(rig.output.iterdir()) == []


def test_source_filename_and_record_traversal_never_determine_copy_path(rig):
    bad_id = "../../synthetic"
    case = rig.store.cases.pop(rig.image.image_id)
    case["image_id"] = bad_id
    rig.store.cases[bad_id] = case
    rig.app.state.images = {bad_id: replace(rig.image, image_id=bad_id, filename="../unsafe.png")}
    rig.app.state.admissions = {bad_id: case["admission"]}
    rig.app.state.workspace_image_ids = {bad_id}
    rig.app.state.workspace_admission_ids = {bad_id}
    result = preview_and_export(rig)
    item = folder_manifest(rig, result)["items"][0]
    assert ".." not in item["output_path"] and "unsafe" not in item["output_path"]
    assert not (rig.output.parent / "unsafe.png").exists()


def test_failed_verification_removes_only_new_snapshot_and_never_publishes_success(rig, monkeypatch):
    owner = rig.output / "owner-file.txt"
    owner.write_text("preserve")
    def fail(*args):
        raise DatasetManifestError("Synthetic verification failure")
    monkeypatch.setattr(rig.service, "_verify_snapshot_file_hashes", fail)
    with pytest.raises(DatasetManifestError):
        preview_and_export(rig)
    assert list(rig.output.iterdir()) == [owner]
    assert owner.read_text() == "preserve" and rig.source_path.read_bytes() == rig.image.data


def test_preview_is_deterministic_read_only_and_metadata_snapshot_remains_compatible(rig):
    first = rig.service.snapshot_preview(include_grade_folders=True)
    second = rig.service.snapshot_preview(include_grade_folders=True)
    assert first == second and list(rig.output.iterdir()) == []
    result = rig.service.export_snapshot()
    assert "grading_folders" not in result["manifest"]
    assert not (rig.output / result["directory_name"] / "grading_folders").exists()


def test_filename_prefix_collision_extends_hash_without_overwriting():
    from dr_support.services.grading_folders import _copy_path, GradingFolderError
    prefix = "a" * 24
    first = _copy_path("Grade2", prefix + "b" * 40, ".png", b"first", {})
    files = {first: b"first"}
    second = _copy_path("Grade2", prefix + "c" * 40, ".png", b"second", files)
    assert second != first and files[first] == b"first"
    full = "a" * 64
    occupied = {f"grading_folders/Grade2/image_{full[:n]}.png": b"owner" for n in (24, 40, 64)}
    with pytest.raises(GradingFolderError):
        _copy_path("Grade2", full, ".png", b"different", occupied)
    assert set(occupied.values()) == {b"owner"}


@pytest.mark.parametrize("failure", ["space", "redirect", "input_output_overlap"])
def test_output_preflight_fails_before_any_snapshot_is_created(rig, monkeypatch, failure):
    if failure == "space":
        monkeypatch.setattr(dataset.shutil, "disk_usage", lambda root: SimpleNamespace(free=0))
    elif failure == "redirect":
        monkeypatch.setattr(dataset, "has_reparse_component", lambda root: True)
    else:
        rig.app.state.workspace_manager.active_workspace.input_folder = str(rig.output)
    with pytest.raises(DatasetManifestError):
        preview_and_export(rig)
    assert list(rig.output.iterdir()) == []


def _http_client(rig):
    """Execute actual route/class definitions without importing the startup factory."""
    import ast
    from typing import Literal
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.testclient import TestClient
    from pydantic import Field
    from dr_support.contracts import Contract
    source = (Path(__file__).parents[1] / "dr_support/api/dataset.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))]
    namespace = {"Contract": Contract, "Field": Field, "Literal": Literal, "Query": Query,
                 "HTTPException": HTTPException, "DatasetManifestService": DatasetManifestService,
                 "DatasetManifestError": DatasetManifestError, "__name__": "memory_dataset_routes"}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), "memory_dataset_routes", "exec"), namespace)
    app = FastAPI()
    for key, value in vars(rig.app.state).items():
        setattr(app.state, key, value)
    namespace["install_dataset_routes"](app)
    return TestClient(app)


def test_existing_http_snapshot_route_serializes_opt_in_folder_plan(rig):
    client = _http_client(rig)
    preview = client.get("/v2/dataset/snapshot/preview?include_grade_folders=true")
    assert preview.status_code == 200
    body = preview.json()
    assert body["grading_folders"]["group_counts"]["Grade2"] == 1
    exported = client.post("/v2/dataset/snapshot", json={"include_grade_folders": True,
        "expected_workspace_id": body["workspace_id"], "expected_source_state_digest": body["source_state_digest"]["digest"],
        "expected_grading_plan_sha256": body["grading_folders"]["plan_sha256"]})
    assert exported.status_code == 200
    assert exported.json()["manifest"]["grading_folders"]["file_count"] == 1
    assert client.get(f'/v2/dataset/snapshots/{exported.json()["snapshot_id"]}').status_code == 200


def test_http_request_cannot_enable_hospital_export_or_smuggle_move_options(rig):
    client = _http_client(rig)
    assert client.post("/v2/dataset/snapshot", json={"include_grade_folders": "true"}).status_code == 422
    assert client.post("/v2/dataset/snapshot", json={"include_grade_folders": True, "move_originals": True}).status_code == 422
    rig.case["admission"]["source_origin"] = "HOSPITAL_AUTHORIZED"
    assert client.post("/v2/dataset/snapshot", json={"include_grade_folders": True, "expected_workspace_id": "synthetic-workspace",
        "expected_source_state_digest": "0" * 64, "expected_grading_plan_sha256": "0" * 64}).status_code == 409
    assert list(rig.output.iterdir()) == []


def test_lesion_labels_stay_independent_of_unreviewed_grade(rig):
    from dr_support.presentation import annotation_set_hash
    rig.case.update(grade_status="NOT_REVIEWED", reviewed_grade=None, clinician_review=None,
                    human_annotations=[{"shape_id": "synthetic-human-box", "type": "rectangle", "label": "HEMORRHAGE",
                        "geometry": {"x": 2, "y": 3, "width": 4, "height": 5}, "source": "HUMAN",
                        "reviewer": "Synthetic clinician", "created_at": "2026-10-21T00:00:00Z"}],
                    lesion_review_state="REVIEWED", annotation_confirmation={"reviewer": "Synthetic clinician",
                        "timestamp": "2026-10-21T00:00:00Z", "source_sha256": rig.image.sha256})
    rig.case["confirmed_annotation_hash"] = annotation_set_hash(rig.case)
    before = deepcopy(rig.case)
    result = preview_and_export(rig)
    root = rig.output / result["directory_name"]
    assert folder_manifest(rig, result)["items"][0]["group"] == "UNREVIEWED"
    assert list(csv.DictReader((root / "dr_labels.csv").open(encoding="utf-8"))) == []
    labels = list(csv.DictReader((root / "lesion_labels.csv").open(encoding="utf-8")))
    assert len(labels) == 1 and labels[0]["annotation_source"] == "HUMAN"
    assert rig.case == before


@pytest.mark.parametrize("marker", ["reviewer", "workspace"])
def test_test_only_grade_goes_to_its_own_folder_and_is_not_training_ready(rig, marker):
    if marker == "reviewer":
        rig.case["clinician_review"]["reviewer"] = "TEST_ONLY_ENGINEERING"
    else:
        rig.app.state.workspace_manager.active_workspace.name = "TEST_ONLY rehearsal"
    result = preview_and_export(rig)
    item = folder_manifest(rig, result)["items"][0]
    assert item["group"] == "TEST_ONLY" and item["confirmed_grade"] is None and item["reason"] == "TEST_ONLY_LABEL"
    assert (rig.output / result["directory_name"] / item["output_path"]).parts[-2] == "TEST_ONLY"
    assert result["manifest"]["grade_label_selection_policy"].startswith("grading-folders.v3")


def test_test_only_rows_are_left_out_of_training_label_files(rig):
    rig.case["annotation_confirmation"] = None
    baseline = rig.service.snapshot_preview(include_grade_folders=False)["row_counts"]
    rig.case["clinician_review"]["reviewer"] = "TEST_ONLY_ENGINEERING"
    rig.app.state.admissions[rig.image.image_id]["reviewed_by"] = "TEST_ONLY_ENGINEERING"
    tagged = rig.service.snapshot_preview(include_grade_folders=False)["row_counts"]
    assert tagged["dr_labels.csv"] == 0 and tagged["lesion_labels.csv"] == 0
    assert baseline["dr_labels.csv"] == 1  # the same record is a training label without the tag
    rows = rig.service._rows([rig.case])[0]
    assert rows[0]["label_class"] == "TEST_ONLY" and rows[0]["dataset_status"] == "Test data (not for training)"
