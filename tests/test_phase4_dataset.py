import hashlib
import csv
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dr_support.api import create_app
from dr_support.contracts import LABELS
from dr_support.services.dataset import _source_state_receipt


def _workspace_client(tmp_path):
    app = create_app(tmp_path / "fallback.sqlite", include_samples=False)
    client = TestClient(app)
    input_folder = tmp_path / "input"
    output_folder = tmp_path / "output"
    input_folder.mkdir()
    output_folder.mkdir()
    response = client.post(
        "/v1/workspaces",
        json={
            "name": "Phase 4 synthetic workspace",
            "input_folder": str(input_folder),
            "output_folder": str(output_folder),
            "database_path": str(tmp_path / "workspace.sqlite"),
        },
    )
    assert response.status_code == 200
    app.state.workspace_image_ids.add("SYNTH_001")
    app.state.workspace_admission_ids.add("SYNTH_001")
    return app, client, output_folder


def test_workspace_data_is_bounded_and_exposes_detail(tmp_path):
    _app, client, _output = _workspace_client(tmp_path)

    response = client.get("/v2/workspace-data/records?limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "s4.workspace-data.v1"
    assert body["limit"] == 1
    assert body["records"][0]["source_origin"] == "SYNTHETIC"
    assert body["records"][0]["export_authorization"] == "ALLOWED_ENGINEERING_SYNTHETIC"

    detail = client.get("/v2/workspace-data/records/SYNTH_001")
    assert detail.status_code == 200
    assert detail.json()["processing"]["status"] == "UNAVAILABLE"
    assert detail.json()["explainability"]["status"] == "UNAVAILABLE"


def test_untouched_ai_suggestion_is_never_gold(tmp_path):
    _app, client, output = _workspace_client(tmp_path)
    assert client.post(
        "/v1/infer/lesion-roi",
        json={"image_id": "SYNTH_001", "model_id": "mock-lesion"},
    ).status_code == 200
    case = client.get("/v1/cases/SYNTH_001").json()
    confirmed = client.post(
        "/v1/cases/SYNTH_001/review",
        json={
            "revision": case["revision"],
            "action": "CONFIRM_ANNOTATIONS",
            "reviewer": "Phase 4 reviewer",
        },
    )
    assert confirmed.status_code == 200

    row = client.get("/v1/dataset/manifest").json()["annotations"][0]
    assert row["annotation_source"] == "AI"
    assert row["include_in_training"] is False

    preview = client.get("/v2/dataset/snapshot/preview").json()
    assert preview["row_counts"]["ai_evidence.csv"] == 1

    snapshot = client.post("/v2/dataset/snapshot")
    assert snapshot.status_code == 200
    snapshot_dir = output / snapshot.json()["directory_name"]
    lesion_csv = (snapshot_dir / "lesion_labels.csv").read_text(encoding="utf-8")
    assert row["annotation_id"] not in lesion_csv


def test_corrected_ai_suggestion_is_gold_only_after_confirmation(tmp_path):
    _app, client, output = _workspace_client(tmp_path)
    assert client.post(
        "/v1/infer/lesion-roi",
        json={"image_id": "SYNTH_001", "model_id": "mock-lesion"},
    ).status_code == 200
    case = client.get("/v1/cases/SYNTH_001").json()
    detection = case["lesion_review"]["lesions"][0]
    corrected = client.post(
        "/v1/cases/SYNTH_001/lesion-review",
        json={
            "revision": case["revision"],
            "reviewer": "Phase 4 reviewer",
            "detection_id": detection["detection_id"],
            "action": "CORRECT",
            "label": "MICROANEURYSM",
        },
    )
    assert corrected.status_code == 200
    confirmed = client.post(
        "/v1/cases/SYNTH_001/review",
        json={
            "revision": corrected.json()["revision"],
            "action": "CONFIRM_ANNOTATIONS",
            "reviewer": "Phase 4 reviewer",
        },
    )
    assert confirmed.status_code == 200

    row = next(
        item for item in client.get("/v1/dataset/manifest").json()["annotations"]
        if item["annotation_id"] == detection["detection_id"]
    )
    assert row["annotation_source"] == "HUMAN_CORRECTION"
    assert row["include_in_training"] is True
    snapshot = client.post("/v2/dataset/snapshot")
    assert snapshot.status_code == 200
    lesion_csv = (output / snapshot.json()["directory_name"] / "lesion_labels.csv").read_text(encoding="utf-8")
    assert detection["detection_id"] in lesion_csv


def test_confirmed_imported_lesion_is_ready_without_dr_grade(tmp_path):
    _app, client, output = _workspace_client(tmp_path)
    base = "/v1/cases/SYNTH_001"
    initial = client.get(base).json()
    imported = client.post(
        base + "/manual-sync",
        json={
            "revision": initial["revision"],
            "image_sha256": initial["image_sha256"],
            "label_ids": {label: index for index, label in enumerate(LABELS.values(), 1)},
            "annotations": {"version": 0, "shapes": [{
                "id": 7, "frame": 0, "label_id": 1, "type": "rectangle", "points": [10, 20, 30, 40],
            }]},
        },
    )
    assert imported.status_code == 200
    confirmed = client.post(
        base + "/review",
        json={
            "revision": imported.json()["revision"],
            "action": "CONFIRM_ANNOTATIONS",
            "reviewer": "Phase 4 reviewer",
        },
    )
    assert confirmed.status_code == 200

    record = client.get("/v2/workspace-data/records/SYNTH_001").json()["record"]
    assert record["dr_grade_training_ready"] is False
    assert record["lesion_positive_training_ready"] is True

    snapshot = client.post("/v2/dataset/snapshot")
    assert snapshot.status_code == 200
    snapshot_dir = output / snapshot.json()["directory_name"]
    lesion_csv = (snapshot_dir / "lesion_labels.csv").read_text(encoding="utf-8")
    assert "cvat-SYNTH_001-7" in lesion_csv


def test_geometry_only_ai_correction_is_human_lineage(tmp_path):
    _app, client, _output = _workspace_client(tmp_path)
    assert client.post(
        "/v1/infer/lesion-roi",
        json={"image_id": "SYNTH_001", "model_id": "mock-lesion"},
    ).status_code == 200
    case = client.get("/v1/cases/SYNTH_001").json()
    detection = case["lesion_review"]["lesions"][0]
    corrected = client.post(
        "/v1/cases/SYNTH_001/lesion-review",
        json={
            "revision": case["revision"],
            "reviewer": "Phase 4 reviewer",
            "detection_id": detection["detection_id"],
            "action": "CORRECT",
            "rectangle": [20, 20, 80, 80],
        },
    )
    assert corrected.status_code == 200
    confirmed = client.post(
        "/v1/cases/SYNTH_001/review",
        json={
            "revision": corrected.json()["revision"],
            "action": "CONFIRM_ANNOTATIONS",
            "reviewer": "Phase 4 reviewer",
        },
    )
    assert confirmed.status_code == 200
    row = next(
        item for item in client.get("/v1/dataset/manifest").json()["annotations"]
        if item["annotation_id"] == detection["detection_id"]
    )
    assert row["annotation_source"] == "HUMAN_CORRECTION"
    assert row["score"] is None
    assert row["source_detection_id"] == detection["detection_id"]
    assert row["include_in_training"] is True


def test_unconfirmed_patient_key_does_not_create_training_group(tmp_path):
    app, client, _output = _workspace_client(tmp_path)
    case = app.state.store.get("SYNTH_001")
    case["patient_key"] = "patient-001"
    case["patient_resolution_state"] = "UNLINKED"
    app.state.store.put(case)
    assert client.get("/v2/workspace-data/records").json()["records"][0]["training_group_key"] is None

    case = app.state.store.get("SYNTH_001")
    case["patient_resolution_state"] = "RESOLVED"
    app.state.store.put(case)
    assert client.get("/v2/workspace-data/records").json()["records"][0]["training_group_key"] == "patient:PATIENT-001"


@pytest.mark.parametrize("origin", ["WORKSPACE", "UNKNOWN"])
def test_blocked_origin_is_visible_but_cannot_create_snapshot(tmp_path, origin):
    app, client, _output = _workspace_client(tmp_path)
    case = app.state.store.get("SYNTH_001")
    case["admission"] = {**(case.get("admission") or app.state.admissions["SYNTH_001"]), "source_origin": origin}
    app.state.store.put(case)

    preview = client.get("/v2/dataset/snapshot/preview")
    assert preview.status_code == 200
    assert preview.json()["source_origin_summary"][origin] == 1
    assert preview.json()["blocked_record_count"] == 1
    assert preview.json()["can_export"] is False
    assert client.post("/v2/dataset/snapshot").status_code == 409
    assert client.post("/v1/dataset/export").status_code == 409
    assert client.post("/v1/dataset/export/grouped-by-grade", json={}).status_code == 409


def test_reviewed_none_is_completeness_only_and_receipt_hashes_files(tmp_path):
    app, client, output = _workspace_client(tmp_path)
    case = app.state.store.get("SYNTH_001")
    case["annotation_completeness"] = {
        "CORE": {
            "state": "REVIEWED_NONE_FOUND",
            "reviewer": "Phase 4 reviewer",
            "timestamp": "2026-10-04T00:00:00+00:00",
            "taxonomy_version": "core-lesions-v1",
        },
    }
    app.state.store.put(case)

    snapshot = client.post("/v2/dataset/snapshot")
    assert snapshot.status_code == 200
    body = snapshot.json()
    snapshot_dir = output / body["directory_name"]
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((snapshot_dir / "receipt.json").read_text(encoding="utf-8"))
    completeness = list(csv.DictReader((snapshot_dir / "review_completeness.csv").read_text(encoding="utf-8").splitlines()))
    lesion_labels = list(csv.DictReader((snapshot_dir / "lesion_labels.csv").read_text(encoding="utf-8").splitlines()))

    core = next(row for row in completeness if row["group"] == "CORE")
    advanced = next(row for row in completeness if row["group"] == "ADVANCED")
    assert core["state"] == "REVIEWED_NONE_FOUND"
    assert core["negative_training_authorized"] == "False"
    assert advanced["state"] == "NOT_REVIEWED"
    assert lesion_labels == []
    assert manifest["negative_policy"]["training_negative_authorized"] is False
    assert receipt["source_state_digest"] == manifest["source_state_digest"]
    for filename, digest in manifest["file_sha256"].items():
        assert hashlib.sha256((snapshot_dir / filename).read_bytes()).hexdigest() == digest

    first_snapshot = snapshot_dir
    case = app.state.store.get("SYNTH_001")
    case["admission"] = {
        **(case.get("admission") or app.state.admissions["SYNTH_001"]),
        "source_origin": "WORKSPACE",
    }
    app.state.store.put(case)
    assert client.post("/v2/dataset/snapshot").status_code == 409
    assert first_snapshot.is_dir()


def test_snapshot_removes_partial_output_on_final_hash_mismatch(tmp_path, monkeypatch):
    _app, client, output = _workspace_client(tmp_path)
    original_write_bytes = Path.write_bytes

    def tamper_records(path, data):
        written = original_write_bytes(path, data)
        if path.name == "records.csv":
            original_write_bytes(path, b"tampered")
        return written

    monkeypatch.setattr(Path, "write_bytes", tamper_records)

    response = client.post("/v2/dataset/snapshot")

    assert response.status_code == 409
    assert list(output.glob("dataset-snapshot-*")) == []


def test_missing_source_keeps_workspace_metadata_and_blocks_only_bytes(tmp_path):
    app, client, output = _workspace_client(tmp_path)
    app.state.images.pop("SYNTH_001")

    record = client.get("/v2/workspace-data/records/SYNTH_001")
    assert record.status_code == 200
    body = record.json()["record"]
    assert body["source_available"] is False
    assert body["source_sha256"]
    assert body["source_origin"] == "SYNTHETIC"

    snapshot = client.post("/v2/dataset/snapshot")
    assert snapshot.status_code == 200
    assert (output / snapshot.json()["directory_name"] / "records.csv").is_file()


def test_source_state_digest_is_deterministic_and_revision_sensitive():
    cases = [{"image_id": "b", "revision": 2, "value": "two"}, {"image_id": "a", "revision": 1, "value": "one"}]
    first = _source_state_receipt("workspace", cases)
    second = _source_state_receipt("workspace", list(reversed(cases)))
    changed = _source_state_receipt("workspace", [{**cases[0], "revision": 3}, cases[1]])

    assert first["digest"] == second["digest"]
    assert first["digest"] != changed["digest"]
    assert first["case_revisions"][0]["payload_sha256"] == hashlib.sha256(b'{"value":"one"}').hexdigest()
