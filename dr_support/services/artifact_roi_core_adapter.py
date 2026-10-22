"""Explicit, unregistered adapter for task-2's unchanged technical-frame core.

Empty host registry is the default: no real rubber-rim effect is claimed.
Empirical rim proposals remain a separate shadow adapter/review checkpoint.
"""

from copy import deepcopy
import hashlib
import io

import numpy as np
from PIL import Image

from . import artifact_core_v01 as core
from .artifact_roi_assist import digest, input_binding


class TechnicalFrameArtifactProvider:
    def __init__(self, *, trusted_profiles=None, evidence_for=None):
        self.profiles = deepcopy(trusted_profiles or {})
        self.evidence_for = evidence_for

    def identity(self):
        return {"method_version": core.VERSION, "mask_version": "technical-frame-core.v1",
                "evidence_kind": "PROVEN_TECHNICAL_PADDING_ONLY",
                "config_sha256": digest(self.profiles)}

    def derive(self, image, rows):
        with Image.open(io.BytesIO(image.data)) as original:
            rgb = np.asarray(original.convert("RGB"), dtype=np.uint8)
        width, height = image.size
        detections = [{"id": row["detection_id"], "box_xyxy": list(row["rectangle"])} for row in rows]
        transform = dict(kind="source_to_detector_scale_pad_xyxy_half_open",
                         source_sha256=image.sha256, source_size=[width, height],
                         detector_size=[width, height], scale_x=1, scale_y=1, pad_x=0, pad_y=0)
        evidence = self.evidence_for(image, rgb) if self.evidence_for else None
        result = core.filter_detections(rgb, image.sha256, detections, evidence=evidence,
                                        trusted_profiles=deepcopy(self.profiles), transform=transform)
        if result["status"] != "EVALUATED":
            return {"status": "TECHNICAL_FRAME_UNAVAILABLE_RETAINED_ALL"}
        mask = result["mask"]["core_exclude"]
        output = io.BytesIO()
        Image.fromarray(mask.astype(np.uint8) * 255).save(output, "PNG")
        png = output.getvalue()
        # The application packet binds the actual full raw result separately;
        # only its presentation IDs/rectangles enter this post-filter adapter.
        binding = {"source_sha256": image.sha256, "image_id": image.image_id,
                   "width": width, "height": height, "coordinate_space": "ORIGINAL",
                   "transform_version": "identity-original-pixels.v1"}
        return {"status": "READY", "source_binding": binding,
                "provider_identity": self.identity(), "exclude_mask_png": png,
                "mask_png_sha256": hashlib.sha256(png).hexdigest(),
                "suppressed": [{"detection_id": row["id"], "reason": "SURE_EXCLUDED_ARTIFACT"}
                               for row in result["hidden_artifacts"]]}


def bind_full_result_packet(provider, case, image, rows):
    """Reviewed caller attaches raw-result hash without altering core decisions."""
    packet = provider.derive(image, rows)
    if packet.get("status") in {"READY", "SHADOW_ONLY"}:
        expected = input_binding(case, image)
        source = {key: value for key, value in expected.items() if key != "raw_result_sha256"}
        if packet.pop("source_binding", None) != source:
            return {"status": "UNKNOWN_SOURCE_BINDING_RETAINED_ALL"}
        packet["input_binding"] = expected
    return packet
