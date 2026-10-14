"""Locked PRISM-DR five-fold lesion assistance with restricted checkpoint loading.

The provider retains the published CFP pipeline and adds a clearly experimental
UWF adaptation. All checkpoints are loaded with ``weights_only=True`` and the
explicit safe-global allowlist in :mod:`prism_safe_loader`; neither Ultralytics
nor SAHI receives a checkpoint path.
"""

from __future__ import annotations

import base64
import importlib
import io
import json
import os
import sys
import time
import types
from pathlib import Path

from dr_support.contracts import LABELS, Lesion, LesionResult, Provenance
from dr_support.runtime import resolve_device, runtime_snapshot
from .assets import verify_source, verify_weight
from .prism_safe_loader import safe_load_detection_model

REVISION = "79637440a535e4f8118e939d3787121f82180125"
PREPROCESSING = "ROI cropper; green median5 CLAHE2 grid8; MA/HE/EX tile1280 overlap.25; SE full"


class _SafeYoloInference:
    """Small YOLO-call-compatible wrapper around an already loaded module.

    SAHI's public ``model=`` constructor expects a callable model object. This
    adapter exposes that protocol while delegating to Ultralytics' standard
    predictor initialized directly from the safely loaded ``nn.Module``.
    It never opens the original checkpoint path.
    """

    def __init__(self, module, *, device: str, image_size: int, confidence: float):
        import torch
        from ultralytics.models.yolo.detect.predict import DetectionPredictor

        self.model = module.to(device).eval()
        self.names = self.model.names
        overrides = {
            "task": "detect",
            "mode": "predict",
            "model": "",
            "data": None,
            "imgsz": image_size,
            "conf": confidence,
            # Preserve Ultralytics predict defaults used by the legacy ROI
            # cropper and by SAHI for each tile; SE passes its explicit values.
            "iou": 0.7,
            "max_det": 3000,
            "device": device,
            "half": False,
            "save": False,
            "verbose": False,
        }
        self.predictor = DetectionPredictor(overrides=overrides)
        # Ultralytics 8.4.8's in-memory module path does not reopen a weight
        # file; setup_model wraps this module in AutoBackend directly.
        self.predictor.setup_model(model=self.model, verbose=False)
        if not isinstance(self.predictor.model.device, torch.device):
            raise RuntimeError("Safe-loaded PRISM predictor did not expose a Torch device")
        if self.predictor.model.device.type != torch.device(device).type:
            raise RuntimeError("Safe-loaded PRISM predictor was placed on the wrong device")

    def __call__(self, source, **kwargs):
        # SAHI passes inference settings to the model callable. Put those
        # values on the predictor's config rather than forwarding them through
        # ``nn.Module.forward`` (which would change model semantics).
        args = self.predictor.args
        for name in ("conf", "iou", "max_det", "imgsz"):
            value = kwargs.get(name)
            if value is not None:
                setattr(args, name, value)
        return self.predictor(source)


class PRISM:
    task = "lesion-roi"
    model_id = "prism-dr-5fold"
    capability_id = "core_lesion_localization"
    model_version = REVISION

    def __init__(self, *, allow_cpu_fallback: bool | None = None):
        self.loaded = False
        self.assets_verified = False
        self.hashes: dict[str, str] = {}
        self.device = None
        self.load_seconds: float | None = None
        self.vram_after_load: dict[str, int] = {}
        self.safe_load_reports: dict[str, dict] = {}
        self.last_processing_evidence: dict | None = None
        self.last_inference_ms: float | None = None
        self._allow_cpu_fallback = allow_cpu_fallback

    def _resolve_device(self):
        return resolve_device(allow_cpu_fallback=self._allow_cpu_fallback)

    def metadata(self):
        configured = all(os.environ.get(key) for key in ("PRISM_SOURCE", "PRISM_WEIGHTS"))
        snapshot = runtime_snapshot()
        warnings = [
            "Research model; no scientific performance claim.",
            "PRISM is trained on CFP; UWF use is EXPERIMENTAL and NOT_VALIDATED_FOR_UWF.",
            "PRISM MIT; Ultralytics AGPL-3.0; released weights are restricted to academic/research use.",
            "Raw detections are retained; empty detections do not prove absence of lesions.",
        ]
        requested = snapshot.requested_device
        effective = self.device or snapshot.effective_device
        if requested.startswith("cuda") and effective != requested:
            warnings.append(f"INFERENCE_DEVICE={requested} requested but unavailable; effective_device={effective}.")
        status = "LOADED" if self.loaded else ("CONFIGURED_NOT_VERIFIED" if configured else "ASSET_REQUIRED")
        if configured and self.assets_verified and not self.loaded:
            status = "QUALIFIED_NOT_LOADED"
        if getattr(self, "load_failed", False):
            status = "LOAD_FAILED"
        return {
            "model_id": self.model_id,
            "provider_id": "prism",
            "capability_id": self.capability_id,
            "task": self.task,
            "revision": REVISION,
            "model_version": REVISION,
            "status": status,
            "modalities": ["CFP", "UWF"],
            "supported_modalities": ["CFP", "UWF"],
            "trained_domain": "CFP",
            "uwf_use": "EXPERIMENTAL",
            "domain_status": "EXPERIMENTAL_UWF_ADAPTATION",
            "clinical_validation_status": "NOT_VALIDATED_FOR_UWF",
            "rights_status": "ACADEMIC_USE_REVIEW_REQUIRED",
            "release_status": "RESEARCH_ONLY",
            "production_authorization": "NOT_AUTHORIZED",
            "runtime_qualification": "ENGINEERING_QUALIFIED" if self.assets_verified or self.loaded else "PENDING_LOAD",
            "requested_device": requested,
            "effective_device": effective,
            "cuda_available": snapshot.cuda_available,
            "warnings": warnings,
            "preprocessing": PREPROCESSING,
            "preprocessing_version": "prism-legacy-cfp-plus-experimental-uwf-v1",
            "safe_checkpoint_loading": "torch.load(weights_only=True); explicit torch.serialization.safe_globals",
            "load_seconds": self.load_seconds,
            "vram_after_load": dict(self.vram_after_load),
            "last_inference_ms": self.last_inference_ms,
        }

    @staticmethod
    def _safe_yolo(module, *, device: str, image_size: int, confidence: float):
        return _SafeYoloInference(
            module,
            device=str(device),
            image_size=image_size,
            confidence=confidence,
        )

    @staticmethod
    def _sahi_model(safe_yolo, *, device: str, confidence: float, image_size: int):
        from sahi import AutoDetectionModel

        # Passing a pre-instantiated model is SAHI's supported in-memory path.
        # model_path remains None, so no checkpoint deserialization is possible.
        return AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model=safe_yolo,
            model_path=None,
            confidence_threshold=confidence,
            device=str(device),
            image_size=image_size,
            load_at_init=True,
        )

    def load(self):
        device = self._resolve_device()
        source = verify_source(os.environ["PRISM_SOURCE"], REVISION)
        weights_root = Path(os.environ["PRISM_WEIGHTS"])
        lock_path = Path(__file__).with_name("prism_assets.json")
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        self.hashes = lock["weights"]
        for relative_path, digest in self.hashes.items():
            verify_weight(weights_root / relative_path, digest)

        # Import the exact locked evaluation source under a private package
        # namespace; the checkpoint files are only read by safe_load_detection_model.
        package = types.ModuleType("_drsupport_prism")
        package.__path__ = [str(source / "evaluation/src")]
        sys.modules["_drsupport_prism"] = package
        self.engine = importlib.import_module("_drsupport_prism.image_level_evaluation")
        config_module = importlib.import_module("_drsupport_prism.config")
        self.config = config_module.Config(str(source / "evaluation/configs/inference.yaml"))

        started = time.perf_counter()
        roi_relative = "ROI_Cropper_Results/yolov8n_roi/weights/best.pt"
        roi_module, self.safe_load_reports[roi_relative] = safe_load_detection_model(weights_root / roi_relative)
        roi_yolo = self._safe_yolo(roi_module, device=device, image_size=640, confidence=0.25)
        self.roi = roi_yolo

        self.models = {}
        self.sahi_models = {}
        for label in LABELS:
            cfg = self.config.get_lesion_config(label)
            self.models[label] = []
            if label != "SE":
                self.sahi_models[label] = []
            for fold in range(1, 6):
                relative = str(Path(cfg.model_dir) / f"fold_{fold}/weights/best.pt")
                model_module, report = safe_load_detection_model(weights_root / relative)
                self.safe_load_reports[relative] = report
                confidence = float(cfg.get_val_best_conf(fold))
                safe_yolo = self._safe_yolo(
                    model_module,
                    device=device,
                    image_size=1280,
                    confidence=confidence,
                )
                if label == "SE":
                    self.models[label].append(safe_yolo)
                else:
                    detection_model = self._sahi_model(
                        safe_yolo,
                        device=str(device),
                        confidence=confidence,
                        image_size=1280,
                    )
                    self.models[label].append(detection_model)
                    self.sahi_models[label].append(detection_model)

        self.device = device
        self.loaded = True
        self.load_failed = False
        self.assets_verified = True
        self.load_seconds = time.perf_counter() - started
        try:
            import torch
            if str(device).startswith("cuda"):
                torch.cuda.synchronize(device)
                self.vram_after_load = {
                    "allocated_bytes": int(torch.cuda.memory_allocated(device)),
                    "reserved_bytes": int(torch.cuda.memory_reserved(device)),
                }
        except Exception:
            self.vram_after_load = {}

    @staticmethod
    def _fov_evidence(fov, *, used_for_model_input: bool) -> dict:
        evidence = {
            "status": str(fov.status),
            "mask_version": fov.mask_version,
            "mask_sha256": fov.mask_sha256,
            "source_rgb_sha256": fov.source_rgb_sha256,
            "image_width": fov.image_width,
            "image_height": fov.image_height,
            "boundary_confidence": fov.boundary_confidence,
            "excluded_fraction": fov.excluded_fraction,
            "boundary": [list(point) for point in fov.boundary],
            "used_for_model_input": used_for_model_input,
        }
        if used_for_model_input and fov.field_mask is not None:
            mask_stream = io.BytesIO()
            fov.field_mask.save(mask_stream, format="PNG", optimize=True)
            evidence["field_mask_png_base64"] = base64.b64encode(mask_stream.getvalue()).decode("ascii")
        return evidence

    @staticmethod
    def _native_roi_box(results, width: int, height: int):
        if not results or getattr(results[0], "boxes", None) is None or len(results[0].boxes) == 0:
            return None
        box = results[0].boxes.xyxy[0].detach().float().cpu().numpy().tolist()
        x1, y1, x2, y2 = (int(value) for value in box)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(width, x2), min(height, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2

    def infer(self, request, image):
        """Run a provider call and release unused CUDA cache on every outcome."""
        try:
            return self._infer_loaded(request, image)
        finally:
            self._release_cuda_memory(self.device)

    def _infer_loaded(self, request, image):
        import numpy as np
        from PIL import Image

        self.last_processing_evidence = None
        if request.modality not in {"CFP", "UWF"}:
            return self.result(request, image, [], "UNSUPPORTED")
        if not self.loaded:
            try:
                self.load()
            except Exception:
                self.load_failed = True
                raise
        device = self.device or self._resolve_device()

        # Decode Original once. UWF FOV evidence is evaluated against these
        # exact RGB pixels, and any accepted mask is applied to a detached copy.
        with Image.open(io.BytesIO(image.data)) as opened:
            if getattr(opened, "n_frames", 1) != 1:
                raise ValueError("PRISM requires a single-frame image")
            opened.load()
            original_rgb_pil = opened.convert("RGB")
        if original_rgb_pil.size != image.size:
            raise ValueError("Decoded PRISM source dimensions do not match the request")
        original_rgb = np.asarray(original_rgb_pil, dtype=np.uint8).copy()
        original_bgr = np.ascontiguousarray(original_rgb[:, :, ::-1])
        height, width = original_bgr.shape[:2]

        fov = None
        fov_prepared_rgb = None
        fov_status = "NOT_APPLICABLE"
        fov_reason = None
        if request.modality == "UWF":
            try:
                from dr_support.imaging.uwf_white_rim_fov import (
                    FovStatus,
                    detect_white_rim_fov,
                    prepare_prism_uwf_image,
                )
                fov = detect_white_rim_fov(original_rgb_pil)
                fov_status = str(fov.status)
                fov_reason = fov.reason_code
                if fov.status is FovStatus.READY:
                    try:
                        fov_prepared_rgb = prepare_prism_uwf_image(original_rgb_pil, fov).masked_rgb
                    except Exception:
                        # Broken/stale external evidence is not allowed to
                        # disable inference or authorize a mask.
                        fov_prepared_rgb = None
                        fov_status = "UNAVAILABLE"
                        fov_reason = "FOV_EVIDENCE_INVALID"
            except Exception:
                fov = None
                fov_status = "UNAVAILABLE"
                fov_reason = "FOV_DETECTOR_UNAVAILABLE"

        roi_input_rgb = fov_prepared_rgb if fov_prepared_rgb is not None else original_rgb_pil
        roi_input_bgr = np.ascontiguousarray(np.asarray(roi_input_rgb, dtype=np.uint8)[:, :, ::-1])
        native_roi = None
        roi_error = None
        try:
            roi_results = self.roi(roi_input_bgr, verbose=False)
            native_roi = self._native_roi_box(roi_results, width, height)
            if native_roi is None:
                roi_error = "NO_VALID_NATIVE_ROI"
        except Exception as exc:
            # ROI failure alone is recoverable. The fatal inference boundary is
            # the later lesion-model pass, not this optional crop proposal.
            roi_error = type(exc).__name__

        is_uwf = request.modality == "UWF"
        if native_roi is not None:
            x1, y1, x2, y2 = native_roi
            crop_input = roi_input_bgr[y1:y2, x1:x2]
            processing_mode = "PREPARED" if is_uwf and fov_prepared_rgb is not None else (
                "FALLBACK" if is_uwf else "LEGACY"
            )
        else:
            # The ROI cropper is non-fatal. If it fails, explicitly bypass it
            # and run the same source preprocessing on full-frame Original RGB.
            x1 = y1 = 0
            crop_input = original_bgr
            processing_mode = "FALLBACK" if is_uwf else "LEGACY"

        crop = self.engine.preprocess_image(crop_input)
        crop_height, crop_width = crop.shape[:2]
        predictions = {}
        thresholds = json.loads(os.environ.get("PRISM_THRESHOLDS", "{}"))
        if set(thresholds) - set(LABELS) or any(not 0 <= float(value) <= 1 for value in thresholds.values()):
            raise ValueError("Invalid source-label thresholds")
        for label, models in self.models.items():
            cfg = self.config.get_lesion_config(label)
            boxes, scores, labels = [], [], []
            for fold, model in enumerate(models, 1):
                threshold = float(thresholds.get(label, cfg.get_val_best_conf(fold)))
                if label == "SE":
                    results = model(
                        crop,
                        imgsz=1280,
                        conf=threshold,
                        iou=0.5,
                        max_det=10000,
                        device=str(device),
                        verbose=False,
                    )
                    result_boxes = results[0].boxes if results else None
                    raw = (
                        [
                            {"bbox": box, "score": score}
                            for box, score in zip(
                                result_boxes.xyxy.detach().cpu().tolist(),
                                result_boxes.conf.detach().cpu().tolist(),
                            )
                        ]
                        if result_boxes is not None else []
                    )
                else:
                    model.confidence_threshold = threshold
                    raw = self.engine.run_sahi_inference(crop, model, 1280, 0.25)
                raw = [prediction for prediction in raw if prediction["score"] >= threshold]
                boxes.append([
                    [max(0.0, min(1.0, coordinate / (crop_width if index % 2 == 0 else crop_height)))
                     for index, coordinate in enumerate(prediction["bbox"])]
                    for prediction in raw
                ])
                scores.append([prediction["score"] for prediction in raw])
                labels.append([0] * len(raw))
            if label == "SE":
                merged, confidence, _ = self.engine.weighted_boxes_fusion(
                    boxes, scores, labels, iou_thr=0.5, skip_box_thr=0.01,
                )
            else:
                merged, confidence, _ = self.engine._majority_voting(
                    boxes, scores, labels, iou_thr=0.5, vote_thr=3,
                )
            predictions[label] = [
                {
                    "bbox": [box[0] * crop_width, box[1] * crop_height,
                             box[2] * crop_width, box[3] * crop_height],
                    "score": float(score),
                    "class_id": 0,
                }
                for box, score in zip(merged, confidence)
            ]
        predictions = self.engine.apply_inter_class_nms(
            predictions, iou_threshold=0.5, use_delta_conf=False,
        )
        lesions = []
        for label, objects in predictions.items():
            for obj in objects:
                box = obj["bbox"]
                rectangle = (box[0] + x1, box[1] + y1, box[2] + x1, box[3] + y1)
                if rectangle[0] < rectangle[2] and rectangle[1] < rectangle[3]:
                    lesions.append(Lesion(
                        source_label=label,
                        canonical_label=LABELS[label],
                        rectangle=rectangle,
                        score=obj["score"],
                    ))

        raw_boundary_classes: list[str | None] = []
        if fov is not None and fov_status == "READY":
            from dr_support.imaging.uwf_white_rim_fov import classify_prism_box
            for lesion in lesions:
                try:
                    raw_boundary_classes.append(str(classify_prism_box(fov, lesion.rectangle)))
                except Exception:
                    raw_boundary_classes.append(None)
        else:
            raw_boundary_classes = [None] * len(lesions)

        processing = {
            "input_image_sha256": image.sha256,
            "processing_mode": processing_mode,
            "native_roi_status": "SUCCEEDED" if native_roi is not None else "FAILED",
            "native_roi_bbox": list(native_roi) if native_roi is not None else None,
            "native_roi_failure_code": roi_error,
            "external_fov_status": fov_status,
            "external_fov_reason_code": fov_reason,
            "fov_used_for_model_input": bool(processing_mode == "PREPARED"),
            "raw_boundary_classes": raw_boundary_classes,
        }
        if fov is not None and fov_status == "READY":
            processing["analysis_field"] = self._fov_evidence(
                fov,
                used_for_model_input=bool(processing_mode == "PREPARED"),
            )
        else:
            processing["analysis_field"] = None
        self.last_processing_evidence = processing
        return self.result(request, image, lesions, processing=processing)

    @staticmethod
    def _release_cuda_memory(device) -> None:
        try:
            import torch
        except Exception:
            return
        if not str(device).startswith("cuda"):
            return
        try:
            import gc
            gc.collect()
            torch.cuda.empty_cache()
        except Exception:
            pass

    def result(self, request, image, lesions, state="AI_SUGGESTION", *, processing=None):
        preprocessing = PREPROCESSING
        warnings = self.metadata()["warnings"] + ["Empty detections do not prove absence of lesions."]
        if processing is not None:
            preprocessing += f"; processing_mode={processing['processing_mode']}"
            if request.modality == "UWF":
                warnings.append("Experimental PRISM UWF assistance; not validated for UWF.")
        return LesionResult(
            model_id=self.model_id,
            model_version=REVISION,
            modality=request.modality,
            width=image.size[0],
            height=image.size[1],
            lesions=lesions,
            state=state,
            warnings=list(dict.fromkeys(warnings)),
            provenance=Provenance(
                image_sha256=image.sha256,
                source_type=image.source_type,
                checkpoint_sha256=self.hashes,
                preprocessing=preprocessing + "; thresholds=" + os.environ.get("PRISM_THRESHOLDS", "upstream-validation"),
                source_revision=REVISION,
            ),
        )
