"""Hash-reviewed USPEC source-RGB preprocessing, versioned independently."""

from __future__ import annotations

from PIL import Image

from ..models.uspec_artifact import PREPROCESSING


MASK_VERSION = "conservative_fov_rim_review_v4"
GRID = 7
PATCH_SIZE = 224
STRIDE = 200
CANVAS_SIZE = 1424
MEAN = (0.5723625, 0.34657937, 0.2374997)
STD = (0.21822436, 0.19240488, 0.17723322)


def _field_mask(rgb):
    import cv2
    import numpy as np

    height, width = rgb.shape[:2]
    scale = min(1.0, 640 / max(height, width))
    small = cv2.resize(
        rgb,
        (round(width * scale), round(height * scale)),
        interpolation=cv2.INTER_AREA,
    )
    small_height, small_width = small.shape[:2]
    visible = (small.max(axis=2) > 18).astype(np.uint8)
    visible = cv2.morphologyEx(
        visible,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
    )
    count, components, stats, _ = cv2.connectedComponentsWithStats(visible, 8)
    if count < 2:
        return np.ones((height, width), dtype=bool), "UNMASKED_FALLBACK"

    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    candidate = (components == largest).astype(np.uint8)
    contours, _ = cv2.findContours(candidate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(candidate, contours, -1, 1, cv2.FILLED)
    candidate = cv2.erode(
        candidate,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
    )

    yy, xx = np.ogrid[:small_height, :small_width]
    central_disk = (
        (xx - small_width / 2) ** 2 + (yy - small_height / 2) ** 2
        < (min(small_height, small_width) * 0.20) ** 2
    )
    central_retention = float(candidate[central_disk].mean())
    coverage = float(candidate.mean())
    if central_retention < 0.995 or not 0.30 <= coverage <= 0.985:
        return np.ones((height, width), dtype=bool), "UNMASKED_FALLBACK"

    mask = cv2.resize(candidate, (width, height), interpolation=cv2.INTER_NEAREST) > 0
    return mask, "FOV_ONLY"


def prepare_patches(image: Image.Image) -> tuple[list[Image.Image], dict[str, str]]:
    """Apply source FOV mask once, then exact RGB letterbox/crop geometry."""
    import numpy as np

    rgb = np.asarray(image.convert("RGB"))
    mask, mask_status = _field_mask(rgb)
    analysis = rgb.copy()
    analysis[~mask] = 0

    height, width = analysis.shape[:2]
    scale = min(CANVAS_SIZE / width, CANVAS_SIZE / height)
    resized = Image.fromarray(analysis).resize(
        (round(width * scale), round(height * scale)),
        Image.Resampling.BILINEAR,
    )
    canvas = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0))
    canvas.paste(resized, ((CANVAS_SIZE - resized.width) // 2, (CANVAS_SIZE - resized.height) // 2))
    patches = [
        canvas.crop((x, y, x + PATCH_SIZE, y + PATCH_SIZE))
        for y in range(0, CANVAS_SIZE - PATCH_SIZE + 1, STRIDE)
        for x in range(0, CANVAS_SIZE - PATCH_SIZE + 1, STRIDE)
    ]
    if len(patches) != GRID * GRID or PREPROCESSING != (
        f"{MASK_VERSION}_rgb_letterbox{CANVAS_SIZE}_{GRID}x{GRID}_stride{STRIDE}_v1"
    ):
        raise RuntimeError("USPEC preprocessing identity is inconsistent")
    return patches, {"mask_status": mask_status, "preprocessing": PREPROCESSING}


def normalize_patches(images: list[Image.Image]):
    import numpy as np
    import torch

    if not images or any(image.mode != "RGB" or image.size != (PATCH_SIZE, PATCH_SIZE) for image in images):
        raise ValueError("USPEC expects RGB 224x224 patches")
    mean = torch.tensor(MEAN, dtype=torch.float32)[:, None, None]
    std = torch.tensor(STD, dtype=torch.float32)[:, None, None]
    pixels = []
    for image in images:
        tensor = torch.from_numpy(np.asarray(image).copy()).permute(2, 0, 1).float() / 255
        pixels.append((tensor - mean) / std)
    return torch.stack(pixels)
