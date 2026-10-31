"""Mask A for PRISM UWF input: remove only the device's rubber rim (owner-approved 2026-10-31).

Goal for phase 1: PRISM should not label the yellow-green rubber eyecup rim in
Optos UWF images. Everything else, including dark peripheral retina, the optic
disc and yellow spots inside the retina, is kept.

Rule (chosen on 20 hard development cases plus samples; not clinically
validated): a rim pixel is bright (green > 100), green at least half of red,
and low in blue, and it must belong to a large region touching the outer edge
of the picture area. The kept area is the picture area minus that rim, the
largest connected part, with enclosed holes filled. Deterministic and CPU only;
no anatomy segmentation and no model.
"""
from __future__ import annotations

import hashlib
import struct

from PIL import Image

from .uwf_white_rim_fov import FovStatus, WhiteRimFov

try:
    import cv2
    import numpy as np
except ImportError:  # OpenCV is an optional extra on non-inference workstations.
    cv2 = None
    np = None

MASK_A_VERSION = "uwf_rubber_rim_colour_a_v1"
_WORKING_SIDE = 960
_MIN_KEPT, _MAX_KEPT = 0.10, 0.999


def _source_hash(rgb: Image.Image) -> str:
    return hashlib.sha256(struct.pack(">II", rgb.width, rgb.height) + rgb.tobytes()).hexdigest()


def mask_hash(mask: Image.Image) -> str:
    return hashlib.sha256(MASK_A_VERSION.encode("ascii") + struct.pack(">II", *mask.size) + mask.tobytes()).hexdigest()


def _fill_holes(mask):
    padded = np.pad(mask.astype(np.uint8) * 255, 1)
    canvas = np.zeros((padded.shape[0] + 2, padded.shape[1] + 2), np.uint8)
    cv2.floodFill(padded, canvas, (0, 0), 128)
    return mask | (padded[1:-1, 1:-1] == 0)


def rim_pixels(rgb):
    """Large bright green-dominant regions touching the outer edge of the picture area."""
    r, g, b = (rgb[..., index].astype(np.float32) for index in range(3))
    candidate = ((g > 100) & (g >= 0.5 * r) & (g > 1.5 * b)).astype(np.uint8)
    picture = ((r + g + b) / 3 > 6).astype(np.uint8)
    band = max(5, int(0.02 * max(rgb.shape[:2])))
    inner = cv2.erode(np.pad(picture, 1), np.ones((3, 3), np.uint8), iterations=band)[1:-1, 1:-1]
    periphery = (picture == 1) & (inner == 0)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, 8)
    rim = np.zeros(candidate.shape, bool)
    for index in range(1, count):
        part = labels == index
        if stats[index, cv2.CC_STAT_AREA] >= 0.002 * candidate.size and (part & periphery).any():
            rim |= part
    return cv2.dilate(rim.astype(np.uint8), np.ones((7, 7), np.uint8), iterations=1).astype(bool), picture.astype(bool)


def kept_area(rgb):
    rim, picture = rim_pixels(rgb)
    keep = (picture & ~rim).astype(np.uint8)
    keep = cv2.morphologyEx(keep, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8), iterations=1)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(keep, 8)
    if count > 1:
        keep = (labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    keep = _fill_holes(keep.astype(bool))
    return keep, bool(rim.any()), boundary_support(keep, rim, picture)


def boundary_support(keep, rim, picture):
    """Engineering boundary score, not a clinical probability: the share of the kept-area outline lying next to
    the removed rim or the dark frame (outside the image counts as frame). Low means it cuts into the picture."""
    padded = np.pad(keep.astype(np.uint8), 1)
    outline = (padded == 1) & (cv2.erode(padded, np.ones((3, 3), np.uint8)) == 0)
    explained = np.pad((rim | ~picture).astype(np.uint8), 1, constant_values=1)
    explained = cv2.dilate(explained, np.ones((7, 7), np.uint8)) == 1
    return round(float(explained[outline].mean()), 4) if outline.any() else 0.0


def _result(rgb: Image.Image, status: FovStatus, reason: str | None, mask: Image.Image | None = None,
            boundary=(), box=None, kept=None, support=None) -> WhiteRimFov:
    return WhiteRimFov(status=status, field_mask=mask, mask_version=MASK_A_VERSION,
                       mask_sha256=mask_hash(mask) if mask is not None else None, source_rgb_sha256=_source_hash(rgb),
                       boundary_confidence=support, field_fraction=kept, excluded_fraction=None if kept is None else 1 - kept,
                       bounding_box=box, boundary=tuple(boundary), image_width=rgb.width, image_height=rgb.height,
                       reason_code=reason)


def detect_rubber_rim_mask(original_rgb: Image.Image) -> WhiteRimFov:
    """READY with a binary mask (255 kept) when a usable area remains; UNAVAILABLE otherwise (original is used)."""
    rgb = original_rgb.convert("RGB")
    if cv2 is None or np is None:
        return _result(rgb, FovStatus.UNAVAILABLE, "OPENCV_UNAVAILABLE")
    scale = min(1.0, _WORKING_SIDE / max(rgb.size))
    working = rgb if scale == 1.0 else rgb.resize((max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))),
                                                  Image.BILINEAR)
    keep, rim_found, support = kept_area(np.asarray(working))
    fraction = float(keep.mean())
    if not _MIN_KEPT <= fraction <= _MAX_KEPT:
        return _result(rgb, FovStatus.UNAVAILABLE, "KEPT_AREA_OUT_OF_RANGE")
    small = Image.fromarray(keep.astype(np.uint8) * 255, "L")
    mask = small if scale == 1.0 else small.resize(rgb.size, Image.NEAREST)
    full = np.asarray(mask) == 255
    ys, xs = np.nonzero(full)
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    contours, _ = cv2.findContours(full.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    outline = max(contours, key=cv2.contourArea) if contours else None
    boundary = [] if outline is None else [(int(x), int(y)) for x, y in
                                           cv2.approxPolyDP(outline, 2.0, True).reshape(-1, 2)]
    return _result(rgb, FovStatus.READY, None if rim_found else "NO_RIM_FOUND_PICTURE_AREA_ONLY", mask, boundary,
                   box, round(float(full.mean()), 6), support)
