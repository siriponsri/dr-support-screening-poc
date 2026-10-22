"""Empirical original-image overlay adapter. Always SHADOW, never hides ROIs.

The task-2 proposer is copied unchanged and imported lazily. This lane tests the
adapter using an injected proposer; it does not retry denied OpenCV access.
"""

from copy import deepcopy
import hashlib
import io

import numpy as np
from PIL import Image

from .artifact_roi_assist import digest


VERSION = "empirical-peripheral-rubber-shadow/0.1.1"
PROPOSER_SHA256 = "c55056f8d218ee9b73a03cadab16cc39cdad363d8401bfb7b9c03fcd9ca978a6"


class EmpiricalRimShadowProvider:
    def __init__(self, *, proposer=None):
        self.proposer = proposer

    def identity(self):
        return {"method_version": VERSION, "mask_version": "empirical-shadow-original-pixels.v1",
                "evidence_kind": "EMPIRICAL_RIM_SHADOW_NOT_CERTIFIED",
                "config_sha256": digest({"source": PROPOSER_SHA256, "mode": "SHADOW_ONLY"})}

    def derive(self, image, rows):
        proposer = self.proposer
        if proposer is None:
            # No module import at app startup; no automatic registration. Host
            # OpenCV access/runtime qualification is separate and NOT_RUN here.
            from .artifact_rim_shadow_v01 import propose_rim_artifacts
            proposer = propose_rim_artifacts
        with Image.open(io.BytesIO(image.data)) as original:
            rgb = np.asarray(original.convert("RGB"), dtype=np.uint8)
        result = proposer(rgb, image.sha256)
        metadata, mask = result.get("metadata") or {}, result.get("core_exclude")
        width, height = image.size
        if (result.get("live_suppression_allowed") is not False
                or result.get("status") != "SHADOW_PROPOSAL_READY"
                or metadata.get("source_sha256") != image.sha256
                or metadata.get("source_rgb_sha256") != hashlib.sha256(rgb.tobytes()).hexdigest()
                or metadata.get("source_size") != [width, height]
                or not isinstance(mask, np.ndarray) or mask.dtype != np.bool_
                or mask.shape != (height, width)):
            return {"status": "EMPIRICAL_SHADOW_UNAVAILABLE_RETAINED_ALL"}
        output = io.BytesIO()
        Image.fromarray(mask.astype(np.uint8) * 255).save(output, "PNG")
        png = output.getvalue()
        return {"status": "SHADOW_ONLY", "source_binding": {
                    "source_sha256": image.sha256, "image_id": image.image_id,
                    "width": width, "height": height, "coordinate_space": "ORIGINAL",
                    "transform_version": "identity-original-pixels.v1"},
                "provider_identity": self.identity(), "exclude_mask_png": png,
                "mask_png_sha256": hashlib.sha256(png).hexdigest(),
                "suppressed": [], "proposal_metadata": {
                    "method": deepcopy(metadata), "roi_proposal_evaluation": "NOT_RUN",
                    "known_failure": "BRIGHT_PERIPHERAL_REAL_TISSUE_MAY_BE_PROPOSED",
                    "live_suppression_allowed": False}}
