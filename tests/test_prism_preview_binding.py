"""CPU-only HTTP contracts. No app factory, database, CV2 or model import."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from threading import RLock
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from dr_support.images import BridgeImage
from dr_support.services.prism_preview import (
    MASK_VERSION, MODEL_ID, PROTOCOL, PreviewSubmitRequest, PrismPreviewService,
    canonical, install_prism_preview_routes, png, sha,
)
from dr_support.services.prism_preview_runtime import ReviewPrismPreview


class MemoryStore:
    def __init__(self):
        self.lock = RLock()
        self.case = {"revision": 0, "source_sha256": None, "analysis_preparation": None,
                     "lesion": None, "global": None, "events": [],
                     "reviewed_grade": 2, "grade_status": "CONFIRMED", "human_annotations": ["preserve"],
                     "clinician_review": {"reviewer": "synthetic-reviewer"}, "inference_history": []}

    def get(self, image_id):
        return deepcopy(self.case)

    def put(self, case):
        self.case = deepcopy(case)


class FakeProvider:
    prism_preview_protocol = PROTOCOL

    def __init__(self):
        self.calls = 0
        self.config = "c" * 64
        self.strip = 1
        self.bad_receipt = False
        self.bad_result = False
        self.fail = False

    def prism_preview_identity(self):
        return {"model_version": "synthetic-v1", "descriptor": {"model_id": MODEL_ID},
                "model_pins": {"model_id": MODEL_ID, "source_revision": "a" * 40,
                               "preprocessing": "locked-synthetic-config", "config_sha256": self.config,
                               "checkpoint_sha256": {"fake.pt": "b" * 64}}}

    def prepare_prism_preview_candidate(self, wire):
        candidate = Image.new("L", wire.size, 255)
        for y in range(wire.size[1]):
            for x in range(self.strip):
                candidate.putpixel((x, y), 0)
        return {"status": "READY", "reason_code": None, "mask_png": png(candidate), "mask_version": MASK_VERSION}

    def infer_bound_prism(self, request, wire, *, mask_png, binding, plan_sha256):
        assert sha(wire.data) == binding["wire_sha256"]
        assert sha(mask_png) == binding["mask_png_sha256"]
        assert sha(canonical(binding)) == plan_sha256
        self.calls += 1  # Fake call only: no model, socket or external adapter.
        if self.fail:
            raise RuntimeError("synthetic failure")
        pins = self.prism_preview_identity()["model_pins"]
        return {"preview_receipt": {"plan_sha256": plan_sha256, "wire_sha256": "0" * 64 if self.bad_receipt else wire.sha256,
                                     "mask_sha256": binding["mask_sha256"], "transform_sha256": binding["transform"]["sha256"]},
                "result": {"model_id": MODEL_ID, "model_version": "synthetic-v1", "modality": "UWF",
                           "width": wire.size[0], "height": wire.size[1], "lesions": [], "warnings": ["Synthetic only"],
                           "provenance": {"image_sha256": "0" * 64 if self.bad_result else wire.sha256,
                                          "source_type": "SYNTHETIC", "preprocessing": pins["preprocessing"],
                                          "source_revision": pins["source_revision"], "checkpoint_sha256": pins["checkpoint_sha256"]}},
                "processing_evidence": {"input_image_sha256": wire.sha256, "processing_mode": "FALLBACK",
                                        "native_roi_status": "FAILED", "native_roi_bbox": None,
                                        "external_fov_status": "READY", "fov_used_for_model_input": False,
                                        "raw_boundary_classes": []}}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    # Guard accidental DB/socket use, even though the actual app factory is never imported.
    import sqlite3
    monkeypatch.setenv("WORKERS", "1")
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("DB access forbidden"))
    data = png(Image.new("RGB", (32, 24), (80, 40, 20)))
    source_path = tmp_path / "synthetic.png"
    source_path.write_bytes(data)
    image = BridgeImage("fixture", source_path.read_bytes(), "SYNTHETIC", "fixture", modality="UWF",
                        media_type="image/png", source_origin="SYNTHETIC")
    store, provider = MemoryStore(), FakeProvider()
    mapping = SimpleNamespace(model_dump=lambda **kwargs: {"kind": "IDENTITY", "scale_x": 1, "scale_y": 1})
    derivative = SimpleNamespace(coordinate_mapping=mapping, audit_record=lambda: {
        "source_sha256": image.sha256, "analysis_sha256": image.sha256,
        "transform_id": "analysis-uwf-unmasked-source-v1", "transform_version": 1,
        "representation_version": "uwf-source-analysis-v1"})
    derivatives = SimpleNamespace(analysis_image=lambda source, **kwargs: (source, derivative))
    app = FastAPI()
    app.state.store = store
    app.state.images = {"fixture": image, "other": image}
    app.state.admissions = {key: {"source_origin": "SYNTHETIC", "retinal_modality": "UWF",
                                  "modality_admission": "FUNDUS_ACCEPTED", "quality_state": "GRADABLE"}
                            for key in app.state.images}
    app.state.providers = {MODEL_ID: provider}
    app.state.derivatives = derivatives
    saved = []

    def save(request, task, result, derivative, **kwargs):
        assert kwargs["target_store"] is store
        saved.append(kwargs)
        store.case["revision"] += 1
        store.case["inference_history"].append({"preview_binding": kwargs["preview_binding"]})

    runtime = ReviewPrismPreview(app, save_result=save,
                                 source_allowed=lambda origin: origin == "SYNTHETIC",
                                 eligible=lambda admission: admission.get("modality_admission") == "FUNDUS_ACCEPTED"
                                 and admission.get("quality_state") == "GRADABLE",
                                 route=lambda descriptor, modality: SimpleNamespace(capability_id="fixture"),
                                 map_result=lambda result, mapping: result, inference_lock=RLock())
    clock = [0.0]
    service = PrismPreviewService(runtime.snapshot, runtime.execute, clock=lambda: clock[0])
    install_prism_preview_routes(app, service)
    return SimpleNamespace(app=app, client=TestClient(app), service=service, runtime=runtime,
                           store=store, provider=provider, image=image, derivative=derivative,
                           clock=clock, saved=saved)


def prepare(rig):
    response = rig.client.post("/v1/cases/fixture/prism-input-preview", json={"revision": 0})
    assert response.status_code == 200, response.text
    return response.json()


def payload(plan):
    return dict(revision=plan["case_revision"], source_sha256=plan["source_sha256"], wire_sha256=plan["wire_sha256"],
                plan_sha256=plan["plan_sha256"], mask_sha256=plan["mask"]["sha256"],
                transform_sha256=plan["transform"]["sha256"], model_version=plan["model_version"])


def submit(rig, plan, body=None):
    return rig.client.post(f'/v1/cases/fixture/prism-input-preview/{plan["plan_id"]}/infer',
                           json=body if body is not None else payload(plan))


def test_prepare_is_cpu_only_with_exact_wire_assets_and_no_clinical_changes(rig):
    before = deepcopy(rig.store.case)
    plan = prepare(rig)
    assert rig.provider.calls == 0 and rig.saved == [] and rig.store.case == before
    assert plan["wire_sha256"] == rig.image.sha256
    assert plan["native_roi_status"] == "NOT_RUN" and plan["native_roi_bbox"] is None
    assert plan["final_crop_or_tensor_sha256"] is None and not plan["exact_lesion_input_available"]
    assert plan["mask_application"] == "CONDITIONAL_ON_NATIVE_ROI_SUCCESS"
    assert plan["submission_binding_enforced"] is True
    for key in ("original_preview", "input_preview", "overlay"):
        response = rig.client.get(plan[key]["url"])
        assert response.status_code == 200 and sha(response.content) == plan[key]["sha256"]
        assert response.headers["cache-control"] == "no-store"


def test_one_use_submission_preserves_human_review_and_stores_binding(rig):
    plan = prepare(rig)
    assert submit(rig, plan).status_code == 200
    assert rig.provider.calls == 1 and len(rig.saved) == 1
    assert rig.store.case["reviewed_grade"] == 2 and rig.store.case["grade_status"] == "CONFIRMED"
    assert rig.store.case["human_annotations"] == ["preserve"]
    assert rig.saved[0]["preview_binding"]["plan_sha256"] == plan["plan_sha256"]
    assert submit(rig, plan).status_code == 409 and rig.provider.calls == 1


@pytest.mark.parametrize("field", ["source_sha256", "wire_sha256", "plan_sha256", "mask_sha256", "transform_sha256", "model_version"])
def test_forged_acknowledgement_cannot_execute(rig, field):
    plan = prepare(rig)
    body = payload(plan)
    body[field] = "other" if field == "model_version" else "0" * 64
    assert submit(rig, plan, body).status_code == 409
    assert rig.provider.calls == 0 and not rig.saved


@pytest.mark.parametrize("change", ["revision", "source", "wire", "mask", "config", "checkpoint", "transform", "admission", "workspace", "expiry"])
def test_stale_server_context_is_rejected_before_fake_forward(rig, change):
    plan = prepare(rig)
    if change == "revision":
        rig.store.case["revision"] = 1
    elif change == "source":
        rig.app.state.images["fixture"] = replace(rig.image, data=png(Image.new("RGB", (32, 24), (1, 2, 3))))
    elif change == "wire":
        other = replace(rig.image, data=png(Image.new("RGB", (32, 24), (1, 2, 3))))
        rig.app.state.derivatives.analysis_image = lambda *a, **k: (other, rig.derivative)
    elif change == "mask":
        rig.provider.strip = 2
    elif change == "config":
        rig.provider.config = "d" * 64
    elif change == "checkpoint":
        original = rig.provider.prism_preview_identity
        def changed():
            result = original()
            result["model_pins"]["checkpoint_sha256"]["fake.pt"] = "e" * 64
            return result
        rig.provider.prism_preview_identity = changed
    elif change == "transform":
        original = rig.derivative.audit_record
        rig.derivative.audit_record = lambda: {**original(), "representation_version": "changed"}
    elif change == "admission":
        rig.app.state.admissions["fixture"]["quality_state"] = "UNGRADABLE"
    elif change == "workspace":
        rig.app.state.store = MemoryStore()
    else:
        rig.clock[0] = 301
    assert submit(rig, plan).status_code in {409, 503}
    assert rig.provider.calls == 0 and not rig.saved


def test_cross_case_and_sibling_receipts_cannot_replay(rig):
    one, two = prepare(rig), prepare(rig)
    wrong = rig.client.post(f'/v1/cases/other/prism-input-preview/{one["plan_id"]}/infer', json=payload(one))
    assert wrong.status_code == 409 and rig.provider.calls == 0
    assert submit(rig, one).status_code == 200
    assert submit(rig, two).status_code == 409 and rig.provider.calls == 1


def test_concurrent_submission_forwards_at_most_once(rig):
    plan = prepare(rig)
    request = PreviewSubmitRequest(**payload(plan))
    def run():
        try:
            rig.service.submit("fixture", plan["plan_id"], request)
            return 200
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: run(), range(2))) == [200, 409]
    assert rig.provider.calls == 1


@pytest.mark.parametrize("failure", ["bad_receipt", "bad_result", "fail"])
def test_unverified_or_failed_result_is_not_saved_or_retried(rig, failure):
    plan = prepare(rig)
    setattr(rig.provider, failure, True)
    assert submit(rig, plan).status_code == 502
    assert not rig.saved and rig.store.case["revision"] == 0
    assert submit(rig, plan).status_code == 409 and rig.provider.calls == 1


def test_unsupported_provider_never_silently_uses_legacy_infer(rig):
    rig.provider.prism_preview_protocol = None
    response = rig.client.post("/v1/cases/fixture/prism-input-preview", json={"revision": 0})
    assert response.status_code == 503 and rig.provider.calls == 0


def test_receipt_cache_is_bounded_and_eviction_invalidates_old_tokens(rig):
    rig.service.max_plans = 1
    one = prepare(rig)
    prepare(rig)
    assert len(rig.service.plans) == 1
    assert submit(rig, one).status_code == 409 and rig.provider.calls == 0


@pytest.mark.parametrize("defect", ["v4", "size", "nonbinary", "empty", "uncertain", "media"])
def test_invalid_mask_or_wire_is_not_presented_as_ready(rig, defect):
    original = rig.provider.prepare_prism_preview_candidate
    def changed(wire):
        candidate = original(wire)
        if defect == "v4":
            candidate["mask_version"] = "candidate-v4"
        elif defect == "size":
            candidate["mask_png"] = png(Image.new("L", (16, 12), 255))
        elif defect == "nonbinary":
            candidate["mask_png"] = png(Image.new("L", wire.size, 128))
        elif defect == "empty":
            candidate["mask_png"] = png(Image.new("L", wire.size, 0))
        elif defect == "uncertain":
            candidate["status"] = "UNCERTAIN"
        return candidate
    rig.provider.prepare_prism_preview_candidate = changed
    if defect == "media":
        rig.app.state.images["fixture"] = replace(rig.image, media_type="image/jpeg")
    response = rig.client.post("/v1/cases/fixture/prism-input-preview", json={"revision": 0})
    assert response.status_code == 409 and rig.provider.calls == 0


def _actual_save_result(rig):
    """Compile only the reviewed pure saver body with a memory store, never import/create app."""
    import ast
    from datetime import datetime, timezone
    from uuid import uuid4
    source = (Path(__file__).parents[1] / "dr_support/api/_factory.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "save_result")
    module = ast.Module(body=[function], type_ignores=[])
    globals_ = {"app": rig.app, "datetime": datetime, "timezone": timezone, "uuid4": uuid4,
                "descriptor_for": lambda model: {"capability_id": "fixture"},
                "RemoteModelProvider": type("UnusedRemote", (), {})}
    exec(compile(ast.fix_missing_locations(module), "reviewed_save_result_memory_fixture", "exec"), globals_)
    return globals_["save_result"]


def test_actual_saver_records_late_result_in_original_workspace_without_overwriting_clinician(rig):
    from dr_support.contracts import InferenceRequest, LesionResult
    plan = prepare(rig)
    cached = rig.service.plans[plan["plan_id"]]
    returned = rig.provider.infer_bound_prism(InferenceRequest(image_id="fixture", modality="UWF", model_id=MODEL_ID),
                                            rig.image, mask_png=cached.snapshot.mask, binding=cached.binding,
                                            plan_sha256=plan["plan_sha256"])
    result = LesionResult.model_validate(returned["result"])
    rig.store.case.update(revision=1, reviewed_grade=3, human_annotations=["new-human-edit"])
    fresh_store = MemoryStore()
    rig.app.state.store = fresh_store
    binding = {"plan_sha256": plan["plan_sha256"], **cached.binding}
    applied = _actual_save_result(rig)(InferenceRequest(image_id="fixture", modality="UWF", model_id=MODEL_ID),
                                      "lesion-roi", result, rig.derivative,
                                      request_case_revision=0, target_store=rig.store, target_provider=rig.provider,
                                      preview_binding=binding)
    assert applied is False and fresh_store.case["inference_history"] == []
    assert rig.store.case["reviewed_grade"] == 3 and rig.store.case["human_annotations"] == ["new-human-edit"]
    assert rig.store.case["lesion"] is None
    assert rig.store.case["inference_history"][0]["status"] == "STALE_RESULT"
    assert rig.store.case["inference_history"][0]["preview_binding"] == binding


def test_provider_replacement_with_identical_pins_is_rejected_at_execution_boundary(rig):
    plan = prepare(rig)
    new_provider = FakeProvider()
    rig.app.state.providers[MODEL_ID] = new_provider
    assert submit(rig, plan).status_code == 409
    assert rig.provider.calls == new_provider.calls == 0


def test_binding_minimizes_admission_metadata_without_losing_integrity(rig):
    rig.app.state.admissions["fixture"].update(filename="synthetic-private-name.png", source_reference="private-root")
    plan = prepare(rig)
    binding = rig.service.plans[plan["plan_id"]].binding
    assert "synthetic-private-name" not in canonical(binding).decode()
    assert "private-root" not in canonical(binding).decode()
    assert "admission_sha256" in binding
    rig.app.state.admissions["fixture"]["filename"] = "renamed.png"
    assert submit(rig, plan).status_code == 409 and rig.provider.calls == 0


@pytest.mark.parametrize("defect", ["fallback", "fov_status", "native_success_without_mask"])
def test_post_run_processing_must_preserve_conditional_fallback_contract(rig, defect):
    plan = prepare(rig)
    original = rig.provider.infer_bound_prism
    def changed(*args, **kwargs):
        returned = original(*args, **kwargs)
        if defect == "fallback":
            returned["processing_evidence"]["processing_mode"] = "LEGACY"
        elif defect == "fov_status":
            returned["processing_evidence"]["external_fov_status"] = "UNAVAILABLE"
        else:
            returned["processing_evidence"].update(native_roi_status="SUCCEEDED", native_roi_bbox=[0, 0, 32, 24])
        return returned
    rig.provider.infer_bound_prism = changed
    assert submit(rig, plan).status_code == 502 and not rig.saved


def test_expiry_is_rechecked_after_waiting_for_provider_lock(rig):
    plan = prepare(rig)
    class DelayedLock:
        def __enter__(self):
            rig.clock[0] = 301
        def __exit__(self, *args):
            return False
    rig.runtime.inference_lock = DelayedLock()
    assert submit(rig, plan).status_code == 409 and rig.provider.calls == 0


def test_unqualified_multiworker_configuration_is_not_enabled(rig, monkeypatch):
    monkeypatch.setenv("WORKERS", "2")
    response = rig.client.post("/v1/cases/fixture/prism-input-preview", json={"revision": 0})
    assert response.status_code == 503 and rig.provider.calls == 0


def test_concurrent_clinician_edit_is_not_blocked_or_overwritten_by_fake_forward(rig):
    plan = prepare(rig)
    rig.runtime.save_result = _actual_save_result(rig)
    original = rig.provider.infer_bound_prism
    def with_human_edit(*args, **kwargs):
        def edit():
            with rig.store.lock:
                rig.store.case.update(revision=1, reviewed_grade=3, human_annotations=["new-clinician-shape"])
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(edit).result(timeout=2)
        return original(*args, **kwargs)
    rig.provider.infer_bound_prism = with_human_edit
    response = submit(rig, plan)
    assert response.status_code == 200 and response.json()["status"] == "STALE_RESULT"
    assert rig.store.case["reviewed_grade"] == 3 and rig.store.case["human_annotations"] == ["new-clinician-shape"]
    assert rig.store.case["lesion"] is None
    assert rig.store.case["inference_history"][0]["status"] == "STALE_RESULT"


def test_submission_cannot_smuggle_clinical_confirmation_or_boolean_revision(rig):
    plan = prepare(rig)
    body = {**payload(plan), "grade": 4, "action": "ACCEPT"}
    assert submit(rig, plan, body).status_code == 422
    assert submit(rig, plan, {**payload(plan), "revision": False}).status_code == 422
    assert rig.provider.calls == 0 and rig.store.case["reviewed_grade"] == 2


def test_main_factory_wires_binding_and_blocks_legacy_prism_without_executing_factory():
    import ast
    source = (Path(__file__).parents[1] / "dr_support/api/_factory.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    infer = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "infer")
    assert isinstance(infer.body[0], ast.If)
    assert "prism-dr-5fold" in ast.unparse(infer.body[0]) and "409" in ast.unparse(infer.body[0])
    assert "install_prism_preview_routes(app, app.state.prism_preview)" in source
    assert "store = target_store if target_store is not None else app.state.store" in source
