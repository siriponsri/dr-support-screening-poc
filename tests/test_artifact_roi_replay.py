"""Actual app routes and generated cache only; no inference/OpenCV/live database."""
import base64
from copy import deepcopy
import hashlib
import io
import json

from PIL import Image
import pytest

import test_artifact_roi_assist as existing
from dr_support.api import create_app
from dr_support.services import artifact_roi_assist as assist
from dr_support.services.artifact_roi_replay import CONFIG, CachedArtifactReplayProvider, p4_cache_manifest

fixture = existing.fixture


def cached(fixture):
    _, case, image, _ = fixture
    mask = Image.new("L", image.size, 0)
    mask.paste(255, (0, 0, 10, image.size[1]))
    stream = io.BytesIO()
    mask.save(stream, "PNG")
    png = stream.getvalue()
    response_bytes = json.dumps({"result": case["lesion"]}).encode()
    response_sha = hashlib.sha256(response_bytes).hexdigest()
    profile = {"id": "generic-cached-policy", "mode": "OFFLINE_POSTFILTER_NOT_RERUN",
               "recommendation_scope": "EXACT_SOURCE_BOUND_DEMO_REPLAY_ONLY", "live_enabled": False,
               "raw_to_confirmed_negative": False, "margin_counted_once": True, "containment_fraction": 1.0,
               "seed_rule": "reviewed cached consensus", "margin_normalized_long_side": .00625,
               "sources": [{"source_sha256": image.sha256, "result_sha256": response_sha,
                            "would_hide_raw_indexes": [0],
                            "guarded_core_pixel_sha256": hashlib.sha256(bytes(value != 0 for value in mask.tobytes())).hexdigest()}]}
    results = {"profile": profile["id"], "records": [{"source_sha256": image.sha256,
        "saved_response_sha256": response_sha, "raw_count": len(case["lesion"]["lesions"]),
        "assessment": {"records": [{"raw_index": index, "raw_detection": deepcopy(row), "would_hide": index == 0}
                                   for index, row in enumerate(case["lesion"]["lesions"])]}}]}
    return profile, results, {image.sha256: png}, {image.sha256: response_bytes}


def test_cached_replay_actual_prepare_overlay_and_export_are_shadow_not_active_suppression(fixture):
    app, case, image, _ = fixture
    manifest = p4_cache_manifest(*cached(fixture))
    app.state.artifact_roi_provider = CachedArtifactReplayProvider(manifest)
    existing.client(fixture).get("/v1/cases/" + image.image_id)  # Existing resolver hydration precedes prepare.
    before = deepcopy(app.state.store.get(image.image_id))
    response = existing.client(fixture).post(existing.BASE + "/prepare", json={"revision": 0})
    assert response.status_code == 200
    view = response.json()["artifact_roi_assist"]
    assert view["status"] == "SHADOW_ONLY"
    assert len(view["shadow_proposals"]) == 1
    assert view["suppressed_ids"] == [] and len(view["visible_ids"]) == 2
    assert view["proposal_metadata"]["mode"] == "OFFLINE_POSTFILTER_NOT_RERUN"
    assert view["proposal_metadata"]["policy"]["margin_counted_once"] is True
    assert existing.client(fixture).get(view["overlay_url"]).status_code == 200
    stored = app.state.store.get(image.image_id)
    for key, value in before.items():
        if key != "revision":
            assert stored[key] == value
    sidecar = assist.export_rows([stored], images=app.state.images, admissions=app.state.admissions,
                                 provider=app.state.artifact_roi_provider,
                                 scope=assist.scope_for_app(app, app.state.store))[0]
    assert sidecar["state"]["suppressed_ids"] == []
    assert sidecar["negative_labels_from_suppression"] is False


@pytest.mark.parametrize("change", ["source", "result", "dimensions", "png", "index", "duplicate_source", "model"])
def test_cache_mismatch_retains_all(fixture, change):
    _, case, image, _ = fixture
    manifest = p4_cache_manifest(*cached(fixture))
    row = manifest["records"][0]
    if change == "source":
        row["source_sha256"] = "b" * 64
    elif change == "result":
        row["raw_detections_sha256"] = "b" * 64
    elif change == "dimensions":
        row["size"][0] += 1
    elif change == "png":
        row["mask_png_base64"] = base64.b64encode(b"changed").decode()
    elif change == "index":
        row["proposed_raw_indexes"] = [10000]
    elif change == "duplicate_source":
        manifest["records"].append(deepcopy(row))
    else:
        case["lesion"]["model_version"] = "changed-with-identical-boxes"
    state = assist.prepare(case, image, CachedArtifactReplayProvider(manifest))
    assert state["status"] == "CACHED_REPLAY_UNAVAILABLE_RETAINED_ALL"
    assert state["suppressed_ids"] == [] and len(state["visible_ids"]) == 2


@pytest.mark.parametrize("change", ["live", "double_margin", "selection", "mask", "result", "raw_order"])
def test_converter_rejects_inconsistent_reviewed_cache(fixture, change):
    profile, results, pngs, responses = cached(fixture)
    if change == "live":
        profile["live_enabled"] = True
    elif change == "double_margin":
        profile["margin_counted_once"] = False
    elif change == "selection":
        profile["sources"][0]["would_hide_raw_indexes"] = []
    elif change == "mask":
        profile["sources"][0]["guarded_core_pixel_sha256"] = "b" * 64
    elif change == "result":
        results["records"][0]["saved_response_sha256"] = "b" * 64
    else:
        results["records"][0]["assessment"]["records"].reverse()
    with pytest.raises(ValueError):
        p4_cache_manifest(profile, results, pngs, responses)


def test_protected_physician_roi_removed_from_current_shadow_proposals(fixture):
    app, case, image, _ = fixture
    provider = CachedArtifactReplayProvider(p4_cache_manifest(*cached(fixture)))
    case["artifact_roi_assist"] = assist.prepare(case, image, provider)
    key = case["artifact_roi_assist"]["shadow_proposals"][0]["detection_id"]
    case["ai_annotation_reviews"] = [{"detection_id": key, "action": "CONFIRM"}]
    current = assist.project(case, image, provider)
    assert current["shadow_proposals"] == [] and len(current["visible_ids"]) == 2
    assert len(case["artifact_roi_assist"]["shadow_proposals"]) == 1


def test_optin_config_registers_cache_without_running_proposer(fixture, tmp_path, monkeypatch):
    manifest = p4_cache_manifest(*cached(fixture))
    path = tmp_path / "cached-replay.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv(CONFIG, str(path))
    app = create_app(tmp_path / "isolated.sqlite", include_samples=False)
    assert type(app.state.artifact_roi_provider) is CachedArtifactReplayProvider
    assert app.state.artifact_roi_provider.manifest == manifest
    monkeypatch.setenv(CONFIG, str(tmp_path / "missing.json"))
    app2 = create_app(tmp_path / "isolated2.sqlite", include_samples=False)
    assert app2.state.artifact_roi_provider.manifest.get("invalid") is True
    monkeypatch.setenv(assist.FLAG, "0")
    app3 = create_app(tmp_path / "isolated3.sqlite", include_samples=False)
    assert not getattr(app3.state, "artifact_roi_provider", None)
