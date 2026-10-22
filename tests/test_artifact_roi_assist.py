"""Fake core, generated image, actual local workflow; no inference or live DB."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from dr_support.api import create_app
from dr_support.services import artifact_roi_assist as module
from dr_support.services.admission import legacy_admission


class FakeCore:
    def __init__(self, case):
        self.case, self.calls = case, 0
        self.version = "fake-sure-exclude.v1"

    def identity(self):
        return dict(method_version=self.version, mask_version="fake-mask.v1", config_sha256="a" * 64)

    def derive(self, image, rows):
        self.calls += 1
        mask = Image.new("L", image.size, 0)
        mask.paste(255, (0, 0, 10, image.size[1]))
        output = io.BytesIO()
        mask.save(output, "PNG")
        png = output.getvalue()
        return dict(status="READY", input_binding=module.input_binding(self.case, image),
                    provider_identity=self.identity(), exclude_mask_png=png,
                    mask_png_sha256=hashlib.sha256(png).hexdigest(),
                    suppressed=[dict(detection_id=rows[0]["detection_id"], reason="SURE_EXCLUDED_ARTIFACT")])


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_RUNTIME", "remote")
    monkeypatch.setenv("APP_PROFILE", "review")
    monkeypatch.setenv("REMOTE_MODEL_URL", "")
    monkeypatch.setenv(module.FLAG, "1")
    app = create_app(tmp_path / "synthetic.sqlite", include_samples=False)
    image = replace(app.state.images["SYNTH_001"], modality="UWF")
    app.state.images[image.image_id] = image
    admission = legacy_admission(image)
    app.state.admissions[image.image_id] = admission
    case = app.state.store.get(image.image_id)
    case.update(source_sha256=image.sha256, image_sha256=image.sha256, admission=admission)
    case["lesion"] = dict(model_id="prism-dr-5fold", model_version="fake-model.v1", modality="UWF",
                          state="AI_SUGGESTION", width=image.size[0], height=image.size[1],
                          lesions=[dict(source_label="MA", canonical_label="MICROANEURYSM",
                                        rectangle=[0, 0, 5, 5], score=.9),
                                   dict(source_label="HE", canonical_label="HEMORRHAGE",
                                        rectangle=[100, 100, 110, 110], score=.8)], warnings=[],
                          provenance=dict(image_sha256=image.sha256, source_type="SYNTHETIC",
                                          preprocessing="fixture", source_revision="fixture", checkpoint_sha256={}))
    case.update(reviewed_grade=3, grade_status="CONFIRMED", grade_reviews=[{"fixture": True}],
                clinician_review={"reviewer": "fixture", "final_grade": 3},
                lesion_review_state="REVIEWED", annotation_completeness={"CORE": {"state": "REVIEWED_NONE_FOUND"}},
                confirmed_annotation_hash="existing", annotation_hash="existing")
    app.state.store.put(case)
    provider = FakeCore(case)
    app.state.artifact_roi_provider = provider
    return app, case, image, provider


def client(fixture):
    app = fixture[0]
    class ScopedClient(TestClient):
        def post(self, url, **kwargs):
            if "/artifact-roi/" in url and "json" in kwargs:
                kwargs["json"] = {"scope_sha256": module.scope_for_app(app, app.state.store), **kwargs["json"]}
            return super().post(url, **kwargs)
    return ScopedClient(app)


BASE = "/v1/cases/SYNTH_001/artifact-roi"


def test_flag_default_off_and_nonreview_profile_never_suppress(fixture, monkeypatch):
    app, case, image, provider = fixture
    monkeypatch.delenv(module.FLAG)
    assert module.project(case, image, provider)["status"] == "DISABLED"
    assert client(fixture).post(BASE + "/prepare", json={"revision": 0}).status_code == 404
    monkeypatch.setenv(module.FLAG, "1")
    monkeypatch.setenv("APP_PROFILE", "model_api")
    assert not module.project(case, image, provider)["enabled"]
    assert provider.calls == 0


@pytest.mark.parametrize("restore_first", [False, True])
def test_unchanged_prepare_does_not_invalidate_drafts_or_duplicate_audit(fixture, restore_first):
    app, case, _, provider = fixture
    c = client(fixture)
    first = c.post(BASE + "/prepare", json={"revision": 0}).json()
    if restore_first:
        view = first["artifact_roi_assist"]
        first = c.post(BASE + "/restore", json={"revision": first["revision"],
                       "binding_sha256": view["binding_sha256"],
                       "detection_ids": view["suppressed_ids"]}).json()
    before = deepcopy(app.state.store.get(case["image_id"]))
    repeated = c.post(BASE + "/prepare", json={"revision": first["revision"]})
    assert repeated.status_code == 200
    assert repeated.json()["revision"] == first["revision"]
    assert app.state.store.get(case["image_id"]) == before
    # A new method is a real change and must still create a revision/audit.
    provider.version = "fake-sure-exclude.v2"
    changed = c.post(BASE + "/prepare", json={"revision": first["revision"]})
    assert changed.status_code == 200
    assert changed.json()["revision"] == first["revision"] + 1
    assert len(app.state.store.get(case["image_id"])["artifact_roi_history"]) == len(before["artifact_roi_history"]) + 1


def test_prepare_persists_distinct_sets_without_raw_or_clinical_mutation(fixture):
    app, case, _, _ = fixture
    client(fixture).get("/v1/cases/SYNTH_001")  # Existing normal resolver hydration precedes filter.
    original = deepcopy(app.state.store.get(case["image_id"]))
    response = client(fixture).post(BASE + "/prepare", json={"revision": 0})
    assert response.status_code == 200, response.text
    view = response.json()["artifact_roi_assist"]
    assert view["status"] == "READY" and len(view["suppressed_ids"]) == len(view["visible_ids"]) == 1
    assert view["negative_labels_from_suppression"] is False
    assert "mask_png_base64" not in view
    stored = app.state.store.get(case["image_id"])
    for key, value in original.items():
        if key != "revision":
            assert stored[key] == value, key
    assert stored["revision"] == 1
    assert json.dumps(stored["lesion"], sort_keys=True) == json.dumps(original["lesion"], sort_keys=True)
    assert len(stored["artifact_roi_history"]) == 1
    assert stored["artifact_roi_masks"][view["mask_png_sha256"]] == stored["artifact_roi_assist"]["mask_png_base64"]
    # New read from durable SQLite store, not only response-local state.
    assert client(fixture).get("/v1/cases/SYNTH_001").json()["artifact_roi_assist"]["suppressed_ids"] == view["suppressed_ids"]


def test_restore_no_popup_or_review_decision_and_repeat_prepare_preserves(fixture):
    app, case, _, _ = fixture
    c = client(fixture)
    view = c.post(BASE + "/prepare", json={"revision": 0}).json()["artifact_roi_assist"]
    saved = c.post(BASE + "/restore", json=dict(revision=1, binding_sha256=view["binding_sha256"],
                                              detection_ids=view["suppressed_ids"]))
    assert saved.status_code == 200, saved.text
    assert saved.json()["artifact_roi_assist"]["suppressed_ids"] == []
    assert len(saved.json()["artifact_roi_assist"]["visible_ids"]) == 2
    repeated = c.post(BASE + "/prepare", json={"revision": 2}).json()["artifact_roi_assist"]
    assert repeated["suppressed_ids"] == []
    stored = app.state.store.get(case["image_id"])
    assert stored["ai_annotation_reviews"] == [] and stored["human_annotations"] == []
    assert stored["confirmed_annotation_hash"] == case["confirmed_annotation_hash"]
    assert len(stored["artifact_roi_assist"]["restore_history"]) == 1
    assert any(entry.get("action") == "RESTORE_AI_VISIBILITY" for entry in stored["artifact_roi_history"])
    assert len(stored["artifact_roi_masks"]) == 1  # Same mask is archived once, never rewritten by restore.


@pytest.mark.parametrize("change", ["source", "model", "mask", "method", "hash_conflict"])
def test_stale_binding_retains_all_and_overlay_restore_reject(fixture, change):
    app, case, image, provider = fixture
    c = client(fixture)
    view = c.post(BASE + "/prepare", json={"revision": 0}).json()["artifact_roi_assist"]
    stored = app.state.store.get(case["image_id"])
    if change == "source":
        image = replace(image, data=image.data + b"different")
        app.state.images[case["image_id"]] = image
    elif change == "model":
        stored["lesion"]["model_version"] = "different"
    elif change == "mask":
        stored["artifact_roi_assist"]["mask_png_base64"] = "Y2hhbmdlZA=="
    elif change == "method":
        provider.version = "new-method"
    else:
        stored["source_sha256"] = "f" * 64
    app.state.store.put(stored)
    actual = module.project(stored, image, provider, scope=module.scope_for_app(app, app.state.store))
    assert actual["suppressed_ids"] == [] and len(actual["visible_ids"]) == 2
    assert c.get(BASE + "/overlay", params={"binding_sha256": view["binding_sha256"]}).status_code == 409
    assert c.post(BASE + "/restore", json=dict(revision=1, binding_sha256=view["binding_sha256"],
                                             detection_ids=view["suppressed_ids"])).status_code == 409


def test_existing_human_review_or_derived_annotation_never_hidden(fixture):
    _, case, image, provider = fixture
    key = module.suggestions(case)[0]["detection_id"]
    case["human_annotations"] = [{"source_detection_id": key}]
    state = module.prepare(case, image, provider)
    assert state["suppressed_ids"] == []
    case["human_annotations"] = []
    case["ai_annotation_reviews"] = [{"detection_id": key, "action": "ACCEPT"}]
    assert module.prepare(case, image, provider)["suppressed_ids"] == []


@pytest.mark.parametrize("kind", ["missing", "failed", "unknown", "transform", "source_conflict"])
def test_unavailable_or_failed_core_and_transform_retains_all(fixture, kind):
    _, case, image, provider = fixture
    if kind == "missing":
        provider = None
    elif kind == "failed":
        provider.derive = lambda *args: (_ for _ in ()).throw(RuntimeError("fixture failure"))
    elif kind == "unknown":
        provider.derive = lambda *args: {"status": "UNCERTAIN"}
    elif kind == "transform":
        case["lesion"]["width"] -= 1
    else:
        case["source_sha256"] = "e" * 64
    state = module.prepare(case, image, provider)
    assert state["suppressed_ids"] == [] and len(state["visible_ids"]) == 2
    assert state["status"] != "READY"


def test_stale_revision_or_binding_does_not_write(fixture):
    app, case, _, _ = fixture
    c = client(fixture)
    assert c.post(BASE + "/prepare", json={"revision": 99}).status_code == 409
    assert app.state.store.get(case["image_id"]) == case
    view = c.post(BASE + "/prepare", json={"revision": 0}).json()["artifact_roi_assist"]
    before = app.state.store.get(case["image_id"])
    assert c.post(BASE + "/restore", json=dict(revision=0, binding_sha256=view["binding_sha256"],
                                             detection_ids=view["suppressed_ids"])).status_code == 409
    assert app.state.store.get(case["image_id"]) == before


def test_overlay_optional_original_coordinates_and_safe_headers(fixture):
    c = client(fixture)
    view = c.post(BASE + "/prepare", json={"revision": 0}).json()["artifact_roi_assist"]
    response = c.get(view["overlay_url"])
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    overlay = Image.open(io.BytesIO(response.content))
    assert overlay.size == fixture[2].size and overlay.mode == "RGBA"
    assert overlay.getpixel((0, 0))[3] == 100 and overlay.getpixel((100, 100))[3] == 0


def test_export_is_non_gold_separate_from_human_labels(fixture):
    app, case, _, _ = fixture
    client(fixture).post(BASE + "/prepare", json={"revision": 0})
    stored = app.state.store.get(case["image_id"])
    rows = module.export_rows([stored], images=app.state.images, admissions=app.state.admissions,
                              provider=app.state.artifact_roi_provider, scope=module.scope_for_app(app, app.state.store))
    assert len(rows) == 1
    assert rows[0]["provenance_class"] == "NON_GOLD_AI_VISIBILITY_ONLY"
    assert not rows[0]["negative_labels_from_suppression"]
    assert "mask_png_base64" not in json.dumps(rows)
    assert stored["human_annotations"] == [] and stored["annotation_completeness"] == case["annotation_completeness"]
    assert module.export_rows([case]) == []


def test_real_core_empty_registry_has_no_rim_effect(fixture):
    from dr_support.services.artifact_roi_core_adapter import TechnicalFrameArtifactProvider
    _, case, image, _ = fixture
    provider = TechnicalFrameArtifactProvider()
    state = module.prepare(case, image, provider)
    assert state["status"] == "TECHNICAL_FRAME_UNAVAILABLE_RETAINED_ALL"
    assert state["suppressed_ids"] == [] and len(state["visible_ids"]) == 2


def test_unchanged_core_adapter_filters_only_proven_generated_padding(fixture):
    import numpy as np
    from dr_support.services import artifact_core_v01 as core
    from dr_support.services.artifact_roi_core_adapter import TechnicalFrameArtifactProvider
    _, case, image, _ = fixture
    rgb = np.full((480, 640, 3), [120, 70, 40], dtype=np.uint8)
    rgb[:, :80] = 0
    output = io.BytesIO()
    Image.fromarray(rgb).save(output, "PNG")
    image = replace(image, data=output.getvalue())
    case.update(source_sha256=image.sha256, image_sha256=image.sha256, admission=legacy_admission(image))
    case["lesion"]["provenance"]["image_sha256"] = image.sha256
    case["lesion"]["lesions"][0]["rectangle"] = [20, 100, 25, 105]
    profile = dict(kind="proven_uniform_canvas_padding", provenance="generated fixture exporter.v1",
                   padding_t_r_b_l=[0, 0, 0, 80], rgb=[0, 0, 0])
    def evidence(image, decoded):
        return dict(profile_id="fixture", profile_sha256=core.profile_sha256(profile),
                    source_sha256=image.sha256, source_rgb_sha256=core.rgb_sha256(decoded),
                    source_size=list(image.size))
    provider = TechnicalFrameArtifactProvider(trusted_profiles={"fixture": profile}, evidence_for=evidence)
    original = deepcopy(case["lesion"])
    state = module.prepare(case, image, provider)
    assert state["status"] == "READY" and len(state["suppressed_ids"]) == 1
    assert state["evidence_kind"] == "PROVEN_TECHNICAL_PADDING_ONLY"
    assert state["provider_identity"]["method_version"] == core.VERSION
    assert case["lesion"] == original


def test_shadow_proposals_keep_all_and_optional_overlay_no_restore_needed(fixture):
    app, case, _, provider = fixture
    original = provider.derive
    def shadow(*args):
        packet = original(*args)
        return {**packet, "status": "SHADOW_ONLY", "suppressed": [
            {**row, "reason": "EMPIRICAL_ARTIFACT_PROPOSAL"} for row in packet["suppressed"]]}
    provider.derive = shadow
    c = client(fixture)
    response = c.post(BASE + "/prepare", json={"revision": 0}).json()
    view = response["artifact_roi_assist"]
    assert view["status"] == "SHADOW_ONLY" and view["suppressed_ids"] == []
    assert "PROPOSAL_ONLY" in view["mask_semantics"] and "SURE" not in view["mask_semantics"]
    assert len(view["visible_ids"]) == 2 and len(view["shadow_proposals"]) == 1
    assert c.get(view["overlay_url"]).status_code == 200
    assert c.post(BASE + "/restore", json=dict(revision=1, binding_sha256=view["binding_sha256"], detection_ids=[])).status_code == 409
    assert app.state.store.get(case["image_id"])["ai_annotation_reviews"] == []


def test_export_stale_raw_result_does_not_claim_active_suppression(fixture):
    app, case, _, _ = fixture
    client(fixture).post(BASE + "/prepare", json={"revision": 0})
    stored = app.state.store.get(case["image_id"])
    stored["lesion"]["model_version"] = "new"
    row = module.export_rows([stored], images=app.state.images, admissions=app.state.admissions,
                             provider=app.state.artifact_roi_provider, scope=module.scope_for_app(app, app.state.store))[0]
    assert row["state"]["status"] == "STALE_RETAIN_ALL"
    assert row["state"]["suppressed_ids"] == row["state"]["suppressed"] == []


def export_workspace(fixture, tmp_path):
    app, case, _, _ = fixture
    input_dir, output = tmp_path / "input", tmp_path / "output"
    input_dir.mkdir()
    output.mkdir()
    c = client(fixture)
    response = c.post("/v1/workspaces", json=dict(name="Synthetic artifact export",
        input_folder=str(input_dir), output_folder=str(output), database_path=str(tmp_path / "workspace.sqlite")))
    assert response.status_code == 200, response.text
    app.state.store.put(case)
    app.state.workspace_image_ids.add(case["image_id"])
    app.state.workspace_admission_ids.add(case["image_id"])
    return c, output


def test_actual_snapshot_keeps_suppression_sidecar_out_of_gold_csv(fixture, tmp_path):
    import csv
    c, output = export_workspace(fixture, tmp_path)
    prepared = c.post(BASE + "/prepare", json={"revision": 0})
    assert prepared.status_code == 200
    exported = c.post("/v2/dataset/snapshot")
    assert exported.status_code == 200, exported.text
    directory = output / exported.json()["directory_name"]
    sidecar = json.loads((directory / "artifact_roi_assist.json").read_bytes())
    assert sidecar["provenance_class"] == "NON_GOLD_AI_VISIBILITY_ONLY"
    assert len(sidecar["cases"][0]["state"]["suppressed_ids"]) == 1
    gold = (directory / "lesion_labels.csv").read_text(encoding="utf-8")
    for key in prepared.json()["artifact_roi_assist"]["suppressed_ids"]:
        assert key not in gold
    evidence = list(csv.DictReader(io.StringIO((directory / "ai_evidence.csv").read_text(encoding="utf-8"))))
    assert len(evidence) == 2  # Filtering did not delete raw AI evidence from export.
    assert all(row["provenance_status"] == "NON_GOLD_AI_EVIDENCE" for row in evidence)


def test_hospital_export_remains_409_no_files_even_with_filter_state(fixture, tmp_path):
    c, output = export_workspace(fixture, tmp_path)
    c.post(BASE + "/prepare", json={"revision": 0})
    app, case, _, _ = fixture
    stored = app.state.store.get(case["image_id"])
    stored["admission"]["source_origin"] = "HOSPITAL_AUTHORIZED"
    app.state.store.put(stored)
    assert c.post("/v2/dataset/snapshot").status_code == 409
    assert list(output.iterdir()) == []


def test_cross_workspace_same_source_revision_rejects_old_scope_without_writes(fixture):
    app, case, _, _ = fixture
    c = client(fixture)
    old_scope = module.scope_for_app(app, app.state.store)
    view = c.post(BASE + "/prepare", json={"revision": 0}).json()["artifact_roi_assist"]
    before = app.state.store.get(case["image_id"])
    app.state.workspace_id = "different-workspace-same-source"
    assert c.post(BASE + "/prepare", json={"revision": 1, "scope_sha256": old_scope}).status_code == 409
    assert c.post(BASE + "/restore", json=dict(revision=1, scope_sha256=old_scope,
        binding_sha256=view["binding_sha256"], detection_ids=view["suppressed_ids"])).status_code == 409
    assert app.state.store.get(case["image_id"]) == before


def test_missing_scope_is_not_silently_filled_by_api(fixture):
    app, case, _, _ = fixture
    assert TestClient(app).post(BASE + "/prepare", json={"revision": 0}).status_code == 422
    assert app.state.store.get(case["image_id"]) == case


def test_empirical_adapter_is_shadow_even_for_nonempty_mask(fixture):
    import numpy as np
    from dr_support.services.artifact_roi_shadow_adapter import EmpiricalRimShadowProvider
    app, case, image, _ = fixture
    def proposer(rgb, source_sha):
        mask = np.zeros(rgb.shape[:2], dtype=bool)
        mask[:, :10] = True
        return dict(status="SHADOW_PROPOSAL_READY", core_exclude=mask,
                    live_suppression_allowed=False,
                    metadata=dict(source_sha256=source_sha,
                                  source_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
                                  source_size=[rgb.shape[1], rgb.shape[0]],
                                  confidence="UNCALIBRATED_EMPIRICAL_HYPOTHESIS"))
    app.state.artifact_roi_provider = EmpiricalRimShadowProvider(proposer=proposer)
    response = client(fixture).post(BASE + "/prepare", json={"revision": 0})
    assert response.status_code == 200
    view = response.json()["artifact_roi_assist"]
    assert view["status"] == "SHADOW_ONLY" and view["suppressed_ids"] == []
    assert view["evidence_kind"] == "EMPIRICAL_RIM_SHADOW_NOT_CERTIFIED"
    assert view["proposal_metadata"]["roi_proposal_evaluation"] == "NOT_RUN"
    assert view["proposal_metadata"]["method"]["confidence"] == "UNCALIBRATED_EMPIRICAL_HYPOTHESIS"
    assert len(view["visible_ids"]) == 2 and client(fixture).get(view["overlay_url"]).status_code == 200
    assert app.state.store.get(case["image_id"])["lesion"] == case["lesion"]


def test_empirical_adapter_cannot_promote_live_flag(fixture):
    from dr_support.services.artifact_roi_shadow_adapter import EmpiricalRimShadowProvider
    _, case, image, _ = fixture
    provider = EmpiricalRimShadowProvider(proposer=lambda *args: dict(live_suppression_allowed=True))
    state = module.prepare(case, image, provider)
    assert state["status"] == "EMPIRICAL_SHADOW_UNAVAILABLE_RETAINED_ALL"
    assert state["suppressed_ids"] == []


def test_shadow_core_import_failure_does_not_hide_or_clear_labels(fixture):
    from dr_support.services.artifact_roi_shadow_adapter import EmpiricalRimShadowProvider
    _, case, image, _ = fixture
    original = deepcopy(case)
    def unavailable(*args):
        raise PermissionError("generated fixture dependency failure, no actual import")
    provider = EmpiricalRimShadowProvider(proposer=unavailable)
    assert module.prepare(case, image, provider)["status"] == "CORE_FAILED_RETAINED_ALL"
    assert case == original


def test_updated_core_and_shadow_are_exact_owned_lane_files():
    from pathlib import Path
    import dr_support.services.artifact_core_v01 as core
    import dr_support.services.artifact_roi_shadow_adapter as adapter
    assert core.VERSION == "prism-artifact-core/0.1.1-candidate"
    assert hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest() == "4ee91419dbabd8d4841aeddd42a0f64e369e2c68ba3cfd95c01bc88641eb9970"
    path = Path(core.__file__).with_name("artifact_rim_shadow_v01.py")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == adapter.PROPOSER_SHA256 == "c55056f8d218ee9b73a03cadab16cc39cdad363d8401bfb7b9c03fcd9ca978a6"


def test_ambiguous_duplicate_detection_ids_keep_every_raw_box(fixture):
    _, case, image, provider = fixture
    case["lesion"]["lesions"].append(deepcopy(case["lesion"]["lesions"][0]))
    original = deepcopy(case["lesion"])
    state = module.prepare(case, image, provider)
    assert state["status"] == "AMBIGUOUS_IDS_RETAINED_ALL"
    assert len(state["visible_ids"]) == 3 and state["suppressed_ids"] == []
    assert case["lesion"] == original


@pytest.mark.parametrize("kind", ["nonbinary", "rgb", "unreadable"])
def test_invalid_mask_never_hides_any_roi(fixture, kind):
    _, case, image, provider = fixture
    derive = provider.derive
    def invalid(*args):
        packet = derive(*args)
        out = io.BytesIO()
        if kind == "unreadable":
            png = b"generated invalid image fixture"
        else:
            Image.new("RGB" if kind == "rgb" else "L", image.size, 128).save(out, "PNG")
            png = out.getvalue()
        return {**packet, "exclude_mask_png": png, "mask_png_sha256": hashlib.sha256(png).hexdigest()}
    provider.derive = invalid
    state = module.prepare(case, image, provider)
    assert state["status"] != "READY" and len(state["visible_ids"]) == 2
    assert state["suppressed_ids"] == []


def test_export_uses_live_effective_view_and_separates_historical_decision(fixture):
    app, case, image, provider = fixture
    client(fixture).post(BASE + "/prepare", json={"revision": 0})
    stored = app.state.store.get(case["image_id"])
    original = deepcopy(stored)
    scope = module.scope_for_app(app, app.state.store)
    live = module.project(stored, image, provider, scope=scope, admission=stored["admission"])
    row = module.export_rows([stored], images=app.state.images, admissions=app.state.admissions,
                             provider=provider, scope=scope)[0]
    assert row["state"]["status"] == live["status"] == "READY"
    assert row["state"]["suppressed_ids"] == live["suppressed_ids"]
    assert row["historical_decision"]["binding_sha256"] == stored["artifact_roi_assist"]["binding_sha256"]
    assert row["history"] == stored["artifact_roi_history"]
    assert "mask_png_base64" not in json.dumps(row)
    assert row["state"]["overlay_url"] is None
    assert stored == original


@pytest.mark.parametrize("authority", ["case_image", "case_source", "admission_source",
                                        "nested_integrity", "metadata_hash", "metadata_integrity"])
def test_export_and_live_share_every_recorded_source_authority(fixture, authority):
    app, case, image, provider = fixture
    client(fixture).post(BASE + "/prepare", json={"revision": 0})
    stored = app.state.store.get(case["image_id"])
    if authority == "case_image":
        stored["image_sha256"] = "b" * 64
    elif authority == "case_source":
        stored["source_sha256"] = "b" * 64
    elif authority == "admission_source":
        stored["admission"]["source_sha256"] = "b" * 64
    elif authority == "nested_integrity":
        stored["admission"]["integrity"]["status"] = "SOURCE_CHANGED"
    elif authority == "metadata_hash":
        stored["admission"]["source_metadata"]["source_sha256"] = "b" * 64
    else:
        stored["admission"]["source_metadata"]["integrity_status"] = "SOURCE_CHANGED"
    original = deepcopy(stored)
    admissions = {case["image_id"]: deepcopy(stored["admission"])}
    scope = module.scope_for_app(app, app.state.store)
    live = module.project(stored, image, provider, scope=scope, admission=admissions[case["image_id"]])
    row = module.export_rows([stored], images=app.state.images, admissions=admissions,
                             provider=provider, scope=scope)[0]
    assert live["suppressed_ids"] == row["state"]["suppressed_ids"] == []
    assert row["state"]["status"] == "STALE_RETAIN_ALL"
    assert len(row["state"]["visible_ids"]) == 2
    assert row["historical_decision"]["status"] == "READY"
    assert len(row["historical_decision"]["suppressed_ids"]) == 1
    assert row["history"] == original["artifact_roi_history"] and stored == original


def test_missing_snapshot_image_or_current_admission_conflict_retains_all(fixture):
    app, case, _, provider = fixture
    client(fixture).post(BASE + "/prepare", json={"revision": 0})
    stored = app.state.store.get(case["image_id"])
    scope = module.scope_for_app(app, app.state.store)
    missing = module.export_rows([stored], images={}, provider=provider, scope=scope)[0]
    assert missing["state"]["status"] == "STALE_RETAIN_ALL" and missing["state"]["suppressed_ids"] == []
    changed = deepcopy(app.state.admissions)
    changed[case["image_id"]]["integrity_status"] = "SOURCE_CHANGED"
    row = module.export_rows([stored], images=app.state.images, admissions=changed, provider=provider, scope=scope)[0]
    assert row["state"]["status"] == "STALE_RETAIN_ALL" and row["state"]["suppressed_ids"] == []


def test_disabled_export_uses_disabled_live_policy_without_losing_audit(fixture, monkeypatch):
    app, case, _, provider = fixture
    client(fixture).post(BASE + "/prepare", json={"revision": 0})
    stored = app.state.store.get(case["image_id"])
    monkeypatch.setenv(module.FLAG, "0")
    row = module.export_rows([stored], images=app.state.images, admissions=app.state.admissions,
                             provider=provider, scope=module.scope_for_app(app, app.state.store))[0]
    assert row["state"]["status"] == "DISABLED" and row["state"]["suppressed_ids"] == []
    assert row["historical_decision"]["status"] == "READY"
    assert row["history"] == stored["artifact_roi_history"]
