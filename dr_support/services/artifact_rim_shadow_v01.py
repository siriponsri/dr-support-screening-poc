"""Automatic empirical peripheral-rubber proposals; SHADOW ONLY, not certified."""

import hashlib
import math

import cv2
import numpy as np

VERSION = "empirical-peripheral-rubber-shadow/0.1.1"
PARAMETERS = dict(
    working_max_side=640,
    support_min_value=30,
    support_min_saturation=40,
    geometry_component_min_area_fraction=0.05,
    peripheral_band_fraction=0.10,
    contact_band_fraction=0.02,
    strong_min_value=180,
    strong_min_green=150,
    strong_min_saturation=100,
    strong_green_over_red=0.75,
    strong_blue_over_value_max=0.25,
    green_over_interior_median=1.8,
    value_over_interior_median=1.35,
    component_min_area_fraction=0.0003,
    component_min_span_fraction=0.12,
    component_contact_fraction=0.02,
    erosion_long_side_fraction=0.00625,
    max_shadow_core_fraction=0.12,
)


def propose_rim_artifacts(rgb, source_sha256):
    """Image-only proposal; all pixels outside eroded hypothesis remain keep.

    Geometry is auxiliary and never itself an exclusion mask. No largest-component
    deletion, darkness exclusion, fixed ellipse, learned model or supplied prompts.
    Returned hypothesis MUST NOT be passed into live hard filtering as certified.
    """
    if (
        not isinstance(source_sha256, str)
        or len(source_sha256) != 64
        or any(c not in "0123456789abcdef" for c in source_sha256)
    ):
        return dict(
            status="ABSTAIN_INVALID_SOURCE_BINDING",
            version=VERSION,
            core_exclude=None,
            uncertain=None,
            live_suppression_allowed=False,
        )
    if (
        not isinstance(rgb, np.ndarray)
        or rgb.dtype != np.uint8
        or rgb.ndim != 3
        or rgb.shape[2] != 3
        or min(rgb.shape[:2]) < 8
        or rgb.shape[0] * rgb.shape[1] > 40_000_000
    ):
        return dict(
            status="ABSTAIN_INVALID_RGB",
            version=VERSION,
            core_exclude=None,
            uncertain=None,
            live_suppression_allowed=False,
        )
    h, w = rgb.shape[:2]
    p = PARAMETERS
    scale = min(1, p["working_max_side"] / max(h, w))
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    small = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    value = hsv[:, :, 2]
    sat = hsv[:, :, 1]
    support = (value > p["support_min_value"]) & (sat > p["support_min_saturation"])
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        support.astype(np.uint8), 8
    )
    geometry = np.zeros((sh, sw), np.uint8)
    component_ids = []
    # Every qualifying support region is retained for auxiliary geometry.
    for i in range(1, count):
        if (
            stats[i, cv2.CC_STAT_AREA]
            < sh * sw * p["geometry_component_min_area_fraction"]
        ):
            continue
        contours, _ = cv2.findContours(
            (labels == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        cv2.drawContours(geometry, contours, -1, 1, -1)
        component_ids.append(i)

    def up(mask):
        return (
            cv2.resize(mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
            > 0
        )

    meta = dict(
        version=VERSION,
        provenance_kind="EMPIRICAL_RUBBER_ARTIFACT_HYPOTHESIS_NOT_CERTIFIED_PADDING",
        source_sha256=source_sha256,
        source_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
        source_size=[w, h],
        working_size=list(size),
        scale_xy=[sw / w, sh / h],
        parameters=dict(p),
        auxiliary_geometry_components=len(component_ids),
        live_suppression_allowed=False,
        confidence="UNCALIBRATED_EMPIRICAL_HYPOTHESIS",
        limitations=[
            "BRIGHT_PERIPHERAL_RETINA_CAN_RESEMBLE_RIM",
            "DIM_OR_ORANGE_RIM_CAN_BE_MISSED",
            "NO_LESION_GROUND_TRUTH",
            "OPAQUE_OBSTRUCTION_NOT_ESTIMATED",
        ],
    )
    if not geometry.any():
        return dict(
            status="ABSTAIN_NO_AUXILIARY_FIELD",
            core_exclude=np.zeros((h, w), bool),
            uncertain=np.zeros((h, w), bool),
            metadata=meta,
            version=VERSION,
            live_suppression_allowed=False,
        )
    ys, xs = np.where(geometry)
    short = min(xs.max() - xs.min() + 1, ys.max() - ys.min() + 1)
    padded = np.pad(geometry, 1)
    distance = cv2.distanceTransform(padded, cv2.DIST_L2, 3)[1:-1, 1:-1]
    peripheral = (geometry > 0) & (distance <= short * p["peripheral_band_fraction"])
    interior = (geometry > 0) & (distance > short * 0.15) & (value > 30)
    if interior.sum() < 64:
        meta["interior_anchor_status"] = "INSUFFICIENT"
        return dict(
            status="ABSTAIN_NO_INTERIOR_REFERENCE",
            core_exclude=np.zeros((h, w), bool),
            uncertain=up(peripheral),
            metadata=meta,
            version=VERSION,
            live_suppression_allowed=False,
        )
    red, green, blue = [small[:, :, i].astype(np.float32) for i in range(3)]
    mg = float(np.median(green[interior]))
    mv = float(np.median(value[interior]))
    green_threshold = max(p["strong_min_green"], mg * p["green_over_interior_median"])
    value_threshold = max(p["strong_min_value"], mv * p["value_over_interior_median"])
    strong = (
        (value >= value_threshold)
        & (green >= green_threshold)
        & (sat >= p["strong_min_saturation"])
    )
    strong &= (green >= red * p["strong_green_over_red"]) & (
        blue <= value * p["strong_blue_over_value_max"]
    )
    raw = strong & peripheral
    n, components, cs, _ = cv2.connectedComponentsWithStats(raw.astype(np.uint8), 8)
    attached = np.zeros((sh, sw), bool)
    decisions = []
    contact = distance <= max(1, short * p["contact_band_fraction"])
    for i in range(1, n):
        region = components == i
        area = int(cs[i, cv2.CC_STAT_AREA])
        touch = int((region & contact).sum())
        valid = (
            area >= sh * sw * p["component_min_area_fraction"]
            and max(cs[i, cv2.CC_STAT_WIDTH], cs[i, cv2.CC_STAT_HEIGHT])
            >= short * p["component_min_span_fraction"]
            and touch >= max(3, area * p["component_contact_fraction"])
        )
        decisions.append(
            dict(area=area, boundary_contact_pixels=touch, accepted=bool(valid))
        )
        if valid:
            attached |= region
    radius = max(1, math.ceil(max(sh, sw) * p["erosion_long_side_fraction"]))
    eroded = (
        cv2.erode(
            attached.astype(np.uint8),
            np.ones((2 * radius + 1, 2 * radius + 1), np.uint8),
            borderType=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        > 0
    )
    core = up(eroded)
    # Recheck original pixels to avoid averaged/downsampled rim colors leaking
    # into darker pixels. No dark pixels become proposed exclusion.
    r, g, b = [rgb[:, :, i] for i in range(3)]
    v = rgb.max(axis=2)
    original_strong = (
        (v >= value_threshold)
        & (g >= green_threshold)
        & (g.astype(np.float32) >= r.astype(np.float32) * p["strong_green_over_red"])
        & (
            b.astype(np.float32)
            <= v.astype(np.float32) * p["strong_blue_over_value_max"]
        )
    )
    core &= original_strong
    weak = (
        peripheral
        & (value >= 100)
        & (green >= 75)
        & (green >= red * 0.68)
        & (sat >= 70)
    )
    uncertain = up(weak | raw | attached) & ~core
    status = "SHADOW_PROPOSAL_READY" if core.any() else "ABSTAIN_NO_CORE_AFTER_GUARDS"
    if core.mean() > p["max_shadow_core_fraction"]:
        uncertain |= core
        core[:] = False
        status = "ABSTAIN_EXCESS_PROPOSAL_AREA"
    meta.update(
        interior_median_green=mg,
        interior_median_value=mv,
        green_threshold=green_threshold,
        value_threshold=value_threshold,
        erosion_work_pixels=radius,
        equivalent_source_margin_xy=[radius * w / sw, radius * h / sh],
        component_decisions=decisions,
        core_fraction=float(core.mean()),
        uncertain_fraction=float(uncertain.mean()),
        geometry_never_used_as_exclusion=True,
    )
    return dict(
        status=status,
        version=VERSION,
        core_exclude=core,
        uncertain=uncertain,
        metadata=meta,
        live_suppression_allowed=False,
    )
