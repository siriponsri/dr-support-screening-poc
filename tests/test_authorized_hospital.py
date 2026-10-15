"""Private authorized-hospital provenance and fail-closed export tests."""

import hashlib
import io
import json

from fastapi.testclient import TestClient
from PIL import Image

from dr_support.api import create_app
from dr_support.services.model_api import create_app as create_model_api_app
from dr_support.services.admission import scan_input_folder
from dr_support.services.source_policy import (
    HOSPITAL_ORIGIN,
    hospital_ingest_enabled,
    source_allowed_for_model,
)


def _jpeg_bytes(color=(30, 90, 60)) -> bytes:
    image = Image.new("RGB", (192, 128), color)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def _configure_hospital(monkeypatch, root, *, modality="UWF") -> None:
    monkeypatch.setenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOT", str(root))
    monkeypatch.setenv("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.setenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_MODALITY", modality)
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)


def test_authorized_hospital_linkage_is_opaque_and_sequence_bound(tmp_path, monkeypatch):
    root = tmp_path / "hospital"
    _configure_hospital(monkeypatch, root)
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_LINKAGE_KEY", "test-private-linkage-key-0123456789012345")
    (root / "PATIENT01_L2.jpg").write_bytes(_jpeg_bytes())
    record = next(iter(scan_input_folder(
        root, source_origin=HOSPITAL_ORIGIN, retinal_modality="UWF",
        retinal_modality_method="AUTHORIZED_SOURCE",
    ).records.values()))
    assert record["trusted_patient_key"].startswith("HOSPITAL-")
    assert record["trusted_patient_key"] != "PATIENT01"
    assert record["trusted_laterality"] == "LEFT"
    assert record["trusted_capture_sequence"] == 2
    assert "PATIENT01" not in json.dumps(record)


def test_default_workspace_remains_workspace_and_unrelated_root_is_not_promoted(tmp_path, monkeypatch):
    root = tmp_path / "hospital"
    root.mkdir()
    root.chmod(0o700)
    (root / "source.jpg").write_bytes(_jpeg_bytes())
    _configure_hospital(monkeypatch, root)

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "source.jpg").write_bytes(_jpeg_bytes())
    scan = scan_input_folder(unrelated)

    assert not hospital_ingest_enabled(unrelated)
    record = next(iter(scan.records.values()))
    assert record["source_origin"] == "WORKSPACE"
    assert record["retinal_modality"] == "UNKNOWN"
    assert record["retinal_modality_method"] == "NONE"


def test_hospital_admission_is_neutral_source_bound_and_preserves_bytes(tmp_path, monkeypatch):
    root = tmp_path / "hospital"
    _configure_hospital(monkeypatch, root)
    original_name = "patient-label-sensitive.jpg"
    source = _jpeg_bytes()
    path = root / original_name
    path.write_bytes(source)

    scan = scan_input_folder(
        root, source_origin=HOSPITAL_ORIGIN, retinal_modality="UWF",
        retinal_modality_method="AUTHORIZED_SOURCE",
    )
    record = next(iter(scan.records.values()))
    image = next(iter(scan.images.values()))
    serialized = json.dumps(record)

    assert hospital_ingest_enabled(root)
    assert record["source_origin"] == HOSPITAL_ORIGIN
    assert record["retinal_modality"] == "UWF"
    assert record["retinal_modality_method"] == "AUTHORIZED_SOURCE"
    assert record["filename"] == "hospital-case-0001.jpg"
    assert record["source_reference"] == "HOSPITAL_AUTHORIZED/CASE-0001"
    assert original_name not in serialized
    assert record["source_sha256"] == hashlib.sha256(source).hexdigest()
    assert image.source_type == HOSPITAL_ORIGIN
    assert image.source_origin == HOSPITAL_ORIGIN
    assert image.source == record["source_reference"]
    assert image.filename == record["filename"]
    assert path.read_bytes() == source


def test_hospital_lane_requires_explicit_modality_binding(tmp_path, monkeypatch):
    root = tmp_path / "hospital"
    root.mkdir()
    root.chmod(0o700)
    monkeypatch.setenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOT", str(root))
    monkeypatch.setenv("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.delenv("DR_SUPPORT_AUTHORIZED_HOSPITAL_MODALITY", raising=False)
    assert not hospital_ingest_enabled(root)


def test_hospital_model_boundary_requires_private_scope_and_model_token(monkeypatch):
    monkeypatch.delenv("DR_SUPPORT_HOSPITAL_SCOPE", raising=False)
    monkeypatch.delenv("MODEL_HOSPITAL_SCOPE", raising=False)
    monkeypatch.delenv("MODEL_ALLOW_AUTHORIZED_HOSPITAL", raising=False)
    monkeypatch.delenv("REMOTE_MODEL_TOKEN", raising=False)
    assert not source_allowed_for_model(HOSPITAL_ORIGIN)
    assert not source_allowed_for_model(HOSPITAL_ORIGIN, model_api=True)

    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_SCOPE", "PRIVATE_PROJECT_EVALUATION")
    monkeypatch.setenv("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL", "1")
    assert source_allowed_for_model(HOSPITAL_ORIGIN)
    assert not source_allowed_for_model(HOSPITAL_ORIGIN, model_api=True)

    monkeypatch.setenv("MODEL_HOSPITAL_SCOPE", "PRIVATE_PROJECT_EVALUATION")
    monkeypatch.setenv("MODEL_ALLOW_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.setenv("REMOTE_MODEL_TOKEN", "test-only-token")
    assert source_allowed_for_model(HOSPITAL_ORIGIN, model_api=True)


def test_model_api_rejects_hospital_origin_without_model_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PROFILE", "model_api")
    monkeypatch.setenv("MODEL_RUNTIME", "local")
    monkeypatch.setenv("MODEL_API_PROVIDER_SET", "uspec")
    monkeypatch.delenv("MODEL_REQUIRE_VERIFIED_ASSETS", raising=False)
    monkeypatch.delenv("MODEL_HOSPITAL_SCOPE", raising=False)
    monkeypatch.delenv("MODEL_ALLOW_AUTHORIZED_HOSPITAL", raising=False)
    monkeypatch.delenv("REMOTE_MODEL_TOKEN", raising=False)
    app = create_model_api_app(device_strict=False)
    client = TestClient(app)
    source = _jpeg_bytes()
    digest = hashlib.sha256(source).hexdigest()
    body = {
        "image_id": "HOSPITAL_CASE_0001",
        "modality": "UWF",
        "model_id": "uspec-uwf-grading",
        "image_b64": __import__("base64").b64encode(source).decode("ascii"),
        "image_sha256": digest,
        "source_type": HOSPITAL_ORIGIN,
        "width": 192,
        "height": 128,
    }
    response = client.post("/v1/predict/dr", json=body)
    assert response.status_code == 409
    assert "source origin is blocked" in response.json()["detail"]
    descriptors = client.get("/v1/models").json()
    assert all("HOSPITAL_AUTHORIZED" not in item["authorized_source_origins"] for item in descriptors)

    monkeypatch.setenv("MODEL_HOSPITAL_SCOPE", "PRIVATE_PROJECT_EVALUATION")
    monkeypatch.setenv("MODEL_ALLOW_AUTHORIZED_HOSPITAL", "1")
    monkeypatch.setenv("REMOTE_MODEL_TOKEN", "test-only-token")
    authorized_app = create_model_api_app(device_strict=False)
    authorized_descriptors = TestClient(authorized_app).get("/v1/models").json()
    assert all("HOSPITAL_AUTHORIZED" in item["authorized_source_origins"] for item in authorized_descriptors)


def test_hospital_manifest_and_all_exports_remain_blocked(tmp_path, monkeypatch):
    root = tmp_path / "hospital"
    _configure_hospital(monkeypatch, root)
    (root / "private-source.jpg").write_bytes(_jpeg_bytes())
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_CATALOG", str(tmp_path / "catalog.sqlite"))
    app = create_app(tmp_path / "state.sqlite", include_samples=False, include_demo_fixtures=False)
    client = TestClient(app)
    response = client.post("/v1/workspaces", json={
        "name": "Private hospital engineering lane",
        "input_folder": str(root),
        "output_folder": str(output),
        "database_path": str(tmp_path / "workspace.sqlite"),
    })
    assert response.status_code == 200, response.text
    case = client.get("/v1/cases").json()[0]
    assert case["source_origin"] == HOSPITAL_ORIGIN
    assert case["filename"] == "hospital-case-0001.jpg"

    manifest = client.get("/v1/dataset/manifest").json()
    row = manifest["images"][0]
    assert row["source_origin"] == HOSPITAL_ORIGIN
    assert row["export_authorization"] == "BLOCKED_HOSPITAL_EXPORT_NOT_AUTHORIZED"
    assert manifest["can_export"] is False
    assert client.post("/v1/dataset/export").status_code == 409
    assert client.post("/v1/dataset/export/grouped-by-grade", json={}).status_code == 409
    assert not any(path.is_file() for path in output.iterdir())


def test_authorized_hospital_api_pairs_previous_same_eye_and_sequence(tmp_path, monkeypatch):
    root = tmp_path / "hospital"
    _configure_hospital(monkeypatch, root)
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_SCOPE", "PRIVATE_PROJECT_EVALUATION")
    monkeypatch.setenv("DR_SUPPORT_HOSPITAL_LINKAGE_KEY", "test-private-linkage-key-0123456789012345")
    for index, name in enumerate((
        "P01_L1.jpg", "P01_L2.jpg", "P01_R1.jpg", "P01_R2.jpg", "P02_R2.jpg",
    )):
        (root / name).write_bytes(_jpeg_bytes((30 + index * 30, 90, 60)))

    app = create_app(
        tmp_path / "state.sqlite", include_samples=False, include_demo_fixtures=False,
    )
    client = TestClient(app)
    output = tmp_path / "output"
    response = client.post("/v1/workspaces", json={
        "name": "Authorized hospital comparison test",
        "input_folder": str(root),
        "output_folder": str(output),
        "database_path": str(tmp_path / "workspace.sqlite"),
    })
    assert response.status_code == 200, response.text

    cases = client.get("/v1/cases").json()
    assert len(cases) == 5
    assert all(item["source_origin"] == HOSPITAL_ORIGIN for item in cases)
    assert all("P01" not in json.dumps(item) for item in cases)

    left_current = next(
        item for item in cases
        if item["laterality"] == "LEFT" and item["visit_context"]["capture_sequence"] == 2
    )
    left_response = client.get(
        f"/v1/cases/{left_current['image_id']}/comparison"
    )
    assert left_response.status_code == 200
    left_comparison = left_response.json()
    assert left_comparison["eligible"] is True
    assert left_comparison["comparison_state"] == "AUTO_PREVIOUS"
    assert [visit["label"] for visit in left_comparison["visits"]] == [
        "PREVIOUS EXAM", "CURRENT EXAM",
    ]
    assert [visit["visit_context"]["capture_sequence"] for visit in left_comparison["visits"]] == [1, 2]
    assert all(visit["laterality"] == "LEFT" for visit in left_comparison["visits"])
    assert all(visit["modality"] == "UWF" for visit in left_comparison["visits"])

    right_current = next(
        item for item in cases
        if item["laterality"] == "RIGHT" and item["visit_context"]["capture_sequence"] == 2
        and item["patient_key"] == left_current["patient_key"]
    )
    right_comparison = client.get(
        f"/v1/cases/{right_current['image_id']}/comparison"
    ).json()
    assert right_comparison["eligible"] is True
    assert all(visit["laterality"] == "RIGHT" for visit in right_comparison["visits"])

    unmatched = next(
        item for item in cases
        if item["patient_key"] != left_current["patient_key"]
        and item["visit_context"]["capture_sequence"] == 2
    )
    assert client.get(
        f"/v1/cases/{unmatched['image_id']}/comparison"
    ).json() == {"eligible": False, "reason": "NO_VERIFIED_PREVIOUS_EXAM"}

    cross_eye = client.get(
        f"/v1/cases/{left_current['image_id']}/comparison?other_image_id={right_current['image_id']}"
    ).json()
    assert cross_eye == {"eligible": False, "reason": "EYE_MISMATCH"}
