"""Conservative, deterministic UWF retinal-field preparation.

This color/geometry screen is an engineering boundary, not a validated
segmentation or a clinical quality judgment. Ambiguous images remain available
for human review without an analysis representation.
"""

from __future__ import annotations

import hashlib
import struct
from collections import deque
from dataclasses import dataclass

from PIL import Image, ImageFilter


class RetinalFieldNeedsReview(ValueError):
    """A bounded retinal field could not be established with confidence."""


@dataclass(frozen=True)
class RetinalField:
    mask: Image.Image
    mask_sha256: str
    valid_fraction: float


def _largest_component(bits: bytearray, width: int, height: int) -> tuple[bytearray, int, int]:
    seen = bytearray(len(bits))
    largest = bytearray(len(bits))
    best = runner_up = 0
    for start, active in enumerate(bits):
        if not active or seen[start]:
            continue
        component = []
        queue = deque([start])
        seen[start] = 1
        while queue:
            index = queue.popleft()
            component.append(index)
            x, y = index % width, index // width
            for neighbor in (index - 1 if x else -1, index + 1 if x + 1 < width else -1,
                             index - width if y else -1, index + width if y + 1 < height else -1):
                if neighbor >= 0 and bits[neighbor] and not seen[neighbor]:
                    seen[neighbor] = 1
                    queue.append(neighbor)
        count = len(component)
        if count > best:
            runner_up, best = best, count
            largest = bytearray(len(bits))
            for index in component:
                largest[index] = 1
        else:
            runner_up = max(runner_up, count)
    return largest, best, runner_up


def _fill_enclosed_holes(bits: bytearray, width: int, height: int) -> bytearray:
    """Keep dark retinal vessels/lesions inside the retinal silhouette."""
    exterior = bytearray(len(bits))
    queue = deque()
    for index in list(range(width)) + list(range((height - 1) * width, height * width)) + [
        y * width + edge for y in range(height) for edge in (0, width - 1)
    ]:
        if not bits[index] and not exterior[index]:
            exterior[index] = 1
            queue.append(index)
    while queue:
        index = queue.popleft()
        x, y = index % width, index // width
        for neighbor in (index - 1 if x else -1, index + 1 if x + 1 < width else -1,
                         index - width if y else -1, index + width if y + 1 < height else -1):
            if neighbor >= 0 and not bits[neighbor] and not exterior[neighbor]:
                exterior[neighbor] = 1
                queue.append(neighbor)
    return bytearray(0 if value else 255 for value in exterior)


def prepare_retinal_field(source: Image.Image) -> RetinalField:
    """Return a same-canvas mask only for a single clear, bounded red field.

    Work at a fixed maximum 512-pixel side for bounded cost, then use nearest
    neighbor expansion. A 3-pixel erosion removes the uncertain edge/rim.
    Missing, clipped, fragmented, or nearly full-frame fields need review.
    """
    if min(source.size) < 128:
        raise RetinalFieldNeedsReview("IMAGE_TOO_SMALL")
    small = source.convert("RGB")
    small.thumbnail((512, 512), Image.Resampling.BILINEAR)
    width, height = small.size
    rgb_bytes = small.tobytes()
    threshold = Image.new("L", small.size)
    threshold.putdata([
        255 if r >= 40 and r > g * 1.18 and r - b >= 20 and g >= b * 0.72 else 0
        for r, g, b in zip(rgb_bytes[0::3], rgb_bytes[1::3], rgb_bytes[2::3])
    ])
    # Remove isolated color noise before looking for one connected field.
    threshold = threshold.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    bits = bytearray(1 if value else 0 for value in threshold.tobytes())
    component, count, runner_up = _largest_component(bits, width, height)
    if count < width * height * 0.20 or runner_up > count * 0.04:
        raise RetinalFieldNeedsReview("FIELD_NOT_ISOLATED")
    if not component[(height // 2) * width + width // 2]:
        raise RetinalFieldNeedsReview("FIELD_NOT_CENTERED")
    field = _fill_enclosed_holes(component, width, height)
    bounds = Image.frombytes("L", small.size, bytes(field)).getbbox()
    if bounds is None or (bounds[0] < 3 or bounds[1] < 3 or bounds[2] > width - 3 or bounds[3] > height - 3):
        raise RetinalFieldNeedsReview("FIELD_TOUCHES_CANVAS")
    if bounds[2] - bounds[0] < width * 0.50 or bounds[3] - bounds[1] < height * 0.50:
        raise RetinalFieldNeedsReview("FIELD_TOO_NARROW")
    # Preserve interior detail while excluding uncertain silhouette edges.
    mask = Image.frombytes("L", small.size, bytes(field)).filter(ImageFilter.MinFilter(5))
    mask = mask.resize(source.size, Image.Resampling.NEAREST)
    mask_bytes = mask.tobytes()
    valid_fraction = mask_bytes.count(255) / (source.width * source.height)
    if not 0.20 <= valid_fraction <= 0.85:
        raise RetinalFieldNeedsReview("FIELD_AREA_UNCERTAIN")
    identity = struct.pack(">II", source.width, source.height) + mask_bytes
    return RetinalField(mask, hashlib.sha256(identity).hexdigest(), valid_fraction)
