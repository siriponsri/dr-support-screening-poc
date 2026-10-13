"""Conservative camera-rim masking for experimental PRISM UWF preparation.

This detects a photographic field boundary only. It is not retinal anatomy
segmentation, and uncertain geometry never authorizes model input.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from enum import StrEnum
from typing import Sequence

from PIL import Image

try:
    import cv2
    import numpy as np
except ImportError:  # OpenCV is an optional extra on non-inference workstations.
    cv2 = None
    np = None


FOV_MASK_VERSION = "uwf_white_rim_fov_v1"
_MAX_WORKING_SIDE = 1024
_MIN_SOURCE_SIDE = 128


class FovStatus(StrEnum):
    READY = "READY"
    UNCERTAIN = "UNCERTAIN"
    UNAVAILABLE = "UNAVAILABLE"


class BoxBoundaryClass(StrEnum):
    INSIDE_ANALYSIS_FIELD = "INSIDE_ANALYSIS_FIELD"
    OUTSIDE_ANALYSIS_FIELD = "OUTSIDE_ANALYSIS_FIELD"
    NEAR_CAMERA_RIM = "NEAR_CAMERA_RIM"
    INVALID_BOX = "INVALID_BOX"


class FovNotReadyError(ValueError):
    """Raised when a candidate field cannot authorize PRISM image input."""


@dataclass(frozen=True)
class WhiteRimFov:
    """FOV evidence in original-image pixel coordinates.

    ``bounding_box`` uses half-open ``(x_min, y_min, x_max, y_max)`` edges;
    ``boundary`` is a polygon on the same canvas. The confidence is an
    engineering boundary score, not a clinical probability.
    """

    status: FovStatus
    field_mask: Image.Image | None
    mask_version: str
    mask_sha256: str | None
    source_rgb_sha256: str
    boundary_confidence: float | None
    field_fraction: float | None
    excluded_fraction: float | None
    bounding_box: tuple[int, int, int, int] | None
    boundary: tuple[tuple[int, int], ...]
    image_width: int
    image_height: int
    reason_code: str | None


@dataclass(frozen=True)
class PrismUwfPreparation:
    masked_rgb: Image.Image
    fov: WhiteRimFov
    bounding_box: tuple[int, int, int, int]


def _source_rgb(source: Image.Image) -> Image.Image:
    if not isinstance(source, Image.Image):
        raise TypeError("Original RGB must be a Pillow image")
    return source.convert("RGB")


def _source_hash(source_rgb: Image.Image) -> str:
    identity = struct.pack(">II", source_rgb.width, source_rgb.height) + source_rgb.tobytes()
    return hashlib.sha256(identity).hexdigest()


def _mask_hash(mask: Image.Image) -> str:
    identity = (
        FOV_MASK_VERSION.encode("ascii")
        + struct.pack(">II", mask.width, mask.height)
        + mask.tobytes()
    )
    return hashlib.sha256(identity).hexdigest()


def _validated_field_mask(fov: WhiteRimFov) -> object:
    if fov.status is not FovStatus.READY or fov.field_mask is None:
        raise FovNotReadyError(fov.reason_code or "FOV_NOT_READY")
    if fov.mask_version != FOV_MASK_VERSION:
        raise FovNotReadyError("FOV_MASK_VERSION_MISMATCH")
    if fov.field_mask.size != (fov.image_width, fov.image_height) or fov.field_mask.mode != "L":
        raise FovNotReadyError("FOV_MASK_DIMENSIONS_INVALID")
    if fov.mask_sha256 != _mask_hash(fov.field_mask):
        raise FovNotReadyError("FOV_MASK_HASH_MISMATCH")
    if np is None:
        raise FovNotReadyError("OPENCV_UNAVAILABLE")
    return np.asarray(fov.field_mask, dtype=np.uint8)


def _empty_result(
    status: FovStatus,
    source_rgb: Image.Image,
    source_sha256: str,
    reason_code: str,
) -> WhiteRimFov:
    return WhiteRimFov(
        status=status,
        field_mask=None,
        mask_version=FOV_MASK_VERSION,
        mask_sha256=None,
        source_rgb_sha256=source_sha256,
        boundary_confidence=None,
        field_fraction=None,
        excluded_fraction=None,
        bounding_box=None,
        boundary=(),
        image_width=source_rgb.width,
        image_height=source_rgb.height,
        reason_code=reason_code,
    )


def _contour_depth(hierarchy: object, index: int) -> int:
    depth = 0
    parent = int(hierarchy[0][index][3])  # type: ignore[index]
    while parent >= 0:
        depth += 1
        parent = int(hierarchy[0][parent][3])  # type: ignore[index]
    return depth


def _sample_support(mask: object, contour: object) -> float:
    points = contour.reshape(-1, 2)
    height, width = mask.shape[:2]
    x = np.clip(points[:, 0], 0, width - 1)
    y = np.clip(points[:, 1], 0, height - 1)
    return float(np.mean(mask[y, x] > 0))


def _ellipse_residual(contour: object) -> tuple[float, float] | None:
    if len(contour) < 5:
        return None
    (cx, cy), (diameter_a, diameter_b), angle = cv2.fitEllipse(contour)
    semi_a, semi_b = diameter_a / 2, diameter_b / 2
    if min(semi_a, semi_b) <= 0:
        return None
    points = contour.reshape(-1, 2).astype(np.float64)
    radians = math.radians(angle)
    dx, dy = points[:, 0] - cx, points[:, 1] - cy
    local_x = dx * math.cos(radians) + dy * math.sin(radians)
    local_y = -dx * math.sin(radians) + dy * math.cos(radians)
    radial = np.sqrt((local_x / semi_a) ** 2 + (local_y / semi_b) ** 2)
    return float(np.median(np.abs(radial - 1))), max(semi_a, semi_b) / min(semi_a, semi_b)


def detect_white_rim_fov(original_rgb: Image.Image) -> WhiteRimFov:
    """Detect a conservative center field from a detached Original RGB image.

    Bright, low-saturation pixels provide the camera-rim candidates. Canny
    edges only support those candidates; a closed contour must still enclose
    the image center and pass area, canvas, and ellipse checks.
    """
    source_rgb = _source_rgb(original_rgb)
    source_sha256 = _source_hash(source_rgb)
    if source_rgb.width < _MIN_SOURCE_SIDE or source_rgb.height < _MIN_SOURCE_SIDE:
        return _empty_result(FovStatus.UNCERTAIN, source_rgb, source_sha256, "IMAGE_TOO_SMALL")
    if cv2 is None or np is None:
        return _empty_result(FovStatus.UNAVAILABLE, source_rgb, source_sha256, "OPENCV_UNAVAILABLE")

    rgb = np.asarray(source_rgb, dtype=np.uint8)
    source_height, source_width = rgb.shape[:2]
    scale = min(1.0, _MAX_WORKING_SIDE / max(source_width, source_height))
    work_width = max(1, round(source_width * scale))
    work_height = max(1, round(source_height * scale))
    if (work_width, work_height) != (source_width, source_height):
        work_rgb = cv2.resize(rgb, (work_width, work_height), interpolation=cv2.INTER_AREA)
    else:
        work_rgb = rgb.copy()

    hsv = cv2.cvtColor(work_rgb, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(work_rgb, cv2.COLOR_RGB2GRAY)
    white_candidates = cv2.inRange(hsv, np.array((0, 0, 198)), np.array((180, 86, 255)))
    white_candidates = cv2.bitwise_and(white_candidates, cv2.inRange(gray, 190, 255))

    min_side = min(work_width, work_height)
    close_size = max(3, int(round(min_side * 0.05)) | 1)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_size, close_size))
    edge_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 45, 135)
    nearby_white = cv2.dilate(white_candidates, edge_kernel)
    supported_candidates = cv2.bitwise_or(
        white_candidates,
        cv2.bitwise_and(edges, nearby_white),
    )
    closed = cv2.morphologyEx(supported_candidates, cv2.MORPH_CLOSE, close_kernel)
    contours, hierarchy = cv2.findContours(closed, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    if hierarchy is None:
        return _empty_result(FovStatus.UNCERTAIN, source_rgb, source_sha256, "NO_CENTER_ENCLOSING_WHITE_RIM")

    center = (work_width / 2, work_height / 2)
    plausible: list[tuple[int, float, object]] = []
    image_area = work_width * work_height
    for index, contour in enumerate(contours):
        area_fraction = abs(cv2.contourArea(contour)) / image_area
        if not 0.20 <= area_fraction <= 0.90:
            continue
        x, y, width, height = cv2.boundingRect(contour)
        if width < work_width * 0.48 or height < work_height * 0.48:
            continue
        aspect = width / height
        if not 0.52 <= aspect <= 1.92:
            continue
        if cv2.pointPolygonTest(contour, center, False) < 0:
            continue
        plausible.append((_contour_depth(hierarchy, index), area_fraction, contour))

    if not plausible:
        return _empty_result(FovStatus.UNCERTAIN, source_rgb, source_sha256, "NO_CENTER_ENCLOSING_WHITE_RIM")

    # The deepest center-enclosing contour is the inside edge of a white ring.
    deepest = max(item[0] for item in plausible)
    contour = max((item for item in plausible if item[0] == deepest), key=lambda item: item[1])[2]
    x, y, box_width, box_height = cv2.boundingRect(contour)
    border_guard = max(3, min_side * 0.025)
    if x <= border_guard or y <= border_guard or (
        x + box_width >= work_width - border_guard
        or y + box_height >= work_height - border_guard
    ):
        return _empty_result(FovStatus.UNCERTAIN, source_rgb, source_sha256, "BOUNDARY_TOUCHES_CANVAS")

    ellipse = _ellipse_residual(contour)
    if ellipse is None:
        return _empty_result(FovStatus.UNCERTAIN, source_rgb, source_sha256, "BOUNDARY_SHAPE_UNCERTAIN")
    ellipse_residual, ellipse_aspect = ellipse
    if ellipse_residual > 0.16 or not 0.52 <= ellipse_aspect <= 1.92:
        return _empty_result(FovStatus.UNCERTAIN, source_rgb, source_sha256, "BOUNDARY_SHAPE_UNCERTAIN")

    edge_distance = cv2.distanceTransform(cv2.bitwise_not(edges), cv2.DIST_L2, 3)
    edge_tolerance = max(2.0, min_side * 0.018)
    boundary_points = contour.reshape(-1, 2)
    edge_support = float(np.mean(
        edge_distance[boundary_points[:, 1], boundary_points[:, 0]] <= edge_tolerance
    ))
    color_support_mask = cv2.dilate(white_candidates, edge_kernel)
    color_support = _sample_support(color_support_mask, contour)
    shape_support = max(0.0, 1.0 - ellipse_residual / 0.16)
    confidence = round(0.40 * color_support + 0.35 * edge_support + 0.25 * shape_support, 4)
    if color_support < 0.60 or edge_support < 0.35 or confidence < 0.66:
        return _empty_result(FovStatus.UNCERTAIN, source_rgb, source_sha256, "BOUNDARY_EVIDENCE_WEAK")

    field = np.zeros((work_height, work_width), dtype=np.uint8)
    cv2.drawContours(field, [contour], -1, 255, thickness=cv2.FILLED)
    margin = max(1, round(min_side * 0.006))
    margin_size = margin * 2 + 1
    margin_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (margin_size, margin_size))
    field = cv2.erode(field, margin_kernel, iterations=1)
    if (work_width, work_height) != (source_width, source_height):
        field = cv2.resize(field, (source_width, source_height), interpolation=cv2.INTER_NEAREST)
    field = np.where(field > 0, 255, 0).astype(np.uint8)
    mask = Image.fromarray(field, mode="L")
    final_contours, _ = cv2.findContours(field, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not final_contours:
        return _empty_result(FovStatus.UNCERTAIN, source_rgb, source_sha256, "FIELD_MASK_EMPTY")
    final_contour = max(final_contours, key=cv2.contourArea)
    x, y, box_width, box_height = cv2.boundingRect(final_contour)
    x_max, y_max = x + box_width, y + box_height
    # Keep the contour extracted from the final mask; display geometry must
    # not drift from the pixels authorized for preprocessing.
    boundary = tuple((int(point[0][0]), int(point[0][1])) for point in final_contour)
    field_fraction = float(np.count_nonzero(field) / field.size)
    return WhiteRimFov(
        status=FovStatus.READY,
        field_mask=mask,
        mask_version=FOV_MASK_VERSION,
        mask_sha256=_mask_hash(mask),
        source_rgb_sha256=source_sha256,
        boundary_confidence=confidence,
        field_fraction=round(field_fraction, 6),
        excluded_fraction=round(1.0 - field_fraction, 6),
        bounding_box=(x, y, x_max, y_max),
        boundary=boundary,
        image_width=source_width,
        image_height=source_height,
        reason_code=None,
    )


def prepare_prism_uwf_image(
    original_rgb: Image.Image,
    fov: WhiteRimFov | None = None,
) -> PrismUwfPreparation:
    """Black out pixels outside a validated field without mutating Original."""
    source_rgb = _source_rgb(original_rgb)
    detected = fov if fov is not None else detect_white_rim_fov(source_rgb)
    if detected.source_rgb_sha256 != _source_hash(source_rgb):
        raise FovNotReadyError("FOV_SOURCE_MISMATCH")
    mask_array = _validated_field_mask(detected)
    if detected.bounding_box is None:
        raise FovNotReadyError("FOV_BOUNDING_BOX_MISSING")

    source_array = np.asarray(source_rgb, dtype=np.uint8)
    masked = source_array.copy()
    masked[mask_array == 0] = (0, 0, 0)
    return PrismUwfPreparation(
        masked_rgb=Image.fromarray(masked, mode="RGB"),
        fov=detected,
        bounding_box=detected.bounding_box,
    )


def classify_prism_box(
    fov: WhiteRimFov,
    box: Sequence[float],
    *,
    near_boundary_px: int = 8,
) -> BoxBoundaryClass:
    """Classify a future box while preserving the caller's raw prediction."""
    try:
        if len(box) != 4:
            return BoxBoundaryClass.INVALID_BOX
    except TypeError:
        return BoxBoundaryClass.INVALID_BOX
    try:
        x1, y1, x2, y2 = (float(value) for value in box)
    except (TypeError, ValueError, OverflowError):
        return BoxBoundaryClass.INVALID_BOX
    if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
        return BoxBoundaryClass.INVALID_BOX
    if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
        return BoxBoundaryClass.INVALID_BOX
    if x2 > fov.image_width or y2 > fov.image_height:
        return BoxBoundaryClass.INVALID_BOX
    field = _validated_field_mask(fov) > 0

    left, top = math.floor(x1), math.floor(y1)
    right, bottom = math.ceil(x2), math.ceil(y2)
    box_field = field[top:bottom, left:right]
    if box_field.size == 0:
        return BoxBoundaryClass.INVALID_BOX
    field_coverage = float(np.mean(box_field))
    if field_coverage < 0.5:
        return BoxBoundaryClass.OUTSIDE_ANALYSIS_FIELD
    if field_coverage < 0.999:
        return BoxBoundaryClass.NEAR_CAMERA_RIM

    if cv2 is not None:
        distance = cv2.distanceTransform(field.astype(np.uint8), cv2.DIST_L2, 3)
        if float(np.min(distance[top:bottom, left:right])) <= max(0, near_boundary_px):
            return BoxBoundaryClass.NEAR_CAMERA_RIM
    elif near_boundary_px > 0:
        return BoxBoundaryClass.NEAR_CAMERA_RIM
    return BoxBoundaryClass.INSIDE_ANALYSIS_FIELD
