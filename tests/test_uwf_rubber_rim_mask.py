"""Mask A (rubber rim only) on synthetic UWF-like pictures: no clinical claim, geometry and colour rules only."""
import numpy as np
from PIL import Image, ImageDraw

from dr_support.imaging.uwf_rubber_rim_mask import MASK_A_VERSION, detect_rubber_rim_mask, mask_hash
from dr_support.imaging.uwf_white_rim_fov import FovStatus

W, H = 640, 300


def picture(rim_colour=(210, 230, 40), retina=(140, 60, 20), spot=None, full_width=False):
    image = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    if full_width:
        # Retina fills the frame; the rim is a crescent near the right border (visible at x 580 to 600).
        draw.rectangle((0, 0, W, H), fill=retina)
        draw.ellipse((580, -20, 720, 320), fill=rim_colour)
        draw.ellipse((600, 0, 740, 300), fill=retina)
    else:
        # Round picture area (x 140 to 500) with a rubber rim crescent outside it on the right (x 500 to 530).
        draw.ellipse((140, 10, 500, 290), fill=retina)
        draw.ellipse((430, 20, 530, 280), fill=rim_colour)
        draw.ellipse((405, 35, 495, 265), fill=retina)
    if spot:
        draw.ellipse(spot, fill=(230, 200, 60))   # Yellow lesion-like spot inside the retina.
    return image


def kept(fov, x, y):
    return np.asarray(fov.field_mask)[y, x] == 255


def test_the_rubber_rim_is_removed_and_the_retina_kept():
    fov = detect_rubber_rim_mask(picture())
    assert fov.status == FovStatus.READY and fov.mask_version == MASK_A_VERSION
    assert fov.field_mask.size == (W, H) and set(np.unique(np.asarray(fov.field_mask))) <= {0, 255}
    assert kept(fov, 320, 150)            # Centre of the retina.
    assert not kept(fov, 515, 150)        # On the rubber rim.
    assert not kept(fov, 20, 20)          # Black frame.
    assert fov.mask_sha256 == mask_hash(fov.field_mask)


def test_yellow_spots_inside_the_retina_are_never_masked():
    fov = detect_rubber_rim_mask(picture(spot=(250, 120, 290, 160)))
    assert kept(fov, 270, 140)


def test_an_orange_rim_is_masked_too():
    fov = detect_rubber_rim_mask(picture(rim_colour=(245, 150, 20)))
    assert not kept(fov, 515, 150) and kept(fov, 320, 150)


def test_a_green_tinted_retina_is_not_mistaken_for_rim():
    fov = detect_rubber_rim_mask(picture(retina=(50, 70, 5)))
    assert kept(fov, 320, 150) and kept(fov, 200, 150) and not kept(fov, 515, 150)


def test_a_full_width_picture_still_loses_its_rim():
    fov = detect_rubber_rim_mask(picture(full_width=True))
    assert fov.status == FovStatus.READY and not kept(fov, 590, 150) and kept(fov, 300, 150)


def test_without_a_usable_area_no_mask_is_made_and_the_original_is_used():
    fov = detect_rubber_rim_mask(Image.new("RGB", (W, H), (0, 0, 0)))
    assert fov.status == FovStatus.UNAVAILABLE and fov.field_mask is None and fov.mask_sha256 is None


def test_every_side_pins_the_same_mask_version():
    from dr_support.providers import prism_bound
    from dr_support.services import prism_preview, prism_remote_transport
    assert prism_bound.MASK_VERSION == prism_preview.MASK_VERSION == prism_remote_transport.MASK_VERSION == MASK_A_VERSION
