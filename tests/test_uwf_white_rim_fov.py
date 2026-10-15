from __future__ import annotations

from PIL import Image, ImageDraw
import pytest

import dr_support.imaging.uwf_white_rim_fov as fov_module
from dr_support.imaging.uwf_white_rim_fov import (
    BoxBoundaryClass,
    FOV_MASK_VERSION,
    FovNotReadyError,
    FovStatus,
    classify_prism_box,
    detect_white_rim_fov,
    prepare_prism_uwf_image,
)


def synthetic_uwf(
    *,
    incomplete: bool = False,
    asymmetric: bool = False,
    bright_internal_regions: bool = False,
    dark_retina: bool = False,
) -> Image.Image:
    image = Image.new("RGB", (256, 256), (9, 10, 12))
    draw = ImageDraw.Draw(image)
    outer = (31, 24, 225, 232) if asymmetric else (25, 25, 231, 231)
    inner = (41, 34, 215, 222) if asymmetric else (36, 36, 220, 220)
    draw.ellipse(outer, fill=(245, 246, 244))
    retina = (28, 24, 20) if dark_retina else (62, 32, 28)
    draw.ellipse(inner, fill=retina)
    if incomplete:
        draw.rectangle((124, 22, 132, 38), fill=(9, 10, 12))
    if bright_internal_regions:
        draw.ellipse((152, 107, 185, 140), fill=(250, 250, 248))
        for x, y, radius in ((81, 80, 4), (101, 174, 3), (177, 174, 4), (111, 119, 2)):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(250, 250, 248))
    return image


def test_detects_clean_white_ellipse_and_excludes_camera_rim():
    original = synthetic_uwf()
    original_bytes = original.tobytes()

    result = detect_white_rim_fov(original)

    assert result.status is FovStatus.READY
    assert result.reason_code is None
    assert result.mask_version == FOV_MASK_VERSION
    assert result.field_mask is not None
    assert result.mask_sha256 is not None
    assert result.bounding_box is not None
    assert result.boundary
    assert result.field_mask.getpixel((128, 128)) == 255
    assert result.field_mask.getpixel((30, 128)) == 0
    assert all(result.field_mask.getpixel(point) == 255 for point in result.boundary)
    assert 0.35 < result.field_fraction < 0.80
    assert result.excluded_fraction == pytest.approx(1.0 - result.field_fraction)
    assert original.tobytes() == original_bytes


@pytest.mark.parametrize(
    "image",
    [
        synthetic_uwf(incomplete=True),
        synthetic_uwf(asymmetric=True),
        synthetic_uwf(bright_internal_regions=True),
        synthetic_uwf(dark_retina=True),
    ],
    ids=["incomplete-rim", "asymmetric-rim", "bright-disc-and-lesions", "dark-retina"],
)
def test_conservative_geometry_handles_supported_variants(image: Image.Image):
    result = detect_white_rim_fov(image)

    assert result.status is FovStatus.READY
    assert result.field_mask is not None
    assert result.field_mask.getpixel((128, 128)) == 255
    assert result.field_fraction is not None and result.field_fraction > 0.35
    assert result.bounding_box is not None


def test_mask_hash_and_bounding_box_are_deterministic():
    original = synthetic_uwf(asymmetric=True, bright_internal_regions=True)

    first = detect_white_rim_fov(original)
    second = detect_white_rim_fov(original)

    assert first.status is second.status is FovStatus.READY
    assert first.mask_sha256 == second.mask_sha256
    assert first.bounding_box == second.bounding_box
    assert first.boundary == second.boundary


def test_no_white_rim_is_uncertain_and_cannot_be_prepared():
    image = Image.new("RGB", (256, 256), (62, 32, 28))
    draw = ImageDraw.Draw(image)
    draw.ellipse((104, 104, 152, 152), fill=(250, 250, 248))

    result = detect_white_rim_fov(image)

    assert result.status is FovStatus.UNCERTAIN
    assert result.reason_code
    with pytest.raises(FovNotReadyError):
        prepare_prism_uwf_image(image, result)


def test_missing_opencv_is_unavailable_and_fails_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fov_module, "cv2", None)
    monkeypatch.setattr(fov_module, "np", None)

    result = detect_white_rim_fov(synthetic_uwf())

    assert result.status is FovStatus.UNAVAILABLE
    assert result.reason_code == "OPENCV_UNAVAILABLE"
    with pytest.raises(FovNotReadyError):
        prepare_prism_uwf_image(synthetic_uwf(), result)


def test_small_image_is_uncertain_and_fails_closed():
    image = Image.new("RGB", (96, 128), (20, 20, 20))

    result = detect_white_rim_fov(image)

    assert result.status is FovStatus.UNCERTAIN
    assert result.reason_code == "IMAGE_TOO_SMALL"


def test_boundary_touching_canvas_is_uncertain():
    image = Image.new("RGB", (256, 256), (9, 10, 12))
    draw = ImageDraw.Draw(image)
    draw.ellipse((-4, -4, 260, 260), outline=(245, 246, 244), width=8)

    result = detect_white_rim_fov(image)

    assert result.status is FovStatus.UNCERTAIN
    assert result.reason_code in {"BOUNDARY_TOUCHES_CANVAS", "NO_CENTER_ENCLOSING_WHITE_RIM"}


def test_prism_preparation_blacks_outside_on_same_canvas_without_mutation():
    original = synthetic_uwf(bright_internal_regions=True)
    original_bytes = original.tobytes()
    fov = detect_white_rim_fov(original)

    prepared = prepare_prism_uwf_image(original, fov)

    assert prepared.masked_rgb.size == original.size
    assert prepared.bounding_box == fov.bounding_box
    assert prepared.masked_rgb.getpixel((128, 128)) == original.getpixel((128, 128))
    assert prepared.masked_rgb.getpixel((30, 128)) == (0, 0, 0)
    assert original.tobytes() == original_bytes


def test_preparation_rejects_mask_mutation_or_wrong_source():
    original = synthetic_uwf()
    fov = detect_white_rim_fov(original)
    assert fov.status is FovStatus.READY

    assert fov.field_mask is not None
    fov.field_mask.putpixel((128, 128), 0)
    with pytest.raises(FovNotReadyError, match="MASK_HASH_MISMATCH"):
        prepare_prism_uwf_image(original, fov)

    original = synthetic_uwf()
    other = synthetic_uwf(dark_retina=True)
    with pytest.raises(FovNotReadyError, match="SOURCE_MISMATCH"):
        prepare_prism_uwf_image(other, detect_white_rim_fov(original))


def test_box_classifier_marks_inside_outside_rim_and_invalid_boxes():
    fov = detect_white_rim_fov(synthetic_uwf())
    assert fov.status is FovStatus.READY

    assert classify_prism_box(fov, (112, 112, 142, 142)) is BoxBoundaryClass.INSIDE_ANALYSIS_FIELD
    assert classify_prism_box(fov, (2, 112, 16, 142)) is BoxBoundaryClass.OUTSIDE_ANALYSIS_FIELD
    assert classify_prism_box(fov, (36, 112, 54, 142)) is BoxBoundaryClass.NEAR_CAMERA_RIM
    assert classify_prism_box(fov, (40, 40, 40, 50)) is BoxBoundaryClass.INVALID_BOX
    assert classify_prism_box(fov, (-1, 20, 10, 40)) is BoxBoundaryClass.INVALID_BOX
    assert classify_prism_box(fov, (0, 0, float("inf"), 1)) is BoxBoundaryClass.INVALID_BOX


def test_uncertain_detector_state_cannot_classify_boxes():
    image = Image.new("RGB", (256, 256), (30, 20, 18))
    fov = detect_white_rim_fov(image)

    with pytest.raises(FovNotReadyError):
        classify_prism_box(fov, (100, 100, 110, 110))
