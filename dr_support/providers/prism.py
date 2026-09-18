"""PRISM-DR released 5-fold pipeline, with original-image pixel coordinates.

The adapter is GPU-ready: it accepts an ``allow_cpu_fallback`` flag and resolves
the runtime device via :func:`dr_support.runtime.resolve_device`. ROI YOLO,
each fold model, and SAHI ``AutoDetectionModel`` are all placed on the resolved
device. Inference tensors are moved to the same device.

Memory strategy: with 4 lesion classes × 5 folds = 20 model instances plus the
ROI cropper on the GPU, a T4 small (16 GB) is sufficient for the released
checkpoint sizes (~6 MB each). The api-level :class:`threading.RLock` ensures
only one inference call runs at a time, so peak activation memory stays
bounded by a single forward pass. After each ``infer`` call we release any
intermediate CUDA tensors the autograd engine might still be holding.
"""
import importlib
import io
import json
import os
import sys
import types
from pathlib import Path

from dr_support.contracts import LABELS, Lesion, LesionResult, Provenance
from dr_support.runtime import resolve_device, runtime_snapshot
from .assets import verify_source, verify_weight

REVISION = '79637440a535e4f8118e939d3787121f82180125'
PREPROCESSING = 'ROI cropper; green median5 CLAHE2 grid8; MA/HE/EX tile1280 overlap.25; SE full'


class PRISM:
    task = 'lesion-roi'
    model_id = 'prism-dr-5fold'

    def __init__(self, *, allow_cpu_fallback: bool | None = None):
        """Construct the PRISM-DR adapter.

        ``allow_cpu_fallback`` mirrors :class:`RETFound`; the production
        model_api factory passes ``False`` so misconfigured GPU hosts fail at
        the first inference call instead of silently degrading to CPU.
        """
        self.loaded = False
        self.hashes = {}
        self.device = None
        self._allow_cpu_fallback = allow_cpu_fallback

    def _resolve_device(self):
        return resolve_device(allow_cpu_fallback=self._allow_cpu_fallback)

    def metadata(self):
        configured = all(os.environ.get(k) for k in ('PRISM_SOURCE', 'PRISM_WEIGHTS'))
        snap = runtime_snapshot()
        warnings = [
            'Research Bridge; not scientific R2/R3',
            'PRISM MIT; Ultralytics AGPL-3.0; source weight release: academic use',
            'HRF scale differs from IDRiD; inter-lesion size rule unvalidated on HRF',
            'Raw detections are retained; clinician overlay/CVAT pre-labels use a separate bounded review policy',
        ]
        requested = snap.requested_device
        effective = snap.effective_device
        if requested.startswith('cuda') and effective != requested:
            warnings.append(
                f"INFERENCE_DEVICE={requested} requested but unavailable; "
                f'effective_device={effective}.'
            )
        return {
            'model_id': self.model_id,
            'task': self.task,
            'revision': REVISION,
            'status': 'LOADED' if self.loaded else (
                'CONFIGURED_NOT_VERIFIED' if configured else 'ASSET_REQUIRED'
            ),
            'modalities': ['CFP'],
            'requested_device': requested,
            'effective_device': self.device or effective,
            'cuda_available': snap.cuda_available,
            'warnings': warnings,
            'preprocessing': PREPROCESSING,
        }

    def load(self):
        from ultralytics import YOLO
        from sahi import AutoDetectionModel
        device = self._resolve_device()
        source = verify_source(os.environ['PRISM_SOURCE'], REVISION)
        root = Path(os.environ['PRISM_WEIGHTS'])
        lock = json.loads((Path(__file__).with_name('prism_assets.json')).read_text(encoding='utf-8'))
        self.hashes = lock['weights']
        for path, digest in self.hashes.items():
            verify_weight(root / path, digest)
        # Namespace isolates upstream relative imports from other providers.
        package = types.ModuleType('_drsupport_prism')
        package.__path__ = [str(source / 'evaluation/src')]
        sys.modules['_drsupport_prism'] = package
        self.engine = importlib.import_module('_drsupport_prism.image_level_evaluation')
        config_module = importlib.import_module('_drsupport_prism.config')
        self.config = config_module.Config(str(source / 'evaluation/configs/inference.yaml'))
        # ROI cropper is a single ultralytics YOLO; place it on the resolved
        # device explicitly because ``YOLO.predict`` takes ``device=`` per
        # call and we want the model's parameters to live on the GPU.
        self.roi = YOLO(str(root / 'ROI_Cropper_Results/yolov8n_roi/weights/best.pt'))
        try:
            self.roi.to(device)
        except Exception:
            # Ultralytics models without parameters (rare) or devices that
            # don't accept ``.to``; fall back to per-call ``device=`` argument.
            pass
        self.models = {}
        for label in LABELS:
            cfg = self.config.get_lesion_config(label)
            self.models[label] = []
            for fold in range(1, 6):
                path = str(root / cfg.model_dir / f'fold_{fold}/weights/best.pt')
                if label == 'SE':
                    model = YOLO(path)
                    try:
                        model.to(device)
                    except Exception:
                        pass
                else:
                    # SAHI's ``AutoDetectionModel`` accepts a device string at
                    # construction; the underlying ultralytics model is moved
                    # to that device internally.
                    model = AutoDetectionModel.from_pretrained(
                        model_type='ultralytics',
                        model_path=path,
                        confidence_threshold=cfg.get_val_best_conf(fold),
                        device=str(device),
                        image_size=1280,
                    )
                self.models[label].append(model)
        self.device = device
        self.loaded = True

    def infer(self, request, image):
        import numpy as np
        from PIL import Image
        if request.modality != 'CFP':
            return self.result(request, image, [], 'UNSUPPORTED')
        if not self.loaded:
            self.load()
        device = self.device or self._resolve_device()
        try:
            with Image.open(io.BytesIO(image.data)) as pil:
                original = np.array(pil.convert('RGB'))[:, :, ::-1].copy()
            height, width = original.shape[:2]
            # ROI cropper: pass ``device=str(device)`` so the prediction runs
            # on the same runtime as the model parameters; the ``.cpu()`` on
            # the bounding-box tensor is required because SAHI expects numpy
            # arrays regardless of where inference ran.
            roi = self.roi(original, device=str(device), verbose=False)[0].boxes
            if roi is None or len(roi) == 0:
                raise RuntimeError('ROI cropper found no field; no silent crop fallback')
            x1, y1, x2, y2 = roi.xyxy[0].cpu().numpy().astype(int)
            x1, y1, x2, y2 = max(0, x1), max(0, y1), min(width, x2), min(height, y2)
            if x2 <= x1 or y2 <= y1:
                raise RuntimeError('Invalid crop')
            crop = self.engine.preprocess_image(original[y1:y2, x1:x2])
            h, w = crop.shape[:2]
            predictions = {}
            thresholds = json.loads(os.environ.get('PRISM_THRESHOLDS', '{}'))
            if set(thresholds) - set(LABELS) or any(not 0 <= float(v) <= 1 for v in thresholds.values()):
                raise ValueError('Invalid source-label thresholds')
            for label, models in self.models.items():
                cfg = self.config.get_lesion_config(label)
                boxes, scores, labels = [], [], []
                for fold, model in enumerate(models, 1):
                    threshold = float(thresholds.get(label, cfg.get_val_best_conf(fold)))
                    if label == 'SE':
                        results = model(crop, imgsz=1280, conf=threshold, iou=.5, max_det=10000,
                                        device=str(device), verbose=False)[0].boxes
                        raw = [{'bbox': b, 'score': s} for b, s in zip(
                            results.xyxy.cpu().tolist(), results.conf.cpu().tolist())] if results is not None else []
                    else:
                        model.confidence_threshold = threshold
                        raw = self.engine.run_sahi_inference(crop, model, 1280, .25)
                    raw = [p for p in raw if p['score'] >= threshold]
                    boxes.append([[max(0., min(1., b / (w if i % 2 == 0 else h)))
                                   for i, b in enumerate(p['bbox'])] for p in raw])
                    scores.append([p['score'] for p in raw]); labels.append([0] * len(raw))
                if label == 'SE':
                    merged, confidence, _ = self.engine.weighted_boxes_fusion(
                        boxes, scores, labels, iou_thr=.5, skip_box_thr=.01)
                else:
                    merged, confidence, _ = self.engine._majority_voting(boxes, scores, labels, iou_thr=.5, vote_thr=3)
                predictions[label] = [{'bbox': [b[0]*w, b[1]*h, b[2]*w, b[3]*h], 'score': float(s), 'class_id': 0}
                                      for b, s in zip(merged, confidence)]
            predictions = self.engine.apply_inter_class_nms(predictions, iou_threshold=.5, use_delta_conf=False)
            lesions = []
            for label, objects in predictions.items():
                for obj in objects:
                    b = obj['bbox']
                    rectangle = (b[0]+x1, b[1]+y1, b[2]+x1, b[3]+y1)
                    if rectangle[0] < rectangle[2] and rectangle[1] < rectangle[3]:
                        lesions.append(Lesion(source_label=label, canonical_label=LABELS[label],
                                              rectangle=rectangle, score=obj['score']))
            return self.result(request, image, lesions)
        finally:
            # Release any intermediate CUDA tensors the autograd engine might
            # still be holding after the inference loop. We deliberately do
            # this even when ``device.type != 'cuda'`` because the call is a
            # cheap no-op on CPU and keeps the cleanup path uniform.
            self._release_cuda_memory(device)

    @staticmethod
    def _release_cuda_memory(device) -> None:
        try:
            import torch
        except Exception:
            return
        if not str(device).startswith('cuda'):
            return
        try:
            torch.cuda.empty_cache()
        except Exception:
            # ``empty_cache`` is best-effort; never let cleanup mask the
            # original inference result or its error.
            pass

    def result(self, request, image, lesions, state='AI_SUGGESTION'):
        return LesionResult(model_id=self.model_id, model_version=REVISION, modality=request.modality,
            width=image.size[0], height=image.size[1], lesions=lesions, state=state,
            warnings=self.metadata()['warnings'] + ['Empty detections do not prove absence of lesions'],
            provenance=Provenance(image_sha256=image.sha256, source_type=image.source_type,
                source_revision=REVISION, checkpoint_sha256=self.hashes,
                preprocessing=PREPROCESSING + '; thresholds=' + os.environ.get('PRISM_THRESHOLDS', 'upstream-validation')))
