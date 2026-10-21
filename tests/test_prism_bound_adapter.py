"""Real PRISM loop with fake ROI/folds/FOV and synthetic bytes. No Torch/CV2/DB."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import builtins
import json
from pathlib import Path
from types import SimpleNamespace
from threading import Event

import numpy as np
from PIL import Image
from fastapi import HTTPException
import pytest

from dr_support.images import BridgeImage
from dr_support.providers import prism_bound as bound
from dr_support.providers.prism import PRISM, REVISION
from test_prism_preview_binding import rig as _review_rig, payload
from dr_support.services.prism_preview import PreviewSubmitRequest

review_rig = _review_rig


@pytest.fixture(autouse=True)
def forbid_real_runtime(monkeypatch):
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "cv2"}:
            pytest.fail("Torch/CV2 execution forbidden in this offline candidate test")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(PRISM, "load", lambda *_: pytest.fail("Real checkpoint load forbidden"))
    import socket
    import sqlite3
    import psycopg
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("Network/listener forbidden"))
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("SQL forbidden"))
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: pytest.fail("SQL forbidden"))


@pytest.fixture
def frozen_module():
    # Joint qualification uses this review branch's actual CPU serializer.
    from dr_support.services import prism_preview as module
    return module


class Tensor:
    def __init__(self, values):
        self.values = values

    def detach(self):
        return self

    float = cpu = numpy = detach

    def tolist(self):
        return self.values


class Boxes:
    xyxy = [Tensor([1, 1, 7, 5])]

    def __len__(self):
        return 1


@pytest.fixture
def rig(monkeypatch, frozen_module):
    monkeypatch.delenv("PRISM_THRESHOLDS", raising=False)
    monkeypatch.setenv("MODEL_RUNTIME", "local")
    data = bound.png(Image.new("RGB", (8, 6), (90, 50, 20)))
    wire = BridgeImage("fixture", data, "SYNTHETIC", "synthetic", modality="UWF", media_type="image/png", source_origin="SYNTHETIC")
    provider = bound.BoundLocalPRISM()
    pins = {"model_id": provider.model_id, "source_revision": REVISION, "preprocessing": "locked-fake-config-not-inference-proof",
            "config_sha256": "c" * 64, "checkpoint_sha256": json.loads(Path(bound.__file__).with_name("prism_assets.json").read_text())["weights"]}
    monkeypatch.setattr(provider, "_runtime_identity", lambda: deepcopy(pins))
    monkeypatch.setattr(provider, "_release_cuda_memory", lambda *_: None)
    monkeypatch.setattr(provider, "_resolve_device", lambda: "cpu")
    monkeypatch.setattr(provider, "metadata", lambda: {"warnings": ["FAKE_INTERNALS_ONLY_NOT_REAL_QUALIFICATION"]})
    provider.loaded = True
    provider.hashes = deepcopy(pins["checkpoint_sha256"])
    provider._loaded_identity = deepcopy(pins)
    calls = {"detect": 0, "roi": 0, "fold": 0, "roi_fail": False, "status": "READY", "roi_input": None, "lesion_input": None}

    def detect(rgb):
        calls["detect"] += 1
        mask = Image.new("L", rgb.size, 255)
        for y in range(rgb.height):
            mask.putpixel((0, y), 0)
        ready = calls["status"] == "READY"
        digest = bound.sha(bound.MASK_VERSION.encode() + bound.struct.pack(">II", *rgb.size) + mask.tobytes())
        return SimpleNamespace(status=calls["status"], reason_code=None if ready else "SYNTHETIC_UNCERTAIN",
            field_mask=mask if ready else None, mask_version=bound.MASK_VERSION,
            mask_sha256=digest if ready else None, source_rgb_sha256=bound.rgb_hash(rgb), boundary_confidence=.9 if ready else None,
            field_fraction=.875 if ready else None, excluded_fraction=.125 if ready else None,
            bounding_box=(1, 0, 8, 6) if ready else None, boundary=((1, 0), (8, 0), (8, 6), (1, 6)) if ready else (),
            image_width=rgb.width, image_height=rgb.height)
    monkeypatch.setattr(provider, "_detect_baseline", detect)
    monkeypatch.setattr(bound, "restore_fov", lambda metadata, mask: SimpleNamespace(**json.loads(metadata), field_mask=mask))

    def roi(image, **kwargs):
        calls["roi"] += 1
        calls["roi_input"] = image.copy()
        if calls["roi_fail"]:
            raise RuntimeError("FAKE_ROI_FAILURE")
        return [SimpleNamespace(boxes=Boxes())]
    provider.roi = roi
    def preprocess(image):
        calls["lesion_input"] = image.copy()
        return image
    def fold(image, model, size, overlap):
        calls["fold"] += 1
        assert size == 1280 and overlap == .25
        return []
    provider.engine = SimpleNamespace(preprocess_image=preprocess, run_sahi_inference=fold,
        _majority_voting=lambda *a, **k: ([], [], []), apply_inter_class_nms=lambda values, **kwargs: values)
    provider.models = {"MA": [SimpleNamespace(confidence_threshold=0) for _ in range(5)]}
    provider.config = SimpleNamespace(get_lesion_config=lambda label: SimpleNamespace(get_val_best_conf=lambda fold: .1))

    def prepare(image=wire, source=None):
        candidate = provider.prepare_prism_preview_candidate(image)
        admission = {"source_origin": "SYNTHETIC", "retinal_modality": image.modality,
            "modality_admission": "FUNDUS_ACCEPTED", "quality_state": "GRADABLE",
            "source_sha256": bound.sha(source or image.data), "integrity_status": "OK"}
        recorded = dict(case_source_sha256=admission["source_sha256"], admission_source_sha256=admission["source_sha256"],
            image_recorded_sha256=admission["source_sha256"], integrity_status="OK", source_origin="SYNTHETIC",
            case_revision=1, admission_sha256=bound.sha(bound.canonical(admission)))
        snapshot = frozen_module.PreviewSnapshot(scope="fixture-scope", image_id=image.image_id, revision=1,
            source=source or image.data, wire=image.data, wire_media_type=image.media_type, modality=image.modality,
            model_version=REVISION, model_pins=deepcopy(pins),
            transform={"version": "1", "transform_id": "analysis-uwf-unmasked-source-v1" if image.modality == "UWF" else "analysis-source-v1",
                "representation_version": "uwf-source-analysis-v1" if image.modality == "UWF" else "uwf-analysis-representation-v1",
                "original_width": 8, "original_height": 6, "input_width": 8, "input_height": 6,
                "original_to_input": [1, 0, 0, 1, 0, 0], "coordinate_mapping": {"kind": "IDENTITY", "scale_x": 1, "scale_y": 1}},
            preparation_context="fixture", admission=admission, recorded_source_identity=recorded,
            external_fov_status=candidate["status"], external_fov_reason_code=candidate["reason_code"],
            mask=candidate["mask_png"], mask_version=candidate["mask_version"], runtime=None)
        binding, _ = frozen_module.PrismPreviewService._freeze(snapshot)
        binding.update(plan_id="synthetic-plan", generation=0, expires_at=(datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat())
        return binding, candidate["mask_png"]
    request = SimpleNamespace(image_id="fixture", model_id=provider.model_id, modality="UWF")
    return SimpleNamespace(provider=provider, wire=wire, request=request, prepare=prepare, calls=calls, pins=pins)


def execute(rig, binding, mask):
    return rig.provider.infer_bound_prism(rig.request, rig.wire, mask_png=mask, binding=binding,
                                         plan_sha256=bound.sha(bound.canonical(binding)), before_forward=lambda: None)


def submit_review(review, plan):
    return review.service.submit("fixture", plan["plan_id"], PreviewSubmitRequest(**payload(plan)))


def test_joint_review_uses_frozen_wire_mask_and_recorded_server_identity(rig, review_rig):
    review_rig.app.state.providers[rig.provider.model_id] = rig.provider
    plan = review_rig.service.prepare("fixture", 0)
    frozen = review_rig.service.plans[plan["plan_id"]]
    recorded = frozen.binding["recorded_source_identity"]
    assert recorded["image_recorded_sha256"] == review_rig.store.case["image_sha256"]
    assert recorded["case_source_sha256"] == review_rig.store.case["source_sha256"]
    assert recorded["admission_source_sha256"] == review_rig.app.state.admissions["fixture"]["source_sha256"]
    assert "recorded_source_identity" not in plan  # Internal authority is not request input.
    assert plan["native_roi_status"] == "NOT_RUN" and not plan["exact_lesion_input_available"]
    assert rig.calls["detect"] == 1 and rig.calls["roi"] == 0
    for name in ("original", "input", "overlay"):
        assert review_rig.service.asset("fixture", plan["plan_id"], name)
    response = submit_review(review_rig, plan)
    assert rig.calls["detect"] == rig.calls["roi"] == 1 and rig.calls["fold"] == 5
    assert np.all(rig.calls["roi_input"][:, 0] == 0)
    assert bound.sha(frozen.snapshot.wire) == plan["wire_sha256"]
    assert response["result"]["state"] == "AI_SUGGESTION"
    assert len(review_rig.saved) == 1
    with pytest.raises(HTTPException) as caught:
        submit_review(review_rig, plan)
    assert caught.value.status_code == 409
    assert rig.calls["roi"] == 1


@pytest.mark.parametrize("defect", ["cache_missing", "case_hash", "integrity", "config", "protocol"])
def test_joint_revalidation_fails_without_redetection_or_forward(rig, review_rig, defect):
    review_rig.app.state.providers[rig.provider.model_id] = rig.provider
    plan = review_rig.service.prepare("fixture", 0)
    if defect == "cache_missing":
        rig.provider._candidates.clear()
    elif defect == "case_hash":
        review_rig.store.case["image_sha256"] = "f" * 64
    elif defect == "integrity":
        review_rig.app.state.admissions["fixture"]["integrity_status"] = "SOURCE_CHANGED"
    elif defect == "config":
        rig.pins["config_sha256"] = "d" * 64
    else:
        rig.provider.prism_preview_protocol = "prism-wire-binding.v1"
    with pytest.raises(HTTPException) as caught:
        submit_review(review_rig, plan)
    assert caught.value.status_code in {409, 503}
    assert rig.calls["detect"] == 1 and rig.calls["roi"] == rig.calls["fold"] == 0
    assert not review_rig.saved
    assert review_rig.store.case["reviewed_grade"] == 2


def test_candidate_not_imported_or_registered_by_default_factory():
    root = Path(__file__).parents[1] / "dr_support"
    for relative in ["api/_factory.py", "providers/__init__.py", "providers/remote.py"]:
        path = root / relative
        if path.exists():
            text = path.read_text(encoding="utf-8")
            assert "BoundLocalPRISM" not in text and "prism_bound" not in text


@pytest.mark.parametrize("change", ["source", "integrity", "review", "workspace", "record_removed"])
def test_joint_source_authority_rechecked_after_fake_load(rig, review_rig, monkeypatch, change):
    review_rig.app.state.providers[rig.provider.model_id] = rig.provider
    plan = review_rig.service.prepare("fixture", 0)
    rig.provider.loaded = False
    def fake_load():
        rig.provider.loaded = True
        if change == "source":
            review_rig.store.case["image_sha256"] = "d" * 64
        elif change == "integrity":
            review_rig.app.state.admissions["fixture"]["integrity_status"] = "SOURCE_CHANGED"
        elif change == "review":
            review_rig.store.case["revision"] += 1
        elif change == "record_removed":
            review_rig.store.case.pop("source_sha256")
            review_rig.store.case.pop("image_sha256")
        else:
            review_rig.app.state.store = object()
    monkeypatch.setattr(rig.provider, "load", fake_load)
    with pytest.raises(HTTPException) as caught:
        submit_review(review_rig, plan)
    assert caught.value.status_code == 409
    assert rig.calls["detect"] == 1 and rig.calls["roi"] == rig.calls["fold"] == 0
    assert not review_rig.saved
    with pytest.raises(HTTPException):
        submit_review(review_rig, plan)


def test_adapter_requires_trusted_server_forward_guard(rig):
    binding, mask = rig.prepare()
    with pytest.raises(bound.BoundPlanError, match="SERVER_SOURCE_REVALIDATION_REQUIRED"):
        rig.provider.infer_bound_prism(rig.request, rig.wire, mask_png=mask, binding=binding,
                                      plan_sha256=bound.sha(bound.canonical(binding)))
    assert rig.calls["roi"] == 0


def test_joint_missing_recorded_integrity_is_not_invented_from_bytes(rig, review_rig):
    review_rig.app.state.providers[rig.provider.model_id] = rig.provider
    review_rig.app.state.admissions["fixture"].pop("integrity_status")
    before = deepcopy(review_rig.store.case)
    with pytest.raises(HTTPException) as caught:
        review_rig.service.prepare("fixture", 0)
    assert caught.value.status_code == 503
    assert rig.calls["detect"] == rig.calls["roi"] == 0
    assert review_rig.store.case == before


def test_frozen_mask_reaches_actual_roi_loop_without_redetection(rig):
    binding, mask = rig.prepare()
    assert rig.calls["roi"] == rig.calls["fold"] == 0
    # Fresh snapshot reuses immutable baseline candidate, never a new detector/model.
    assert rig.prepare()[1] == mask and rig.calls["detect"] == 1
    returned = execute(rig, binding, mask)
    assert rig.calls["roi"] == 1 and rig.calls["fold"] == 5 and rig.calls["detect"] == 1
    assert np.all(rig.calls["roi_input"][:, 0] == 0)
    assert np.array_equal(rig.calls["lesion_input"], rig.calls["roi_input"][1:5, 1:7])
    assert returned["processing_evidence"]["processing_mode"] == "PREPARED"
    assert returned["processing_evidence"]["analysis_field"]["mask_sha256"] == binding["mask_sha256"]
    assert returned["result"]["state"] == "AI_SUGGESTION" and returned["result"]["lesions"] == []
    assert returned["preview_receipt"]["wire_sha256"] == rig.wire.sha256
    with pytest.raises(bound.BoundPlanError, match="REPLAY"):
        execute(rig, binding, mask)
    assert rig.calls["roi"] == 1


def test_native_roi_failure_discards_frozen_mask_and_uses_full_original(rig):
    binding, mask = rig.prepare()
    rig.calls["roi_fail"] = True
    returned = execute(rig, binding, mask)
    assert np.all(rig.calls["roi_input"][:, 0] == 0)
    original_bgr = np.asarray(bound.decode(rig.wire.data))[:, :, ::-1]
    assert np.array_equal(rig.calls["lesion_input"], original_bgr)
    processing = returned["processing_evidence"]
    assert processing["processing_mode"] == "FALLBACK" and processing["analysis_field"] is None
    assert not processing["fov_used_for_model_input"] and processing["native_roi_status"] == "FAILED"


@pytest.mark.parametrize("field", ["case_source_sha256", "admission_source_sha256", "image_recorded_sha256"])
def test_newly_rehashed_bytes_cannot_replace_recorded_identity(rig, field):
    binding, mask = rig.prepare()
    binding["recorded_source_identity"][field] = "d" * 64
    with pytest.raises(bound.BoundPlanError, match="RECORDED_SOURCE_CHANGED"):
        execute(rig, binding, mask)
    assert rig.calls["roi"] == rig.calls["fold"] == 0


@pytest.mark.parametrize("integrity", ["SOURCE_CHANGED", "UNKNOWN", None])
def test_integrity_conflict_rejected_before_any_fake_forward(rig, integrity):
    binding, mask = rig.prepare()
    binding["recorded_source_identity"]["integrity_status"] = integrity
    with pytest.raises(bound.BoundPlanError, match="RECORDED_SOURCE_CHANGED"):
        execute(rig, binding, mask)
    assert rig.calls["roi"] == 0


def test_frozen_v1_without_source_attestation_remains_unsupported(rig, frozen_module):
    binding, mask = rig.prepare()
    del binding["recorded_source_identity"]
    assert rig.provider.prism_preview_protocol == frozen_module.PROTOCOL
    assert not rig.provider.prism_preview_identity()["descriptor"]["ready"]
    with pytest.raises(bound.BoundPlanError, match="ATTESTATION_REQUIRED"):
        execute(rig, binding, mask)


@pytest.mark.parametrize("change", ["wire", "mask", "config", "transform", "expired", "admission", "mutable"])
def test_stale_or_unsupported_inputs_never_reach_roi(rig, change):
    binding, mask = rig.prepare()
    if change == "wire":
        rig.wire = replace(rig.wire, data=bound.png(Image.new("RGB", (8, 6), (1, 2, 3))))
    elif change == "mask":
        mask = bound.png(Image.new("L", (8, 6), 255))
    elif change == "config":
        rig.pins["config_sha256"] = "d" * 64
    elif change == "transform":
        binding["transform"]["transform_id"] = "changed"
        binding["transform"]["sha256"] = bound.sha(bound.canonical({k: v for k, v in binding["transform"].items() if k != "sha256"}))
    elif change == "expired":
        binding["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    elif change == "admission":
        binding["admission"]["modality_admission"] = "NEEDS_REVIEW"
    elif change == "mutable":
        rig.wire = replace(rig.wire, data=bytearray(rig.wire.data))
    with pytest.raises(bound.BoundPlanError):
        execute(rig, binding, mask)
    assert rig.calls["roi"] == rig.calls["fold"] == 0


def test_failed_execution_consumes_plan_no_retry(rig, monkeypatch):
    binding, mask = rig.prepare()
    def fail(*args, **kwargs):
        raise RuntimeError("FAKE_EXECUTION_FAILURE")
    monkeypatch.setattr(rig.provider, "_infer_loaded", fail)
    with pytest.raises(RuntimeError, match="FAKE"):
        execute(rig, binding, mask)
    with pytest.raises(bound.BoundPlanError, match="REPLAY"):
        execute(rig, binding, mask)


def test_consumed_plan_id_cannot_be_rehashed_to_replay(rig):
    binding, mask = rig.prepare()
    execute(rig, binding, mask)
    binding["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=130)).isoformat()
    with pytest.raises(bound.BoundPlanError, match="REPLAY"):
        execute(rig, binding, mask)
    assert rig.calls["roi"] == 1


def test_legacy_prism_class_and_normal_behavior_are_not_registered(rig):
    assert not hasattr(PRISM(), "prism_preview_protocol")
    with pytest.raises(bound.BoundPlanError, match="BOUND_PLAN_REQUIRED"):
        rig.provider.infer(rig.request, rig.wire)


def test_wire_rgb_is_used_even_when_original_source_pixels_differ(rig):
    source = bound.png(Image.new("RGB", (8, 6), (20, 40, 80)))
    binding, mask = rig.prepare(source=source)
    assert binding["source_sha256"] != binding["wire_sha256"]
    assert binding["source_rgb_sha256"] == bound.rgb_hash(bound.decode(rig.wire.data))
    returned = execute(rig, binding, mask)
    assert returned["processing_evidence"]["analysis_field"]["source_rgb_sha256"] == binding["wire_rgb_sha256"]


def test_uncertain_fov_still_attempts_native_roi_on_original(rig):
    rig.calls["status"] = "UNCERTAIN"
    binding, mask = rig.prepare()
    assert mask is None
    returned = execute(rig, binding, mask)
    assert rig.calls["roi"] == 1 and rig.calls["fold"] == 5
    assert np.array_equal(rig.calls["roi_input"], np.asarray(bound.decode(rig.wire.data))[:, :, ::-1])
    assert returned["processing_evidence"]["native_roi_status"] == "SUCCEEDED"
    assert returned["processing_evidence"]["processing_mode"] == "FALLBACK"


def test_cfp_preserves_native_legacy_crop_without_fov(rig):
    rig.wire = replace(rig.wire, modality="CFP")
    rig.request.modality = "CFP"
    binding, mask = rig.prepare(rig.wire)
    returned = execute(rig, binding, mask)
    assert rig.calls["detect"] == 0 and rig.calls["roi"] == 1
    assert returned["processing_evidence"]["processing_mode"] == "LEGACY"


def test_restart_and_expired_candidate_are_not_recomputed_at_execution(rig):
    binding, mask = rig.prepare()
    rig.provider._candidates.clear()
    with pytest.raises(bound.BoundPlanError, match="EXPIRED_OR_RESTARTED"):
        execute(rig, binding, mask)
    assert rig.calls["detect"] == 1 and rig.calls["roi"] == 0


def test_config_change_during_load_stops_before_native_roi_and_consumes_plan(rig, monkeypatch):
    binding, mask = rig.prepare()
    rig.provider.loaded = False
    def changed_load():
        rig.provider.loaded = True
        rig.provider._loaded_identity = deepcopy(rig.pins)
        rig.pins["config_sha256"] = "d" * 64
    monkeypatch.setattr(rig.provider, "load", changed_load)
    with pytest.raises(bound.BoundPlanError, match="CONFIG_PINS_CHANGED"):
        execute(rig, binding, mask)
    assert bound.sha(bound.canonical(binding)) in rig.provider._consumed and rig.calls["roi"] == 0


def test_concurrent_submit_never_runs_second_fake_roi(rig):
    binding, mask = rig.prepare()
    entered, release = Event(), Event()
    roi = rig.provider.roi
    def blocked(image, **kwargs):
        entered.set()
        assert release.wait(3)
        return roi(image, **kwargs)
    rig.provider.roi = blocked
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(execute, rig, binding, mask)
        assert entered.wait(3)
        try:
            with pytest.raises(bound.BoundPlanError, match="SERIAL_EXECUTION_ONLY"):
                execute(rig, binding, mask)
        finally:
            release.set()
        assert first.result()["result"]["state"] == "AI_SUGGESTION"
    assert rig.calls["roi"] == 1
