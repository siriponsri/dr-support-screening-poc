"""Image-only annotation-assist core (byte-pinned upstream algorithm, see .gitattributes).

Used by `services/artifact_roi_generic_adapter.py`, which `workflow.install_workflow` selects when the
artifact ROI assist is enabled. `core.py` is byte-identical to `services/artifact_core_v01.py`; both
stay as separate pinned copies because each is a provenance-pinned upstream file.
"""

from .core import filter_detections, profile_sha256, restore_hidden, rgb_sha256

__all__ = ["filter_detections", "profile_sha256", "restore_hidden", "rgb_sha256"]
