"""CPU image-only empirical annotation assist; Original model wire is untouched."""

from copy import deepcopy
import hashlib
import io

import numpy as np
from PIL import Image

from .artifact_generic_v01 import generic_uwf as core
from .artifact_roi_assist import digest, input_binding

EVIDENCE = "GENERIC_IMAGE_ONLY_EMPIRICAL_NOT_CERTIFIED"
REASON = "EMPIRICAL_CORE_CONTAINMENT_CANDIDATE"
SCHEMA = "annotation-assist.image-only-field.v1"


def encoded_png(image):
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


class GenericUwfArtifactProvider:
    """No weight, registry, source file, model result or review needed to prepare."""

    def identity(self):
        return {
            "method_version": core.VERSION,
            "mask_version": "generic-empirical-core-source-pixels.v1",
            "evidence_kind": EVIDENCE,
            "config_sha256": digest(core.PARAMETERS),
        }

    def _prepare(self, image):
        if type(image.data) is not bytes:
            raise ValueError("Immutable source bytes required")
        with Image.open(io.BytesIO(image.data)) as opened:
            if (
                getattr(opened, "n_frames", 1) != 1
                or opened.width * opened.height > 40_000_000
            ):
                raise ValueError("Single bounded source required")
            rgb = np.array(opened.convert("RGB"), dtype=np.uint8, copy=True)
        if image.size != (rgb.shape[1], rgb.shape[0]):
            raise ValueError("Source dimensions changed")
        return rgb, core.prepare_exclusion(rgb, image.sha256)

    def image_field(self, image):
        """Read-only display copy; retain-all never blocks downstream inference."""
        base = {
            "schema_version": SCHEMA,
            "image_id": image.image_id,
            "source_sha256": image.sha256,
            "method_version": core.VERSION,
            "evidence_kind": EVIDENCE,
            "status": "RETAIN_ALL",
            "reason": "INVALID_OR_UNAVAILABLE_SOURCE",
            "width": None,
            "height": None,
            "parameters": deepcopy(core.PARAMETERS),
            "source_rgb_sha256": None,
            "core_sha256": None,
            "uncertain_sha256": None,
            "core_fraction": 0.0,
            "uncertain_fraction": 0.0,
            "model_input": "ORIGINAL_UNCHANGED",
            "clinical_validation": "NOT_EVALUATED",
            "mask_semantics": "RED=EMPIRICAL_CORE_CANDIDATE;AMBER=UNCERTAIN_KEEP;OTHER=KEEP",
            "raw_detections_preserved": True,
            "negative_or_gold_label": False,
        }
        try:
            rgb, prepared = self._prepare(image)
            height, width = rgb.shape[:2]
            base.update(
                width=width,
                height=height,
                status=prepared["status"],
                reason=prepared["reason"],
                source_rgb_sha256=prepared.get("source_rgb_sha256"),
                core_sha256=prepared.get("core_sha256"),
                uncertain_sha256=prepared.get("uncertain_sha256"),
                safety_margin_source_pixels=prepared.get("safety_margin_source_pixels"),
            )
            shape = (height, width)
            excluded, uncertain = (
                prepared.get("exclude_core"),
                prepared.get("uncertain_keep"),
            )
            valid = all(
                isinstance(mask, np.ndarray)
                and mask.dtype == bool
                and mask.shape == shape
                for mask in (excluded, uncertain)
            )
            overlay = None
            if valid:
                base.update(
                    core_fraction=float(excluded.mean()),
                    uncertain_fraction=float(uncertain.mean()),
                )
                rgba = np.zeros((height, width, 4), dtype=np.uint8)
                rgba[uncertain] = (255, 175, 0, 115)
                rgba[excluded] = (255, 35, 35, 145)
                # Only this detached display image is colored; bytes/RGB used
                # by the model are never assigned or modified.
                overlay = encoded_png(
                    Image.alpha_composite(
                        Image.fromarray(rgb).convert("RGBA"), Image.fromarray(rgba)
                    )
                )
            base["overlay_png_sha256"] = (
                hashlib.sha256(overlay).hexdigest() if overlay else None
            )
            base["field_sha256"] = digest(base)
            return base, overlay
        except Exception:
            base["overlay_png_sha256"] = None
            base["field_sha256"] = digest(base)
            return base, None

    def derive_bound(self, case, image, rows):
        unavailable = {"status": "GENERIC_UWF_RETAINED_ALL"}
        try:
            from ..contracts import LesionResult

            result = LesionResult.model_validate(case["lesion"])
            if (
                result.modality != "UWF"
                or result.model_id != "prism-dr-5fold"
                or (result.width, result.height) != image.size
                or result.provenance.image_sha256 != image.sha256
            ):
                return unavailable
            rgb, prepared = self._prepare(image)
            # The host has already mapped these displayed source-space boxes;
            # transform=None is explicit identity, never a second ROI offset.
            detections = [
                {"id": row["detection_id"], "rectangle": deepcopy(row["rectangle"])}
                for row in rows
            ]
            view = core.apply_prepared(
                rgb, image.sha256, prepared, detections, transform=None, enabled=True
            )
            if view["status"] != "EVALUATED":
                return {**unavailable, "reason": view.get("reason")}
            png = encoded_png(
                Image.fromarray(prepared["exclude_core"].astype(np.uint8) * 255)
            )
            return {
                "status": "READY",
                "input_binding": input_binding(case, image),
                "provider_identity": self.identity(),
                "exclude_mask_png": png,
                "mask_png_sha256": hashlib.sha256(png).hexdigest(),
                "suppressed": [
                    {"detection_id": row["id"], "reason": REASON}
                    for row in view["hidden_artifacts"]
                ],
                "proposal_metadata": {
                    "method_version": core.VERSION,
                    "parameters": deepcopy(core.PARAMETERS),
                    "source_rgb_sha256": prepared["source_rgb_sha256"],
                    "core_sha256": prepared["core_sha256"],
                    "uncertain_sha256": prepared["uncertain_sha256"],
                    "safety_margin_source_pixels": prepared[
                        "safety_margin_source_pixels"
                    ],
                    "confidence": prepared["confidence"],
                    "clinical_validation": "NOT_EVALUATED",
                    "model_input": "ORIGINAL_UNCHANGED",
                    "empirical_not_proven_padding": True,
                },
            }
        except Exception:
            return unavailable
