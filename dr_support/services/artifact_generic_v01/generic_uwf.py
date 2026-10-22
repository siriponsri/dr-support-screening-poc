"""Generic CPU image-only reflective-border adapter; no cached image identities.

Pillow/NumPy only. An empirical annotation-assist candidate, not a retina segmenter
or certified artifact probability. Original RGB is never modified or blinded.
"""

from copy import deepcopy
import hashlib
import math

import numpy as np
from PIL import Image

from .core import _number, _sha, _size_equals, _transform, restore_hidden

VERSION = "generic-uwf-reflective-border/0.1.0"
PARAMETERS = dict(
    working_max_side=640,
    support_value=30,
    support_saturation=40,
    geometry_min_component_area=0.05,
    outer_band_fraction=0.10,
    contact_band_fraction=0.02,
    interior_fraction=0.15,
    interior_min_pixels=64,
    weak_value=100,
    weak_green=75,
    weak_green_over_red=0.68,
    weak_saturation=70,
    strong_value=180,
    strong_green=150,
    strong_green_over_red=0.75,
    strong_saturation=100,
    strong_blue_over_value=0.25,
    green_over_interior=1.8,
    value_over_interior=1.35,
    strong_min_area_fraction=0.0003,
    component_span_fraction=0.12,
    strong_fraction_in_connected_weak_component=0.10,
    safety_margin_long_side_fraction=0.00625,
    max_excluded_fraction=0.12,
)


def pixel_hash(rgb):
    return hashlib.sha256(np.ascontiguousarray(rgb).tobytes()).hexdigest()


def erode_square(mask, radius):
    """Exact square erosion, separable sums; bounded memory vs a 2D integral."""
    if radius == 0:
        return mask.copy()
    k = 2 * radius + 1
    padded = np.pad(mask, ((radius, radius), (0, 0)))
    sums = np.pad(padded.cumsum(0, dtype=np.uint32), ((1, 0), (0, 0)))
    vertical = (sums[k:] - sums[:-k]) == k
    del padded, sums
    padded = np.pad(vertical, ((0, 0), (radius, radius)))
    sums = np.pad(padded.cumsum(1, dtype=np.uint32), ((0, 0), (1, 0)))
    return (sums[:, k:] - sums[:, :-k]) == k


def components(mask):
    """4-connected run components. No semantic classes or largest-only selection."""
    parent = []
    runs = []
    previous = []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for y, row in enumerate(mask):
        edges = np.diff(np.pad(row.astype(np.int8), (1, 1)))
        current = []
        j = 0
        for left, right in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
            i = len(parent)
            parent.append(i)
            runs.append((y, int(left), int(right)))
            current.append(i)
            while j < len(previous) and runs[previous[j]][2] <= left:
                j += 1
            q = j
            while q < len(previous) and runs[previous[q]][1] < right:
                a, b = find(i), find(previous[q])
                if a != b:
                    parent[b] = a
                q += 1
        previous = current
    found = {}
    for i, run in enumerate(runs):
        found.setdefault(find(i), []).append(run)
    return list(found.values())


def region_mask(shape, runs):
    out = np.zeros(shape, bool)
    for y, left, right in runs:
        out[y, left:right] = True
    return out


def filled_geometry(support):
    h, w = support.shape
    geometry = np.zeros_like(support)
    n = 0
    for runs in components(support):
        if (
            sum(right - left for _, left, right in runs)
            >= h * w * PARAMETERS["geometry_min_component_area"]
        ):
            for y, left, right in runs:
                geometry[y, left:right] = True
            n += 1
    for runs in components(~geometry):
        if not any(
            y in (0, h - 1) or left == 0 or right == w for y, left, right in runs
        ):
            for y, left, right in runs:
                geometry[y, left:right] = True
    return geometry, n


def _color_planes(rgb):
    value = rgb.max(2)
    low = rgb.min(2)
    saturation = 255 * (value.astype(np.float32) - low) / np.maximum(value, 1)
    return value, saturation, rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]


def prepare_exclusion(rgb, source_sha256):
    """Every valid RGB may be evaluated; no filename/SHA whitelist or prompts."""
    result = dict(
        version=VERSION,
        status="RETAIN_ALL",
        reason="INVALID_SOURCE",
        source_sha256=source_sha256,
        confidence="UNCALIBRATED_EMPIRICAL_CANDIDATE",
        provenance_kind="IMAGE_ONLY_REFLECTIVE_PERIPHERAL_HYPOTHESIS",
        seed=None,
        exclude_core=None,
        uncertain_keep=None,
        source_size=None,
        parameters=deepcopy(PARAMETERS),
    )
    if (
        not _sha(source_sha256)
        or not isinstance(rgb, np.ndarray)
        or rgb.dtype != np.uint8
        or rgb.ndim != 3
        or rgb.shape[2] != 3
        or min(rgb.shape[:2]) < 8
        or max(rgb.shape[:2]) > 16384
        or rgb.shape[0] * rgb.shape[1] > 40_000_000
    ):
        return result
    h, w = rgb.shape[:2]
    result.update(source_size=[w, h], source_rgb_sha256=pixel_hash(rgb))

    def abstain(reason, uncertain=None):
        result.update(
            status="RETAIN_ALL",
            reason=reason,
            seed=np.zeros((h, w), bool),
            exclude_core=np.zeros((h, w), bool),
            uncertain_keep=np.zeros((h, w), bool) if uncertain is None else uncertain,
        )
        result.update(
            seed_sha256=pixel_hash(result["seed"]),
            core_sha256=pixel_hash(result["exclude_core"]),
            uncertain_sha256=pixel_hash(result["uncertain_keep"]),
        )
        return result

    p = PARAMETERS
    scale = min(1, p["working_max_side"] / max(w, h))
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    small = np.array(Image.fromarray(rgb).resize(size, Image.Resampling.BOX), copy=True)
    value, sat, red, green, blue = _color_planes(small)
    sh, sw = value.shape
    geometry, count = filled_geometry(
        (value > p["support_value"]) & (sat > p["support_saturation"])
    )
    result.update(
        working_size=list(size),
        source_to_work_scale_xy=[sw / w, sh / h],
        geometry_components=count,
    )
    if not geometry.any():
        return abstain("NO_CHROMATIC_FIELD_REFERENCE")
    yy, xx = np.where(geometry)
    short = min(int(xx.max() - xx.min() + 1), int(yy.max() - yy.min() + 1))
    peripheral = geometry & ~erode_square(
        geometry, max(1, math.ceil(short * p["outer_band_fraction"]))
    )
    contact = geometry & ~erode_square(
        geometry, max(1, math.ceil(short * p["contact_band_fraction"]))
    )
    interior = erode_square(
        geometry, max(1, math.ceil(short * p["interior_fraction"]))
    ) & (value > 30)

    def up(m):
        return np.array(Image.fromarray(m).resize((w, h), Image.Resampling.NEAREST))

    if interior.sum() < p["interior_min_pixels"]:
        return abstain("INSUFFICIENT_INTERIOR_REFERENCE", up(peripheral))
    mg = float(np.median(green[interior]))
    mv = float(np.median(value[interior]))
    gt = max(p["strong_green"], mg * p["green_over_interior"])
    vt = max(p["strong_value"], mv * p["value_over_interior"])
    weak = (
        peripheral
        & (value > p["weak_value"])
        & (green > p["weak_green"])
        & (green >= red.astype(np.float32) * p["weak_green_over_red"])
        & (sat >= p["weak_saturation"])
    )
    strong = (
        weak
        & (value >= vt)
        & (green >= gt)
        & (green >= red.astype(np.float32) * p["strong_green_over_red"])
        & (sat >= p["strong_saturation"])
        & (blue.astype(np.float32) <= value * p["strong_blue_over_value"])
    )
    accepted = np.zeros_like(geometry)
    decisions = []
    # Weak reflective connectivity reaches the optical edge; only its strong
    # plateau pixels are exclusion seeds. This avoids requiring a bright plateau
    # itself to touch a potentially dim outer rim, without deleting weak tissue.
    for runs in components(weak):
        area = sum(right - left for _, left, right in runs)
        ys = [r[0] for r in runs]
        span = max(
            max(ys) - min(ys) + 1,
            max(right for _, _, right in runs) - min(left for _, left, _ in runs),
        )
        region = region_mask(weak.shape, runs)
        touch = int((region & contact).sum())
        strength = int((region & strong).sum())
        ok = (
            span >= short * p["component_span_fraction"]
            and touch >= 3
            and strength
            >= max(
                12,
                sh * sw * p["strong_min_area_fraction"],
                area * p["strong_fraction_in_connected_weak_component"],
            )
        )
        if ok:
            accepted |= region & strong
        decisions.append(
            dict(
                area=area,
                span=span,
                boundary_contact=touch,
                strong_pixels=strength,
                accepted=bool(ok),
            )
        )
    result.update(
        interior_median_green=mg,
        interior_median_value=mv,
        strong_green_threshold=gt,
        strong_value_threshold=vt,
        component_decisions=decisions,
    )
    seed = up(accepted)
    # Exact source-pixel recheck: no averaging can convert dark/white pixels into
    # saturated reflective seeds. Auxiliary geometry never excludes background.
    sv = rgb.max(2)
    low = rgb.min(2)
    sr = rgb[:, :, 0]
    sg = rgb[:, :, 1]
    sb = rgb[:, :, 2]
    seed &= (sv >= vt) & (sg >= gt)
    seed &= sg.astype(np.uint16) * 4 >= sr.astype(np.uint16) * 3
    seed &= sb.astype(np.uint16) * 4 <= sv
    seed &= (sv.astype(np.uint16) - low) * 255 >= p["strong_saturation"] * sv.astype(
        np.uint16
    )
    margin = math.ceil(max(h, w) * p["safety_margin_long_side_fraction"])
    core = erode_square(seed, margin)
    uncertain = up(weak) & ~core
    result.update(
        safety_margin_source_pixels=margin,
        margin_counted_once=True,
        core_fraction=float(core.mean()),
        uncertain_fraction=float(uncertain.mean()),
    )
    if not core.any():
        return abstain("NO_CORE_AFTER_CONNECTIVITY_COLOR_AND_MARGIN", uncertain)
    if core.mean() > p["max_excluded_fraction"]:
        return abstain("EXCESS_EXCLUSION_ABSTAIN", uncertain | core)
    result.update(
        status="READY_EMPIRICAL",
        reason="CONNECTED_REFLECTIVE_BORDER_WITH_MARGIN",
        seed=seed,
        exclude_core=core,
        uncertain_keep=uncertain,
        seed_sha256=pixel_hash(seed),
        core_sha256=pixel_hash(core),
        uncertain_sha256=pixel_hash(uncertain),
    )
    return result


def apply_prepared(
    rgb, source_sha256, prepared, lesions, *, transform=None, enabled=False
):
    """Reversible annotation view. Source/transform/mask mismatch keeps all rows."""
    raw = deepcopy(lesions) if isinstance(lesions, list) else []
    occurrences = {}
    rows = []
    for index, item in enumerate(raw):
        identity = item.get("id") if isinstance(item, dict) else None
        if not isinstance(identity, str) or not identity:
            digest = hashlib.sha256(json_bytes(item)).hexdigest()[:20]
            n = occurrences.get(digest, 0)
            occurrences[digest] = n + 1
            identity = f"{source_sha256}:{digest}:{n}"
        rows.append(
            dict(
                id=identity,
                raw_index=index,
                raw_detection=deepcopy(item),
                disposition="visible",
                reason="RETAIN_ALL",
                method_version=VERSION,
            )
        )
    view = dict(
        method_version=VERSION,
        raw_detections=raw,
        visible=rows,
        hidden_artifacts=[],
        confirmed_negative=False,
        mask=None,
        source_sha256=source_sha256,
        enabled=bool(enabled),
        status="RETAIN_ALL",
    )

    def retain(reason):
        view["reason"] = reason
        for row in rows:
            row["reason"] = reason
        return view

    if not isinstance(lesions, list):
        return retain("INVALID_ROI_LIST")
    if type(enabled) is not bool:
        view["enabled"] = False
        return retain("INVALID_ENABLE_FLAG_KEEP_ALL")
    if len({r["id"] for r in rows}) != len(rows):
        return retain("DUPLICATE_IDS_KEEP_ALL")
    if (
        not isinstance(prepared, dict)
        or not isinstance(prepared.get("version"), str)
        or prepared.get("version") != VERSION
    ):
        return retain("UNKNOWN_PREPARED_VERSION")
    if not isinstance(rgb, np.ndarray) or rgb.ndim != 3 or rgb.dtype != np.uint8:
        return retain("INVALID_RGB")
    h, w = rgb.shape[:2]
    if (
        not _sha(source_sha256)
        or not _sha(prepared.get("source_sha256"))
        or prepared.get("source_sha256") != source_sha256
        or not _size_equals(prepared.get("source_size"), w, h)
        or not _sha(prepared.get("source_rgb_sha256"))
        or prepared.get("source_rgb_sha256") != pixel_hash(rgb)
    ):
        return retain("SOURCE_BINDING_MISMATCH")
    if not isinstance(prepared.get("status"), str):
        return retain("INVALID_PREPARED_STATUS")
    if prepared.get("status") != "READY_EMPIRICAL":
        return retain(prepared.get("reason", "UNCERTAIN_KEEP_ALL"))
    for name, hashkey in [
        ("seed", "seed_sha256"),
        ("exclude_core", "core_sha256"),
        ("uncertain_keep", "uncertain_sha256"),
    ]:
        m = prepared.get(name)
        if (
            not isinstance(m, np.ndarray)
            or m.dtype != bool
            or m.shape != (h, w)
            or not _sha(prepared.get(hashkey))
            or pixel_hash(m) != prepared.get(hashkey)
        ):
            return retain("MASK_BINDING_MISMATCH")
    if transform is None:
        transform = dict(
            kind="source_to_detector_scale_pad_xyxy_half_open",
            source_sha256=source_sha256,
            source_size=[w, h],
            detector_size=[w, h],
            scale_x=1,
            scale_y=1,
            pad_x=0,
            pad_y=0,
        )
    try:
        mapping, reason = _transform(transform, source_sha256, w, h)
    except (TypeError, ValueError, OverflowError):
        return retain("INVALID_TRANSFORM")
    if mapping is None:
        return retain(reason)
    sx, sy, px, py, dw, dh = mapping
    seed = prepared["seed"]
    margin = prepared.get("safety_margin_source_pixels")
    if type(margin) is not int or margin != math.ceil(
        max(h, w) * PARAMETERS["safety_margin_long_side_fraction"]
    ):
        return retain("INVALID_SAFETY_MARGIN")
    view.update(
        status="EVALUATED",
        reason="EMPIRICAL_IMAGE_ONLY_POSTFILTER",
        mask=deepcopy(prepared),
        visible=[],
    )
    for row in rows:
        item = row["raw_detection"]
        box = (
            item.get("rectangle", item.get("box_xyxy"))
            if isinstance(item, dict)
            else None
        )
        if (
            not isinstance(box, (list, tuple))
            or len(box) != 4
            or not all(_number(v) for v in box)
        ):
            row["reason"] = "INVALID_BOX_KEEP"
        elif not (0 <= box[0] < box[2] <= dw and 0 <= box[1] < box[3] <= dh):
            row["reason"] = "OUT_OF_BOUNDS_OR_DEGENERATE_KEEP"
        else:
            mapped = [
                (box[0] - px) / sx,
                (box[1] - py) / sy,
                (box[2] - px) / sx,
                (box[3] - py) / sy,
            ]
            row["source_box_xyxy"] = mapped
            if not all(_number(v) for v in mapped):
                row["reason"] = "NONFINITE_MAPPED_BOX_KEEP"
                view["visible"].append(row)
                continue
            left, top, right, bottom = (
                math.floor(mapped[0]) - margin,
                math.floor(mapped[1]) - margin,
                math.ceil(mapped[2]) + margin,
                math.ceil(mapped[3]) + margin,
            )
            row["expanded_box_xyxy"] = [left, top, right, bottom]
            if left < 0 or top < 0 or right > w or bottom > h:
                row["reason"] = "EXPANDED_BOX_OUTSIDE_SOURCE_KEEP"
            else:
                patch = seed[top:bottom, left:right]
                row["expanded_box_seed_fraction"] = float(patch.mean())
                row["would_hide"] = bool(patch.size and patch.all())
                row["reason"] = (
                    "ENTIRE_EXPANDED_BOX_IN_EMPIRICAL_SEED"
                    if row["would_hide"]
                    else "INTERSECTS_KEEP_OR_UNCERTAIN"
                )
                if row["would_hide"] and enabled:
                    row["disposition"] = "hidden_artifact_candidate"
                    view["hidden_artifacts"].append(row)
                    continue
        view["visible"].append(row)
    return view


def json_bytes(value):
    import json

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()


def prepare_and_filter(rgb, source_sha256, lesions, *, transform=None, enabled=False):
    return apply_prepared(
        rgb,
        source_sha256,
        prepare_exclusion(rgb, source_sha256),
        lesions,
        transform=transform,
        enabled=enabled,
    )


__all__ = [
    "prepare_exclusion",
    "apply_prepared",
    "prepare_and_filter",
    "restore_hidden",
]
