"""Real CPU adapter/field regressions on synthetic pixels, not model or clinical proof."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import io

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest

from dr_support.api import create_app
from dr_support.images import BridgeImage
from dr_support.services import artifact_roi_assist as assist
from dr_support.services.admission import legacy_admission
from dr_support.services.artifact_roi_generic_adapter import GenericUwfArtifactProvider
from dr_support.services.artifact_roi_replay import CONFIG as REPLAY_CONFIG


def synthetic_pixels(*, reflective=True):
    """A rectangular colored canvas with an artificial bright connected strip.

    These pixels have no retinal/lesion identity. The strip deliberately exercises
    the existing color/connectivity/margin rule without tuning its thresholds.
    """
    rgb = np.full((160, 200, 3), (100, 50, 30), dtype=np.uint8)
    if reflective:
        rgb[:14, 25:175] = (180, 230, 10)
    return rgb


def bridge_image(rgb):
    output = io.BytesIO()
    Image.fromarray(rgb).save(output, "PNG")
    return BridgeImage(
        "SYNTH_001", output.getvalue(), "SYNTHETIC", "Generated CPU post-filter regression",
        modality="UWF", filename="SYNTH_001.png", media_type="image/png",
        source_origin="SYNTHETIC",
    )


def case_with_synthetic_roi_packet(image):
    # Explicit test-supplied ROI coordinates; no model prediction is fabricated
    # as inference evidence and no human/clinical label is created here.
    rectangles = ([50, 5, 60, 10], [50, 13, 60, 20], [80, 80, 90, 90], [50, 0, 60, 3])
    return {
        "image_id": image.image_id,
        "source_sha256": image.sha256,
        "image_sha256": image.sha256,
        "admission": legacy_admission(image),
        "lesion": {
            "model_id": "prism-dr-5fold", "model_version": "synthetic-packet-not-inference",
            "modality": "UWF", "state": "AI_SUGGESTION", "width": 200, "height": 160,
            "lesions": [
                {"source_label": "MA", "canonical_label": "MICROANEURYSM",
                 "rectangle": list(rectangle), "score": 0.5}
                for rectangle in rectangles
            ],
            "warnings": ["Synthetic coordinates for CPU adapter regression only"],
            "provenance": {
                "image_sha256": image.sha256, "source_type": "SYNTHETIC",
                "preprocessing": "synthetic-test-packet", "source_revision": "not-inference",
                "checkpoint_sha256": {},
            },
        },
    }


def test_real_adapter_hides_only_contained_candidate_and_preserves_source_and_raw_packet():
    rgb = synthetic_pixels()
    original_rgb = rgb.copy()
    image = bridge_image(rgb)
    case = case_with_synthetic_roi_packet(image)
    original_case = deepcopy(case)
    original_bytes = image.data
    rows = assist.suggestions(case)
    original_rows = deepcopy(rows)
    provider = GenericUwfArtifactProvider()

    packet = provider.derive_bound(case, image, rows)

    assert packet["status"] == "READY"
    assert packet["input_binding"] == assist.input_binding(case, image)
    assert packet["suppressed"] == [
        {"detection_id": rows[0]["detection_id"], "reason": "EMPIRICAL_CORE_CONTAINMENT_CANDIDATE"}
    ]
    assert hashlib.sha256(packet["exclude_mask_png"]).hexdigest() == packet["mask_png_sha256"]
    with Image.open(io.BytesIO(packet["exclude_mask_png"])) as mask:
        assert mask.mode == "L" and mask.size == image.size
        assert mask.getpixel((55, 7)) == 255
        assert mask.getpixel((85, 85)) == 0
    assert packet["proposal_metadata"]["model_input"] == "ORIGINAL_UNCHANGED"
    assert packet["proposal_metadata"]["clinical_validation"] == "NOT_EVALUATED"
    assert packet["proposal_metadata"]["empirical_not_proven_padding"] is True
    assert case == original_case and rows == original_rows
    assert image.data is original_bytes and image.sha256 == hashlib.sha256(original_bytes).hexdigest()
    np.testing.assert_array_equal(rgb, original_rgb)
    with Image.open(io.BytesIO(image.data)) as original:
        np.testing.assert_array_equal(np.asarray(original), original_rgb)


@pytest.mark.parametrize("change", ["model", "modality", "source", "dimensions", "invalid_box"])
def test_real_adapter_rejects_mismatched_result_without_mutating_it(change):
    image = bridge_image(synthetic_pixels())
    case = case_with_synthetic_roi_packet(image)
    rows = assist.suggestions(case)
    if change == "model":
        case["lesion"]["model_id"] = "unrecognized-test-provider"
    elif change == "modality":
        case["lesion"]["modality"] = "CFP"
    elif change == "source":
        case["lesion"]["provenance"]["image_sha256"] = "a" * 64
    elif change == "dimensions":
        case["lesion"]["width"] += 1
    else:
        case["lesion"]["lesions"][0]["rectangle"] = [50, 5, 201, 10]
    before = deepcopy(case)
    result = GenericUwfArtifactProvider().derive_bound(case, image, rows)
    assert result["status"] == "GENERIC_UWF_RETAINED_ALL"
    assert result.get("suppressed", []) == []
    assert case == before


@pytest.mark.parametrize("appearance", ["plain", "white_border", "interior_patch"])
def test_appearance_without_supported_peripheral_core_retains_every_roi(appearance):
    rgb = synthetic_pixels(reflective=False)
    if appearance == "white_border":
        rgb[:14, 25:175] = (255, 255, 255)
    elif appearance == "interior_patch":
        rgb[70:90, 70:130] = (180, 230, 10)
    image = bridge_image(rgb)
    case = case_with_synthetic_roi_packet(image)
    before = deepcopy(case)
    provider = GenericUwfArtifactProvider()
    field, _ = provider.image_field(image)
    packet = provider.derive_bound(case, image, assist.suggestions(case))
    assert field["status"] == "RETAIN_ALL" and field["core_fraction"] == 0
    assert packet["status"] == "GENERIC_UWF_RETAINED_ALL"
    assert packet.get("suppressed", []) == []
    assert case == before


@pytest.mark.parametrize("change", ["corrupt", "dimensions", "mutable_bytes"])
def test_field_fails_open_for_unusable_source(change):
    image = bridge_image(synthetic_pixels())
    if change == "corrupt":
        image = replace(image, data=b"not an image")
    elif change == "dimensions":
        image = replace(image, dimensions=(201, 160))
    else:
        image = replace(image, data=bytearray(image.data))
    field, png = GenericUwfArtifactProvider().image_field(image)
    assert field["status"] == "RETAIN_ALL" and field["core_fraction"] == 0
    assert field["model_input"] == "ORIGINAL_UNCHANGED"
    assert field["raw_detections_preserved"] is True
    assert field["negative_or_gold_label"] is False
    assert png is None


@pytest.fixture
def real_field_app(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_PROFILE", "review")
    monkeypatch.setenv("MODEL_RUNTIME", "remote")
    monkeypatch.setenv("REMOTE_MODEL_URL", "")
    monkeypatch.setenv(assist.FLAG, "1")
    monkeypatch.delenv("DR_SUPPORT_DEPLOYMENT_PROFILE", raising=False)
    monkeypatch.delenv(REPLAY_CONFIG, raising=False)
    app = create_app(tmp_path / "synthetic-generic-adapter.sqlite", include_samples=False)
    image = bridge_image(synthetic_pixels())
    app.state.images[image.image_id] = image
    app.state.admissions[image.image_id] = legacy_admission(image)
    # Field generation must work before any lesion model exists or has run.
    app.state.providers = {}
    assert type(app.state.artifact_roi_provider) is GenericUwfArtifactProvider
    return app, image


def test_field_endpoint_is_read_only_source_bound_and_needs_no_prediction_or_review(real_field_app):
    app, image = real_field_app
    client = TestClient(app)
    before = deepcopy(app.state.store.get(image.image_id))
    assert before.get("lesion") is None
    response = client.get(f"/v1/cases/{image.image_id}/artifact-roi/field")
    assert response.status_code == 200, response.text
    field = response.json()
    assert field["status"] == "READY_EMPIRICAL"
    assert field["source_sha256"] == image.sha256
    assert field["model_input"] == "ORIGINAL_UNCHANGED"
    assert field["clinical_validation"] == "NOT_EVALUATED"
    assert field["raw_detections_preserved"] is True and field["negative_or_gold_label"] is False
    assert response.headers["cache-control"] == "no-store"
    overlay = client.get(field["overlay_url"])
    assert overlay.status_code == 200
    assert overlay.headers["cache-control"] == "no-store"
    assert overlay.headers["x-source-sha256"] == image.sha256
    assert overlay.headers["x-field-sha256"] == field["field_sha256"]
    assert hashlib.sha256(overlay.content).hexdigest() == field["overlay_png_sha256"]
    with Image.open(io.BytesIO(overlay.content)) as shown:
        assert shown.size == image.size
        assert shown.getpixel((85, 85))[:3] == (100, 50, 30)
        assert shown.getpixel((55, 7))[:3] != (180, 230, 10)
    assert app.state.store.get(image.image_id) == before
    assert client.get(field["overlay_url"]).content == overlay.content
    assert image.sha256 == field["source_sha256"]


@pytest.mark.parametrize("changed", ["source", "field"])
def test_field_overlay_rejects_stale_binding_without_any_case_write(real_field_app, changed):
    app, image = real_field_app
    client = TestClient(app)
    field = client.get(f"/v1/cases/{image.image_id}/artifact-roi/field").json()
    before = deepcopy(app.state.store.get(image.image_id))
    source_hash = "a" * 64 if changed == "source" else field["source_sha256"]
    field_hash = "a" * 64 if changed == "field" else field["field_sha256"]
    response = client.get(
        f"/v1/cases/{image.image_id}/artifact-roi/field/overlay",
        params={"source_sha256": source_hash, "field_sha256": field_hash},
    )
    assert response.status_code == 409
    assert app.state.store.get(image.image_id) == before


@pytest.mark.parametrize("boundary,expected", [("source", 409), ("modality", 422), ("disabled", 404)])
def test_real_field_route_enforces_source_modality_and_opt_in(real_field_app, monkeypatch, boundary, expected):
    app, image = real_field_app
    before = deepcopy(app.state.store.get(image.image_id))
    if boundary == "source":
        app.state.admissions[image.image_id]["source_sha256"] = "a" * 64
    elif boundary == "modality":
        app.state.images[image.image_id] = replace(image, modality="CFP")
    else:
        monkeypatch.delenv(assist.FLAG)
    response = TestClient(app).get(f"/v1/cases/{image.image_id}/artifact-roi/field")
    assert response.status_code == expected, response.text
    assert app.state.store.get(image.image_id) == before


def test_real_provider_prepare_restore_preserves_raw_order_and_clinical_state(real_field_app):
    app, image = real_field_app
    case = app.state.store.get(image.image_id)
    case.update(case_with_synthetic_roi_packet(image))
    app.state.store.put(case)
    client = TestClient(app)
    # Resolve existing read-time metadata first; it is separate from post-filter changes.
    assert client.get(f"/v1/cases/{image.image_id}").status_code == 200
    before = deepcopy(app.state.store.get(image.image_id))
    scope = assist.scope_for_app(app, app.state.store)
    base = f"/v1/cases/{image.image_id}/artifact-roi"
    response = client.post(base + "/prepare", json={"revision": before["revision"], "scope_sha256": scope})
    assert response.status_code == 200, response.text
    prepared = response.json()
    view = prepared["artifact_roi_assist"]
    assert view["status"] == "READY" and len(view["suppressed_ids"]) == 1
    assert view["negative_labels_from_suppression"] is False
    assert view["proposal_metadata"]["model_input"] == "ORIGINAL_UNCHANGED"
    assert len(view["visible_ids"]) == 3
    assert client.get(view["overlay_url"]).status_code == 200
    restored = client.post(base + "/restore", json={
        "revision": prepared["revision"], "scope_sha256": scope,
        "binding_sha256": view["binding_sha256"], "detection_ids": view["suppressed_ids"],
    })
    assert restored.status_code == 200, restored.text
    restored_view = restored.json()["artifact_roi_assist"]
    assert restored_view["suppressed_ids"] == []
    assert restored_view["visible_ids"] == [row["detection_id"] for row in assist.suggestions(before)]
    stored = app.state.store.get(image.image_id)
    for key, value in before.items():
        if key != "revision":
            assert stored[key] == value, key
    assert image.sha256 == before["source_sha256"]
    assert stored["artifact_roi_assist"]["restore_history"][0]["action"] == "RESTORE_AI_VISIBILITY"
