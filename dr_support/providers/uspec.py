"""Lazy, UWF-only USPEC provider for public/synthetic engineering inference."""

from __future__ import annotations

import io
import math
import os
from pathlib import Path

from dr_support.contracts import GlobalResult, Provenance
from dr_support.models.uspec_artifact import (
    EXPECTED,
    CAPABILITY_ID,
    MODEL_ID,
    MODEL_VERSION,
    PREPROCESSING,
    RESEARCH_MODEL_ID,
    REPRESENTATION,
    SOURCE_REVISION,
    TRANSFORM,
)
from dr_support.runtime import DeviceUnavailable, resolve_device, runtime_snapshot


class USPEC:
    task = "global"
    model_id = MODEL_ID
    capability_id = CAPABILITY_ID
    model_version = MODEL_VERSION
    representation = REPRESENTATION
    transform = TRANSFORM

    def __init__(self, *, allow_cpu_fallback: bool = False):
        self.model = None
        self.device = None
        self.observed_artifact = None
        self.last_inference_ms = None
        self._allow_cpu_fallback = allow_cpu_fallback
        self._directory = os.environ.get("USPEC_MODEL_DIR")
        self._load_enabled = os.environ.get("USPEC_ENABLE_CANDIDATE_LOAD") == "1"
        artifact_dir = Path(self._directory) if self._directory else None
        has_artifact = bool(
            artifact_dir
            and artifact_dir.is_dir()
            and all(
                (artifact_dir / filename).is_file()
                and not (artifact_dir / filename).is_symlink()
                for filename in ("manifest.json", "grading_state.pt")
            )
        )
        self._status = (
            "NOT_LOADED"
            if has_artifact
            else "ASSET_REQUIRED"
        )

    def metadata(self) -> dict:
        snapshot = runtime_snapshot()
        return {
            "model_id": self.model_id,
            "research_model_id": RESEARCH_MODEL_ID,
            "provider_id": "uspec",
            "capability_id": self.capability_id,
            "task": self.task,
            "revision": MODEL_VERSION,
            "artifact_digest": EXPECTED.sha256,
            "status": "LOADED" if self.model is not None else self._status,
            "modalities": ["UWF"],
            "class_order": [0, 1, 2, 3, 4],
            "requested_device": snapshot.requested_device,
            "effective_device": self.device or snapshot.effective_device,
            "cuda_available": snapshot.cuda_available,
            "preprocessing": PREPROCESSING,
            "preprocessing_version": PREPROCESSING,
            "input_representation": REPRESENTATION,
            "postprocessing_version": "softmax-argmax-5-v1",
            "explanation_status": "UNAVAILABLE",
            "release_status": "DISABLED",
            "runtime_qualification": "NEEDS_QUALIFICATION",
            "rights_status": "UNVERIFIED",
            "clinical_validation_status": "NOT_ESTABLISHED",
            "warnings": [
                "USPEC research candidate; runtime qualification is pending.",
                "Production rights are unverified and clinical validation is not established.",
                "Raw model scores are not calibrated clinical probabilities.",
                "Model attention is not exposed as lesion localization; clinician review remains authoritative.",
            ],
        }

    def load(self) -> None:
        if self.model is not None:
            return
        if not self._directory:
            self._status = "ASSET_REQUIRED"
            raise RuntimeError("USPEC artifact is not configured")
        if not self._load_enabled:
            raise RuntimeError("USPEC candidate loading is disabled")
        requested_device = (os.environ.get("INFERENCE_DEVICE") or "").strip().lower()
        if not self._allow_cpu_fallback and not requested_device.startswith("cuda"):
            raise DeviceUnavailable("USPEC production inference requires CUDA")

        device = resolve_device(allow_cpu_fallback=self._allow_cpu_fallback)
        try:
            from dr_support.models.uspec_mil import load_verified_model

            model, observed = load_verified_model(self._directory, device=device)
        except Exception:
            self.model = None
            self.device = None
            self.observed_artifact = None
            self._status = "BLOCKED_ARTIFACT"
            raise RuntimeError("USPEC verified load failed") from None

        self.model = model
        self.device = device
        self.observed_artifact = observed
        self._status = "LOADED"

    def _result(
        self,
        image,
        modality: str,
        scores: list[float] | None = None,
        *,
        mask_status: str | None = None,
    ) -> GlobalResult:
        preprocessing = "none"
        checkpoint_sha256 = {}
        if scores is not None:
            preprocessing = PREPROCESSING
            if mask_status:
                preprocessing = f"{PREPROCESSING}; mask_status={mask_status}"
            checkpoint_sha256 = {"grading_state.pt": EXPECTED.sha256}
        provenance = Provenance(
            image_sha256=image.sha256,
            source_type=image.source_type,
            source_revision=SOURCE_REVISION,
            preprocessing=preprocessing,
            checkpoint_sha256=checkpoint_sha256,
        )
        common = {
            "model_id": self.model_id,
            "model_version": MODEL_VERSION,
            "modality": modality,
            "warnings": self.metadata()["warnings"],
            "provenance": provenance,
        }
        if scores is None:
            return GlobalResult(**common, state="UNSUPPORTED")
        if (
            len(scores) != 5
            or any(not math.isfinite(score) or not 0 <= score <= 1 for score in scores)
            or not math.isclose(sum(scores), 1, abs_tol=1e-5)
        ):
            raise ValueError("USPEC returned invalid five-class scores")
        grade = max(range(5), key=scores.__getitem__)
        return GlobalResult(
            **common,
            state="AI_SUGGESTION",
            grade=grade,
            probabilities=scores,
            confidence=scores[grade],
        )

    def infer(self, request, image) -> GlobalResult:
        if image.source_type not in {"PUBLIC", "SYNTHETIC"}:
            raise ValueError("USPEC source origin is blocked")
        if request.model_id != self.model_id or request.modality != image.modality:
            raise ValueError("USPEC invocation identity mismatch")
        if request.modality != "UWF":
            return self._result(image, request.modality)
        if self.model is None:
            self.load()

        import torch
        from PIL import Image

        from dr_support.imaging.uspec_preprocessing import normalize_patches, prepare_patches

        with Image.open(io.BytesIO(image.data)) as decoded:
            if getattr(decoded, "n_frames", 1) != 1:
                raise ValueError("USPEC requires a single-frame image")
            if decoded.size != image.size:
                raise ValueError("USPEC image dimensions do not match the request")
            decoded.load()
            original_rgb = decoded.convert("RGB")
            patches, preprocessing = prepare_patches(original_rgb)

        encoded = []
        with torch.inference_mode():
            for start in range(0, 49, 4):
                pixels = normalize_patches(patches[start:start + 4]).to(self.device)
                features = self.model.encoder(pixel_values=pixels).last_hidden_state[:, 0, :]
                encoded.append(features)
            hidden = torch.cat(encoded).unsqueeze(0)
            scores = self.model.aggregate(hidden).softmax(dim=-1)[0].float().cpu().tolist()
        return self._result(
            image,
            request.modality,
            scores,
            mask_status=preprocessing["mask_status"],
        )
