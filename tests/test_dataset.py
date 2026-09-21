import csv
import hashlib
import io
import json

from fastapi.testclient import TestClient
from PIL import Image

from dr_support.api import create_app
from dr_support.contracts import LABELS


def _workspace_client(tmp_path):
    app = create_app(tmp_path / "fallback.sqlite", include_samples=False)
    client = TestClient(app)
    input_folder = tmp_path / "input"
    output_folder = tmp_path / "output"
    input_folder.mkdir()
    output_folder.mkdir()
    response = client.post("/v1/workspaces", json={
        "name": "Dataset fixtures",
        "input_folder": str(input_folder),
        "output_folder": str(output_folder),
        "database_path": str(tmp_path / "workspace.sqlite"),
    })
    assert response.status_code == 200
    # The synthetic fixture is intentionally retained by the legacy factory;
    # include it explicitly when this test models an active workspace record.
    app.state.workspace_image_ids.add("SYNTH_001")
    app.state.workspace_admission_ids.add("SYNTH_001")
    return app, client, output_folder


def _human_annotations(revision):
    return {
        "revision": revision,
        "reviewer": "Dataset clinician",
        "annotations": [
            {"type": "rectangle", "label": "MICROANEURYSM",
             "geometry": {"x": 10, "y": 20, "width": 30, "height": 25}, "locked": False},
            {"type": "polygon", "label": "HEMORRHAGE",
             "geometry": {"points": [[50, 50], [80, 50], [70, 90]]}},
            {"type": "point", "label": "HARD_EXUDATE", "geometry": {"x": 100, "y": 120}},
            {"type": "circle", "label": "SOFT_EXUDATE",
             "geometry": {"cx": 160, "cy": 140, "radius": 12}},
        ],
    }


def test_manifest_preserves_identity_provenance_geometry_and_export_files(tmp_path):
    app, client, output_folder = _workspace_client(tmp_path)
    assert client.post("/v1/infer/global", json={"image_id": "SYNTH_001", "model_id": "mock-global"}).status_code == 200
    assert client.post("/v1/infer/lesion-roi", json={"image_id": "SYNTH_001", "model_id": "mock-lesion"}).status_code == 200
    case = client.get("/v1/cases/SYNTH_001").json()
    saved = client.put("/v1/cases/SYNTH_001/annotations", json=_human_annotations(case["revision"]))
    assert saved.status_code == 200
    reviewed = client.post("/v1/cases/SYNTH_001/review", json={
        "revision": saved.json()["revision"],
        "action": "CORRECT_GRADE",
        "reviewer": "Dataset clinician",
        "grade": 3,
    })
    assert reviewed.status_code == 200

    before_case = app.state.store.get("SYNTH_001")
    source_bytes = app.state.images["SYNTH_001"].data
    preview = client.get("/v1/dataset/manifest")
    assert preview.status_code == 200
    body = preview.json()
    assert body["image_count"] == 1
    assert body["annotation_count"] == 5
    image = body["images"][0]
    assert image["image_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert image["width"] == 640 and image["height"] == 480
    assert image["ai_grade"] == 2 and image["clinician_grade"] == 3
    assert image["include_in_training"] is True
    assert image["eligibility_reason"] == "ELIGIBLE"
    assert {row["annotation_source"] for row in body["annotations"]} == {"AI", "HUMAN"}
    assert {row["label"] for row in body["annotations"]} == set(LABELS.values())
    assert {row["shape_type"] for row in body["annotations"]} == {"rectangle", "polygon", "point", "circle"}
    ai_row = next(row for row in body["annotations"] if row["annotation_source"] == "AI")
    assert ai_row["include_in_training"] is False
    assert ai_row["eligibility_reason"] == "AI_ONLY_UNVERIFIED"
    human_rows = [row for row in body["annotations"] if row["annotation_source"] == "HUMAN"]
    assert all(row["include_in_training"] is False for row in human_rows)
    assert json.loads(next(row for row in human_rows if row["shape_type"] == "circle")["geometry_json"]) == {
        "cx": 160.0, "cy": 140.0, "radius": 12.0,
    }
    summary = client.get("/v1/dataset/manifest?include_annotations=false").json()
    assert summary["annotation_count"] == 5
    assert summary["annotations"] == []

    export = client.post("/v1/dataset/export")
    assert export.status_code == 200
    export_info = export.json()
    export_dir = output_folder / export_info["directory_name"]
    assert export_dir.is_dir()
    assert {path.name for path in export_dir.iterdir()} == {"manifest.json", "images.csv", "annotations.csv"}
    manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
    images_csv = (export_dir / "images.csv").read_bytes()
    annotations_csv = (export_dir / "annotations.csv").read_bytes()
    assert manifest["image_count"] == 1 and manifest["annotation_count"] == 5
    assert manifest["file_sha256"]["images.csv"] == hashlib.sha256(images_csv).hexdigest()
    assert manifest["file_sha256"]["annotations.csv"] == hashlib.sha256(annotations_csv).hexdigest()
    assert str(tmp_path) not in (export_dir / "manifest.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in images_csv.decode("utf-8")
    assert csv.DictReader(io.StringIO(images_csv.decode("utf-8"))).fieldnames == [
        "image_id", "filename", "image_sha256", "width", "height", "modality", "source_type",
        "patient_key", "laterality", "patient_resolution_method", "laterality_resolution_method",
        "modality_admission", "quality_state", "queue_state", "ai_grade", "ai_model_id",
        "ai_model_version", "ai_confidence", "clinician_grade", "grade_review_source",
        "review_status", "reviewer", "reviewed_at", "human_annotation_count", "ai_lesion_count",
        "cvat_annotation_count", "verification_status", "include_in_training", "eligibility_reason",
    ]
    assert app.state.store.get("SYNTH_001") == before_case
    assert app.state.images["SYNTH_001"].data == source_bytes

    second = client.post("/v1/dataset/export")
    assert second.status_code == 200
    assert second.json()["directory_name"] != export_info["directory_name"]


def test_manifest_scope_uses_active_workspace_scan_records(tmp_path):
    input_folder = tmp_path / "input"
    output_folder = tmp_path / "output"
    input_folder.mkdir()
    output_folder.mkdir()
    image_path = input_folder / "PAT0001_L1.png"
    Image.new("RGB", (320, 240), (120, 45, 30)).save(image_path)

    app = create_app(tmp_path / "fallback.sqlite", include_samples=False)
    client = TestClient(app)
    created = client.post("/v1/workspaces", json={
        "name": "Scanned dataset",
        "input_folder": str(input_folder),
        "output_folder": str(output_folder),
        "database_path": str(tmp_path / "workspace.sqlite"),
    })
    assert created.status_code == 200

    body = client.get("/v1/dataset/manifest").json()
    assert body["workspace_name"] == "Scanned dataset"
    assert body["image_count"] == 1
    assert body["images"][0]["image_id"] == hashlib.sha256(image_path.read_bytes()).hexdigest()
    assert body["images"][0]["filename"] == "PAT0001_L1.png"


def test_manifest_eligibility_rejects_ai_only_excluded_unresolved_and_ungradable(tmp_path):
    app, client, _ = _workspace_client(tmp_path)
    client.post("/v1/infer/global", json={"image_id": "SYNTH_001", "model_id": "mock-global"})
    row = client.get("/v1/dataset/manifest").json()["images"][0]
    assert row["include_in_training"] is False
    assert row["eligibility_reason"] == "NO_FINAL_CLINICIAN_GRADE"

    case = client.get("/v1/cases/SYNTH_001").json()
    excluded = client.post("/v1/cases/SYNTH_001/queue", json={"revision": case["revision"], "action": "EXCLUDE"})
    assert excluded.status_code == 200
    row = client.get("/v1/dataset/manifest").json()["images"][0]
    assert row["include_in_training"] is False and row["eligibility_reason"] == "QUEUE_EXCLUDED"

    restored = client.post("/v1/cases/SYNTH_001/queue", json={
        "revision": excluded.json()["revision"], "action": "RESTORE",
    })
    assert restored.status_code == 200
    case = app.state.store.get("SYNTH_001")
    case["admission"] = {**case["admission"], "modality_admission": "NEEDS_REVIEW"}
    app.state.store.put(case)
    row = client.get("/v1/dataset/manifest").json()["images"][0]
    assert row["eligibility_reason"] == "ADMISSION_UNRESOLVED"

    case = app.state.store.get("SYNTH_001")
    case["admission"] = {
        **case["admission"], "modality_admission": "FUNDUS_ACCEPTED", "quality_state": "UNGRADABLE",
    }
    app.state.store.put(case)
    row = client.get("/v1/dataset/manifest").json()["images"][0]
    assert row["eligibility_reason"] == "UNGRADABLE"


def test_manifest_does_not_export_non_pseudonymous_patient_keys(tmp_path):
    app, client, _ = _workspace_client(tmp_path)
    case = app.state.store.get("SYNTH_001")
    case["patient_key"] = "Jane Doe"
    app.state.store.put(case)

    row = client.get("/v1/dataset/manifest").json()["images"][0]
    assert row["patient_key"] is None


def test_confirmed_cvat_annotations_are_provenanced_but_unreviewed_import_is_not_ready(tmp_path):
    _, client, _ = _workspace_client(tmp_path)
    base = "/v1/cases/SYNTH_001"
    initial = client.get(base).json()
    payload = {
        "revision": initial["revision"],
        "image_sha256": initial["image_sha256"],
        "label_ids": {label: index for index, label in enumerate(LABELS.values(), 1)},
        "annotations": {"version": 0, "shapes": [{
            "id": 7, "frame": 0, "label_id": 1, "type": "rectangle", "points": [10, 20, 30, 40],
        }]},
    }
    imported = client.post(base + "/manual-sync", json=payload).json()
    before = client.get("/v1/dataset/manifest").json()["annotations"][0]
    assert before["annotation_source"] == "CVAT_IMPORTED"
    assert before["include_in_training"] is False
    assert before["eligibility_reason"] == "NO_FINAL_CLINICIAN_GRADE"

    graded = client.post(base + "/review", json={
        "revision": imported["revision"], "action": "CORRECT_GRADE", "reviewer": "CVAT reviewer", "grade": 2,
    }).json()
    confirmed = client.post(base + "/review", json={
        "revision": graded["revision"], "action": "CONFIRM_ANNOTATIONS", "reviewer": "CVAT reviewer",
    })
    assert confirmed.status_code == 200
    rows = client.get("/v1/dataset/manifest").json()["annotations"]
    assert rows[0]["verification_status"] == "CONFIRMED"
    assert rows[0]["include_in_training"] is True
    assert rows[0]["reviewer"] == "CVAT reviewer"
