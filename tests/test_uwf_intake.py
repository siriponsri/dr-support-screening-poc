"""Synthetic P0 image-type and same-canvas UWF safety regression tests."""

import hashlib
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from dr_support.api import create_app
from dr_support.images import BridgeImage, admitted_samples
from dr_support.imaging import DerivativeService
from dr_support.imaging.retinal_field import RetinalFieldNeedsReview
from dr_support.providers.prism import PRISM
from dr_support.providers.retfound import RETFound


def _uwf_bytes(*, bounded=True):
    image = Image.new("RGB", (512, 384), (7, 7, 7))
    draw = ImageDraw.Draw(image)
    if bounded:
        draw.ellipse((32, 24, 480, 360), fill=(170, 60, 35))
        # An enclosed pale retinal feature must not punch a hole in the mask.
        draw.ellipse((230, 140, 280, 180), fill=(240, 240, 220))
    else:
        draw.rectangle((0, 0, 511, 383), fill=(170, 60, 35))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _workspace(tmp_path, monkeypatch, source):
    monkeypatch.setenv("DR_SUPPORT_WORKSPACE_CATALOG", str(tmp_path / "catalog.sqlite"))
    folder = tmp_path / "input"
    folder.mkdir()
    out = tmp_path / "output"
    out.mkdir()
    path = folder / "synthetic-uwf.png"
    path.write_bytes(source)
    client = TestClient(create_app(tmp_path / "fallback.sqlite", include_samples=False))
    response = client.post("/v1/workspaces", json={
        "name": "Synthetic UWF", "input_folder": str(folder),
        "output_folder": str(out), "database_path": str(tmp_path / "reviews.sqlite"),
    })
    assert response.status_code == 200
    client.post("/v1/admissions/scan")
    case = next(c for c in client.get("/v1/cases").json() if c["filename"] == path.name)
    return client, case, path


def _confirm(client, case, modality):
    return client.post(f"/v1/cases/{case['image_id']}/confirm-image", json={
        "revision": case["revision"], "reviewer": "Synthetic Reviewer",
        "patient_key": "PAT001", "laterality": "LEFT", "retinal_modality": modality,
    })


def test_workspace_intake_unknown_then_manual_uwf_persists_and_blocks_cfp(tmp_path, monkeypatch):
    source = _uwf_bytes()
    client, case, path = _workspace(tmp_path, monkeypatch, source)
    assert case["modality"] == "UNKNOWN"
    assert case["admission"]["retinal_modality_state"] == "NEEDS_CONFIRMATION"
    image_id = case["image_id"]
    assert client.post("/v1/infer/global", json={"image_id": image_id, "modality": "CFP", "model_id": "retfound-aptos5"}).status_code == 409

    response = _confirm(client, case, "UWF")
    assert response.status_code == 200
    confirmed = response.json()
    assert confirmed["modality"] == confirmed["admission"]["retinal_modality"] == "UWF"
    assert confirmed["admission"]["retinal_modality_method"] == "MANUAL"
    assert confirmed["admission_history"][-1]["new"]["retinal_modality"] == "UWF"
    assert confirmed["analysis_preparation"]["status"] == "READY"
    audit = confirmed["analysis_preparation"]["derivative"]
    assert audit["source_sha256"] == hashlib.sha256(source).hexdigest()
    assert audit["analysis_sha256"] != audit["source_sha256"]
    assert audit["transform_id"] == "analysis-uwf-retinal-mask-v1"
    assert audit["transform_version"] == 1
    assert audit["retinal_field_status"] == "READY"
    assert 0.2 < audit["valid_retina_fraction"] < 0.85
    assert len(audit["valid_retina_mask_sha256"]) == 64
    assert (audit["source_dimensions"]["width"], audit["source_dimensions"]["height"]) == (512, 384)
    assert (audit["analysis_dimensions"]["width"], audit["analysis_dimensions"]["height"]) == (512, 384)
    assert audit["coordinate_mapping"]["kind"] == "IDENTITY"
    assert audit["coordinate_mapping"]["scale_x"] == audit["coordinate_mapping"]["scale_y"] == 1

    area = client.get(f"/v1/images/{image_id}/analysis-area")
    assert area.status_code == 200
    assert hashlib.sha256(area.content).hexdigest() == audit["analysis_sha256"]
    with Image.open(io.BytesIO(area.content)) as masked:
        assert masked.size == (512, 384)
        assert masked.getpixel((0, 0)) == (0, 0, 0)
        assert masked.getpixel((256, 192)) != (0, 0, 0)
    assert path.read_bytes() == source
    assert client.get(f"/v1/images/{image_id}").content == source
    assert client.post("/v1/infer/global", json={"image_id": image_id, "modality": "CFP", "model_id": "retfound-aptos5"}).status_code == 409
    assert client.post("/v1/infer/lesion-roi", json={"image_id": image_id, "modality": "UWF", "model_id": "prism-dr-5fold"}).status_code == 409

    client.post("/v1/admissions/scan")
    rescanned = client.get(f"/v1/cases/{image_id}").json()
    assert rescanned["modality"] == "UWF"
    assert rescanned["analysis_preparation"]["derivative"]["analysis_sha256"] == audit["analysis_sha256"]
    assert rescanned["image_url"] and rescanned["global"] is None
    manifest = client.get("/v1/dataset/manifest").json()
    assert next(row for row in manifest["images"] if row["image_id"] == image_id)["modality"] == "UWF"
    # Human grade review stays available with no model evidence.
    grade = client.post(f"/v1/cases/{image_id}/review", json={
        "revision": rescanned["revision"], "reviewer": "Synthetic Reviewer",
        "action": "CORRECT_GRADE", "grade": 2,
    })
    assert grade.status_code == 200
    assert grade.json()["grade_review_source"] == "MANUAL"


def test_mask_is_deterministic_and_preserves_original_dimensions():
    source = _uwf_bytes()
    image = BridgeImage(hashlib.sha256(source).hexdigest(), source, "PUBLIC", "synthetic",
                        modality="UWF", filename="synthetic.png", media_type="image/png")
    first = DerivativeService().prepare_analysis(image)
    second = DerivativeService().prepare_analysis(image)
    assert first.data == second.data
    assert first.valid_retina_mask_sha256 == second.valid_retina_mask_sha256
    assert first.lineage.derivative_sha256 == second.lineage.derivative_sha256
    assert first.coordinate_mapping.kind == "IDENTITY"
    assert first.coordinate_mapping.map_point(280, 190) == (280, 190)
    assert first.source.source_sha256 == hashlib.sha256(source).hexdigest()
    assert image.data == source


def test_ambiguous_field_needs_review_without_source_fallback(tmp_path, monkeypatch):
    source = _uwf_bytes(bounded=False)
    client, case, path = _workspace(tmp_path, monkeypatch, source)
    confirmed = _confirm(client, case, "UWF").json()
    assert confirmed["modality"] == "UWF"
    assert confirmed["analysis_preparation"]["status"] == "NEEDS_REVIEW"
    assert "derivative" not in confirmed["analysis_preparation"]
    assert client.get(f"/v1/images/{case['image_id']}/analysis-area").status_code == 409
    assert client.post("/v1/infer/global", json={
        "image_id": case["image_id"], "modality": "CFP", "model_id": "retfound-aptos5",
    }).status_code == 409
    assert path.read_bytes() == source
    with Image.open(io.BytesIO(source)) as image:
        with pytest.raises(RetinalFieldNeedsReview):
            from dr_support.imaging.retinal_field import prepare_retinal_field
            prepare_retinal_field(image)


def test_explicit_cfp_fixture_keeps_existing_inference_path(tmp_path):
    client = TestClient(create_app(tmp_path / "synthetic.sqlite", include_samples=False))
    case = client.get("/v1/cases/SYNTH_001").json()
    assert case["modality"] == case["admission"]["retinal_modality"] == "CFP"
    assert client.post("/v1/infer/global", json={
        "image_id": "SYNTH_001", "modality": "CFP", "model_id": "mock-global",
    }).status_code == 200


def test_public_manifest_explicit_cfp_remains_cfp(tmp_path):
    source = _uwf_bytes()
    manifest = tmp_path / "docs" / "reference" / "SAMPLE_SOURCE_MANIFEST.json"
    manifest.parent.mkdir(parents=True)
    sample = tmp_path / "local-state" / "bridge" / "samples" / "synthetic.png"
    sample.parent.mkdir(parents=True)
    sample.write_bytes(source)
    manifest.write_text(json.dumps([{
        "image_id": "PUBLIC_SYNTHETIC", "filename": "synthetic.png",
        "sha256": hashlib.sha256(source).hexdigest(), "source": "Synthetic fixture",
        "modality": "CFP",
    }]), encoding="utf-8")
    assert admitted_samples(tmp_path)["PUBLIC_SYNTHETIC"].modality == "CFP"


def test_corrected_source_type_supersedes_cfp_evidence_without_losing_human_review(tmp_path):
    client = TestClient(create_app(tmp_path / "synthetic.sqlite", include_samples=False))
    assert client.post("/v1/infer/global", json={
        "image_id": "SYNTH_001", "modality": "CFP", "model_id": "mock-global",
    }).status_code == 200
    before = client.get("/v1/cases/SYNTH_001").json()
    assert before["global"] is not None
    changed = _confirm(client, before, "UWF")
    assert changed.status_code == 200
    case = changed.json()
    assert case["modality"] == "UWF"
    assert case["global"] is None
    assert case["lesion_review"] is None
    assert case["review_evidence"]["unresolved_count"] == 0
    assert case["superseded_model_results"][0]["global"] == before["global"]
    assert client.post("/v1/cases/SYNTH_001/review", json={
        "revision": case["revision"], "action": "ACCEPT", "reviewer": "Synthetic Reviewer",
    }).status_code == 409
    manual = client.post("/v1/cases/SYNTH_001/review", json={
        "revision": case["revision"], "action": "CORRECT_GRADE", "grade": 2,
        "reviewer": "Synthetic Reviewer",
    })
    assert manual.status_code == 200
    assert manual.json()["grade_review_source"] == "MANUAL"


def test_current_providers_advertise_only_cfp():
    assert RETFound(allow_cpu_fallback=True).metadata()["modalities"] == ["CFP"]
    assert PRISM(allow_cpu_fallback=True).metadata()["modalities"] == ["CFP"]
