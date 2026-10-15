"""PRISM UWF processing-mode tests using deterministic in-memory predictors."""

from __future__ import annotations

import io
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw


def _synthetic_uwf(*, white_rim: bool) -> Image.Image:
    if not white_rim:
        return Image.new("RGB", (256, 256), (62, 32, 28))
    image = Image.new("RGB", (256, 256), (9, 10, 12))
    draw = ImageDraw.Draw(image)
    draw.ellipse((25, 25, 231, 231), fill=(245, 246, 244))
    draw.ellipse((36, 36, 220, 220), fill=(62, 32, 28))
    return image


class _Boxes:
    def __init__(self, xyxy):
        import torch

        self.xyxy = torch.tensor([xyxy], dtype=torch.float32)
        self.conf = torch.tensor([0.9], dtype=torch.float32)

    def __len__(self):
        return len(self.xyxy)


class _ROI:
    def __init__(self, *, fail: bool):
        self.fail = fail
        self.input = None

    def __call__(self, image, **_kwargs):
        self.input = image.copy()
        if self.fail:
            raise RuntimeError("controlled ROI failure")
        return [SimpleNamespace(boxes=_Boxes((0, 0, image.shape[1], image.shape[0])))]


class _Engine:
    def __init__(self):
        self.preprocessed = None

    def preprocess_image(self, image):
        self.preprocessed = image.copy()
        return image

    @staticmethod
    def run_sahi_inference(_image, model, _image_size, _overlap):
        model.received_inputs.append(_image.copy())
        if model.label == "MA":
            return [{"bbox": [0, 100, 10, 110], "score": 0.9}]
        return [{"bbox": [100, 100, 120, 120], "score": 0.9}]

    @staticmethod
    def _majority_voting(boxes, scores, _labels, **_kwargs):
        assert len(boxes) == 5
        return boxes[0], scores[0], [0] * len(scores[0])

    @staticmethod
    def weighted_boxes_fusion(boxes, scores, _labels, **_kwargs):
        return boxes[0], scores[0], [0] * len(scores[0])

    @staticmethod
    def apply_inter_class_nms(predictions, **_kwargs):
        return predictions


class _DetectionModel:
    def __init__(self, label):
        self.label = label
        self.confidence_threshold = 0.0
        self.last_input = None
        self.received_inputs = []

    def __call__(self, image, **_kwargs):
        self.last_input = image.copy()
        if self.label == "MA":
            box = (0, 100, 10, 110)
        else:
            box = (100, 100, 120, 120)
        return [SimpleNamespace(boxes=_Boxes(box))]


class _Config:
    def get_lesion_config(self, _label):
        return SimpleNamespace(get_val_best_conf=lambda _fold: 0.1)


def _ready_provider(*, roi_failure: bool):
    torch = pytest.importorskip("torch")
    from dr_support.providers.prism import PRISM

    del torch
    provider = PRISM(allow_cpu_fallback=True)
    provider.loaded = True
    provider.assets_verified = True
    provider.device = "cpu"
    provider.hashes = {}
    provider.engine = _Engine()
    provider.config = _Config()
    provider.roi = _ROI(fail=roi_failure)
    provider.models = {
        label: [_DetectionModel(label) for _ in range(5)]
        for label in ("MA", "HE", "EX", "SE")
    }
    return provider


def _bridge_image(image: Image.Image):
    from dr_support.images import BridgeImage

    stream = io.BytesIO()
    image.save(stream, format="PNG")
    raw = stream.getvalue()
    return BridgeImage(
        image_id="SYNTH_UWF_001",
        data=raw,
        source_type="SYNTHETIC",
        source="generated synthetic UWF fixture",
        modality="UWF",
        filename="SYNTH_UWF_001.png",
        media_type="image/png",
        source_origin="SYNTHETIC",
    )


def _request():
    from dr_support.contracts import InferenceRequest

    return InferenceRequest(image_id="SYNTH_UWF_001", modality="UWF", model_id="prism-dr-5fold")


def test_prepared_path_uses_trusted_mask_and_keeps_edge_detection(monkeypatch):
    import dr_support.imaging.uwf_white_rim_fov as fov_module
    from dr_support.contracts import PrismProcessingEvidence
    from dr_support.imaging.uwf_white_rim_fov import detect_white_rim_fov

    source = _synthetic_uwf(white_rim=True)
    evidence = detect_white_rim_fov(source)
    assert evidence.status.value == "READY"
    monkeypatch.setattr(fov_module, "detect_white_rim_fov", lambda _source: evidence)
    provider = _ready_provider(roi_failure=False)

    result = provider.infer(_request(), _bridge_image(source))

    assert result.state == "AI_SUGGESTION"
    assert len(result.lesions) == 4
    assert provider.roi.input[128, 30].tolist() == [0, 0, 0]
    assert provider.roi.input[128, 128].tolist() != [0, 0, 0]
    # Bind mask application through the exact provider boundary: native ROI
    # receives the masked RGB converted to BGR, preprocessing receives that
    # same full-frame input, and every lesion model sees the preprocessed crop.
    assert np.array_equal(provider.engine.preprocessed, provider.roi.input)
    assert all(
        all(np.array_equal(image, provider.engine.preprocessed) for image in model.received_inputs)
        if model.label != "SE" else np.array_equal(model.last_input, provider.engine.preprocessed)
        for models in provider.models.values()
        for model in models
    )
    assert provider.last_processing_evidence["processing_mode"] == "PREPARED"
    assert provider.last_processing_evidence["fov_used_for_model_input"] is True
    assert len(provider.last_processing_evidence["raw_boundary_classes"]) == len(result.lesions)
    assert provider.last_processing_evidence["raw_boundary_classes"][0] == "OUTSIDE_ANALYSIS_FIELD"
    assert provider.last_processing_evidence["analysis_field"]["used_for_model_input"] is True
    assert provider.last_processing_evidence["analysis_field"]["field_mask_png_base64"]
    PrismProcessingEvidence.model_validate(provider.last_processing_evidence)


def test_uncertain_fov_falls_back_to_original_without_boundary_claim(monkeypatch):
    import dr_support.imaging.uwf_white_rim_fov as fov_module
    from dr_support.imaging.uwf_white_rim_fov import detect_white_rim_fov

    source = _synthetic_uwf(white_rim=False)
    evidence = detect_white_rim_fov(source)
    assert evidence.status.value == "UNCERTAIN"
    monkeypatch.setattr(fov_module, "detect_white_rim_fov", lambda _source: evidence)
    provider = _ready_provider(roi_failure=False)

    result = provider.infer(_request(), _bridge_image(source))

    assert result.state == "AI_SUGGESTION"
    assert provider.last_processing_evidence["processing_mode"] == "FALLBACK"
    assert provider.last_processing_evidence["fov_used_for_model_input"] is False
    assert provider.last_processing_evidence["analysis_field"] is None
    assert set(provider.last_processing_evidence["raw_boundary_classes"]) == {None}
    assert np.array_equal(provider.roi.input, np.asarray(source)[:, :, ::-1])
    assert np.array_equal(provider.engine.preprocessed, np.asarray(source)[:, :, ::-1])


def test_native_roi_failure_runs_full_frame_original_fallback(monkeypatch):
    import dr_support.imaging.uwf_white_rim_fov as fov_module
    from dr_support.imaging.uwf_white_rim_fov import detect_white_rim_fov

    source = _synthetic_uwf(white_rim=False)
    evidence = detect_white_rim_fov(source)
    monkeypatch.setattr(fov_module, "detect_white_rim_fov", lambda _source: evidence)
    provider = _ready_provider(roi_failure=True)

    result = provider.infer(_request(), _bridge_image(source))

    assert result.state == "AI_SUGGESTION"
    assert len(result.lesions) == 4
    assert provider.last_processing_evidence["processing_mode"] == "FALLBACK"
    assert provider.last_processing_evidence["native_roi_status"] == "FAILED"
    assert provider.last_processing_evidence["native_roi_failure_code"] == "RuntimeError"
    assert provider.last_processing_evidence["fov_used_for_model_input"] is False
    assert provider.last_processing_evidence["raw_boundary_classes"] == [None] * len(result.lesions)
    assert np.array_equal(provider.engine.preprocessed, np.asarray(source)[:, :, ::-1])
