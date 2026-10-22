"""Conservative, reversible post-detection artifact queue.

No image classifier, semantic segmentation or filesystem/network access. A trusted
server-side export/acquisition profile is required to establish canvas padding.
Appearance alone cannot establish that rubber, dark tissue or bright lesions are
non-retina. The default profile registry is empty, so default suppression is zero.
"""

from copy import deepcopy
import hashlib
import json
import math

import numpy as np

VERSION = "prism-artifact-core/0.1.1-candidate"
MAX_PIXELS = 40_000_000
SUPPORTED_KIND = "proven_uniform_canvas_padding"


def rgb_sha256(rgb):
    """Hash decoded uint8 RGB bytes, separately from encoded-file SHA256."""
    return hashlib.sha256(np.ascontiguousarray(rgb).tobytes()).hexdigest()


def _sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _size_equals(value, w, h):
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(_integer(v) for v in value)
        and list(value) == [w, h]
    )


def _detection_id(raw, source_sha, occurrence):
    if isinstance(raw, dict) and isinstance(raw.get("id"), str) and raw["id"]:
        return raw["id"]
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()[:20]
    count = occurrence.get(fingerprint, 0)
    occurrence[fingerprint] = count + 1
    return f"{source_sha[:12]}:{fingerprint}:{count}"


def _erode(mask, radius):
    """Square erosion with unknown/outside-canvas treated as keep, not exclude."""
    if radius == 0:
        return mask.copy()
    kernel = 2 * radius + 1
    padded = np.pad(mask.astype(np.uint32), radius)
    summed = np.pad(
        padded.cumsum(0, dtype=np.uint32).cumsum(1, dtype=np.uint32),
        ((1, 0), (1, 0)),
    )
    # uint32 inclusion/exclusion is exact modulo 2**32; max area is <2**32.
    counts = (
        summed[kernel:, kernel:]
        - summed[:-kernel, kernel:]
        - summed[kernel:, :-kernel]
        + summed[:-kernel, :-kernel]
    )
    return counts == kernel * kernel


def _mask(rgb, source_sha, evidence, profiles):
    if not isinstance(evidence, dict):
        return None, "NO_TRUSTED_ARTIFACT_EVIDENCE"
    profile = profiles.get(evidence.get("profile_id"))
    if not isinstance(profile, dict) or profile.get("kind") != SUPPORTED_KIND:
        return None, "UNTRUSTED_OR_UNSUPPORTED_PROFILE"
    if (
        not isinstance(profile.get("provenance"), str)
        or not profile["provenance"].strip()
    ):
        return None, "PROFILE_PROVENANCE_MISSING"
    h, w = rgb.shape[:2]
    if (
        evidence.get("source_sha256") != source_sha
        or evidence.get("source_rgb_sha256") != rgb_sha256(rgb)
        or not _size_equals(evidence.get("source_size"), w, h)
    ):
        return None, "EVIDENCE_SOURCE_BINDING_MISMATCH"
    # Profile extents are host-controlled, never supplied by a detector/client.
    widths = profile.get("padding_t_r_b_l")
    color = profile.get("rgb")
    if (
        not isinstance(widths, (list, tuple))
        or len(widths) != 4
        or not all(_integer(v) and v >= 0 for v in widths)
        or not isinstance(color, (list, tuple))
        or len(color) != 3
        or not all(_integer(v) and 0 <= v <= 255 for v in color)
    ):
        return None, "INVALID_PROFILE_GEOMETRY_OR_COLOR"
    top, right, bottom, left = widths
    if top + bottom >= h or left + right >= w or not any(widths):
        return None, "INVALID_PROFILE_PADDING_EXTENTS"
    # Evidence certifies the exact verified profile revision and full source size.
    if evidence.get("profile_sha256") != profile_sha256(profile):
        return None, "PROFILE_REVISION_MISMATCH"
    candidate = np.zeros((h, w), bool)
    candidate[:top] = True
    if bottom:
        candidate[h - bottom :] = True
    candidate[:, :left] = True
    if right:
        candidate[:, w - right :] = True
    if not np.all(rgb[candidate] == np.array(color, np.uint8)):
        return None, "PIXELS_DO_NOT_MATCH_PROVEN_PADDING"
    return candidate, "PROVEN_CANVAS_PADDING_ONLY"


def profile_sha256(profile):
    """Fingerprint a host-reviewed profile revision; this does not confer trust."""
    return hashlib.sha256(
        json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _transform(transform, source_sha, w, h):
    if not isinstance(transform, dict):
        return None, "TRANSFORM_MISSING"
    if transform.get("source_sha256") != source_sha or not _size_equals(
        transform.get("source_size"), w, h
    ):
        return None, "TRANSFORM_SOURCE_BINDING_MISMATCH"
    if transform.get("kind") != "source_to_detector_scale_pad_xyxy_half_open":
        return None, "UNSUPPORTED_TRANSFORM_OR_COORDINATE_CONVENTION"
    size = transform.get("detector_size")
    vals = [transform.get(k) for k in ["scale_x", "scale_y", "pad_x", "pad_y"]]
    if (
        not isinstance(size, (list, tuple))
        or len(size) != 2
        or not all(_integer(v) and v > 0 for v in size)
        or not all(_number(v) for v in vals)
    ):
        return None, "INVALID_TRANSFORM_NUMBERS"
    sx, sy, px, py = vals
    dw, dh = size
    if sx <= 0 or sy <= 0 or px < 0 or py < 0:
        return None, "INVALID_TRANSFORM_SCALE_OR_PADDING"
    if px + w * sx > dw + 1e-7 or py + h * sy > dh + 1e-7:
        return None, "CROPPING_TRANSFORM_UNSUPPORTED"
    return (sx, sy, px, py, dw, dh), "VALID_TRANSFORM"


def filter_detections(
    rgb,
    source_sha256,
    detections,
    *,
    evidence=None,
    trusted_profiles=None,
    transform=None,
    core_margin_fraction=0.00625,
    box_margin_fraction=0.00625,
):
    """Return raw, visible and reversible hidden-artifact records; never negatives.

    Input detections are JSON dictionaries with ``box_xyxy`` in detector pixels.
    The caller computes encoded-file SHA256 and decodes RGB from those same bytes.
    ``trusted_profiles`` is host configuration, NEVER user/detector request data.
    All uncertainty stays visible. Invalid metadata returns no-suppression status.
    Both normalized margins use the source long side, rounded UP to source pixels.
    """
    raw = deepcopy(detections) if isinstance(detections, list) else []
    occurrence = {}
    records = [
        {
            "id": _detection_id(item, str(source_sha256), occurrence),
            "raw_index": i,
            "raw_detection": deepcopy(item),
            "disposition": "visible",
            "reason": "NO_SUPPRESSION",
            "method_version": VERSION,
        }
        for i, item in enumerate(raw)
    ]
    result = {
        "status": "NO_SUPPRESSION",
        "reason": "NOT_EVALUATED",
        "method_version": VERSION,
        "source_sha256": source_sha256,
        "raw_detections": raw,
        "visible": records,
        "hidden_artifacts": [],
        "confirmed_negative": False,
        "mask": None,
    }

    def abstain(reason):
        result["reason"] = reason
        for record in records:
            record["reason"] = reason
        return result

    if not isinstance(detections, list):
        return abstain("INVALID_DETECTIONS_CONTAINER")
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        return abstain("DUPLICATE_DETECTION_IDS")
    if (
        not isinstance(rgb, np.ndarray)
        or rgb.dtype != np.uint8
        or rgb.ndim != 3
        or rgb.shape[2] != 3
        or min(rgb.shape[:2]) <= 0
        or max(rgb.shape[:2]) > 16384
        or rgb.shape[0] * rgb.shape[1] > MAX_PIXELS
        or not _sha(source_sha256)
    ):
        return abstain("INVALID_SOURCE_RGB_OR_HASH")
    h, w = rgb.shape[:2]
    if not all(
        _number(v) and 0 <= v <= 0.05
        for v in [core_margin_fraction, box_margin_fraction]
    ):
        return abstain("INVALID_SAFETY_MARGIN")
    try:
        mapping, reason = _transform(transform, source_sha256, w, h)
    except (TypeError, ValueError, OverflowError):
        return abstain("INVALID_TRANSFORM_METADATA")
    if mapping is None:
        return abstain(reason)
    if trusted_profiles is not None and not isinstance(trusted_profiles, dict):
        return abstain("INVALID_TRUSTED_PROFILE_REGISTRY")
    try:
        candidate, reason = _mask(rgb, source_sha256, evidence, trusted_profiles or {})
    except (TypeError, ValueError, KeyError, OverflowError):
        return abstain("INVALID_ARTIFACT_METADATA")
    if candidate is None:
        return abstain(reason)
    radius = math.ceil(core_margin_fraction * max(h, w))
    margin = math.ceil(box_margin_fraction * max(h, w))
    try:
        core = _erode(candidate, radius)
    except MemoryError:
        return abstain("RESOURCE_LIMIT_NO_SUPPRESSION")
    result["mask"] = {
        "source_size": [w, h],
        "source_rgb_sha256": rgb_sha256(rgb),
        "candidate_exclude_sha256": hashlib.sha256(candidate.tobytes()).hexdigest(),
        "core_sha256": hashlib.sha256(core.tobytes()).hexdigest(),
        "core_exclude": core,
        "keep_or_uncertain": ~core,
        "core_erosion_source_pixels": radius,
        "box_expansion_source_pixels": margin,
        "provenance": deepcopy(evidence),
    }
    if not core.any():
        return abstain("NO_TRUSTWORTHY_CORE_AFTER_MARGIN")
    sx, sy, px, py, dw, dh = mapping
    result.update(status="EVALUATED", reason="PROVEN_PADDING_POST_FILTER", visible=[])
    for record in records:
        item = record["raw_detection"]
        box = item.get("box_xyxy") if isinstance(item, dict) else None
        reason = None
        if (
            not isinstance(box, (list, tuple))
            or len(box) != 4
            or not all(_number(v) for v in box)
        ):
            reason = "INVALID_NONFINITE_OR_MISSING_BOX"
        elif not (0 <= box[0] < box[2] <= dw and 0 <= box[1] < box[3] <= dh):
            reason = "DEGENERATE_OR_OUT_OF_DETECTOR_BOUNDS"
        if reason:
            record["reason"] = reason
            result["visible"].append(record)
            continue
        x0, y0, x1, y1 = box
        mapped = [(x0 - px) / sx, (y0 - py) / sy, (x1 - px) / sx, (y1 - py) / sy]
        record["source_box_xyxy"] = mapped
        if not (0 <= mapped[0] < mapped[2] <= w and 0 <= mapped[1] < mapped[3] <= h):
            record["reason"] = "BOX_OUTSIDE_SOURCE_NO_CLIPPING_FOR_SUPPRESSION"
            result["visible"].append(record)
            continue
        left, top = math.floor(mapped[0]) - margin, math.floor(mapped[1]) - margin
        right, bottom = math.ceil(mapped[2]) + margin, math.ceil(mapped[3]) + margin
        if left < 0 or top < 0 or right > w or bottom > h:
            record["reason"] = "EXPANDED_BOX_OUTSIDE_SOURCE"
            result["visible"].append(record)
            continue
        patch = core[top:bottom, left:right]
        record["expanded_source_box_xyxy"] = [left, top, right, bottom]
        record["expanded_box_core_fraction"] = float(patch.mean())
        if patch.size and patch.all():
            record.update(
                disposition="hidden_artifact_candidate",
                reason="ENTIRE_EXPANDED_BOX_INSIDE_PROVEN_PADDING_CORE",
            )
            record["core_sha256"] = result["mask"]["core_sha256"]
            result["hidden_artifacts"].append(record)
        else:
            record["reason"] = "INTERSECTS_KEEP_OR_UNCERTAIN"
            result["visible"].append(record)
    return result


def restore_hidden(result, ids=None):
    """Undo hiding for selected IDs (None = all), preserving raw ledger and order."""
    wanted = None if ids is None else set(ids)
    # Own every mutable audit field, including mask arrays and nested provenance.
    # A later overlay edit in this view must never alter the previous audit.
    restored = deepcopy(result)
    visible = restored["visible"]
    hidden = []
    for record in restored["hidden_artifacts"]:
        if wanted is None or record["id"] in wanted:
            record.update(disposition="visible", reason="ARTIFACT_HIDING_REVERSED")
            visible.append(record)
        else:
            hidden.append(record)
    restored.update(
        visible=sorted(visible, key=lambda r: r["raw_index"]), hidden_artifacts=hidden
    )
    return restored
