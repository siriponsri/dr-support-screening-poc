"""Conservative, local-only image discovery and admission rules."""

from __future__ import annotations

import hashlib
import io
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from ..contracts import AdmissionMetadata
from ..images import BridgeImage


SUPPORTED_INPUT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

MIN_REVIEW_DIMENSION = 128
MIN_ASPECT_RATIO = 0.45
MAX_ASPECT_RATIO = 2.4


@dataclass(frozen=True)
class AdmissionScan:
    images: dict[str, BridgeImage]
    records: dict[str, dict]
    warnings: list[str]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_reference(filename: str) -> str:
    # Keep the audit reference useful without exposing the workspace's absolute path.
    return f"WORKSPACE_INPUT/{filename.replace(chr(92), '/') }"


def _image_id_for_unreadable(reference: str) -> str:
    return "invalid-" + hashlib.sha256(reference.encode("utf-8")).hexdigest()


def _metadata(
    *,
    image_id: str,
    source_reference: str,
    filename: str,
    extension: str,
    file_size_bytes: int,
    width: int | None,
    height: int | None,
    mode: str | None,
    modality_admission: str,
    quality_state: str,
    admission_reason_code: str,
    quality_reason_code: str | None,
    method: str = "AUTOMATIC",
    created_at: str | None = None,
    updated_at: str | None = None,
) -> dict:
    now = updated_at or utc_now()
    return AdmissionMetadata(
        image_id=image_id,
        source_reference=source_reference,
        filename=filename,
        file_extension=extension,
        file_size_bytes=file_size_bytes,
        width=width,
        height=height,
        channels_or_mode=mode,
        modality_admission=modality_admission,
        quality_state=quality_state,
        admission_method=method,
        admission_reason_code=admission_reason_code,
        quality_reason_code=quality_reason_code,
        created_at=created_at or now,
        updated_at=now,
    ).model_dump(mode="json")


def _invalid_record(
    *,
    image_id: str,
    source_reference: str,
    filename: str,
    extension: str,
    file_size_bytes: int,
    reason: str,
) -> dict:
    return _metadata(
        image_id=image_id,
        source_reference=source_reference,
        filename=filename,
        extension=extension,
        file_size_bytes=file_size_bytes,
        width=None,
        height=None,
        mode=None,
        modality_admission="REJECTED_INVALID",
        quality_state="NOT_EVALUATED",
        admission_reason_code=reason,
        quality_reason_code=None,
    )


def _sample_statistics(image: Image.Image) -> tuple[float, float, float, float, float, float, float]:
    sample = image.copy()
    sample.thumbnail((96, 96))
    rgb = sample.convert("RGB")
    pixels = list(rgb.getdata())
    if not pixels:
        return (0.0,) * 7

    luminance = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels]
    mean_r = statistics.fmean(pixel[0] for pixel in pixels)
    mean_g = statistics.fmean(pixel[1] for pixel in pixels)
    mean_b = statistics.fmean(pixel[2] for pixel in pixels)
    mean_luma = statistics.fmean(luminance)
    luma_std = statistics.pstdev(luminance) if len(luminance) > 1 else 0.0

    width, height = rgb.size
    center = [
        pixels[y * width + x]
        for y in range(height // 4, max(height // 4 + 1, height * 3 // 4))
        for x in range(width // 4, max(width // 4 + 1, width * 3 // 4))
    ]
    edge = [
        pixels[y * width + x]
        for y in range(height)
        for x in range(width)
        if x < max(1, width // 8)
        or x >= width - max(1, width // 8)
        or y < max(1, height // 8)
        or y >= height - max(1, height // 8)
    ]
    center_luma = statistics.fmean(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in center)
    edge_luma = statistics.fmean(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in edge)
    red_dominant_fraction = sum(
        1 for r, g, b in pixels if r > g * 1.35 and g > b * 1.08
    ) / len(pixels)
    return (
        mean_r,
        mean_g,
        mean_b,
        mean_luma,
        luma_std,
        center_luma - edge_luma,
        red_dominant_fraction,
    )


def _classify_decoded(image: Image.Image) -> tuple[str, str, str | None]:
    width, height = image.size
    ratio = width / height if height else math.inf
    stats = _sample_statistics(image)
    mean_r, mean_g, mean_b, mean_luma, luma_std, center_edge_delta, red_fraction = stats

    quality_reason = None
    if min(width, height) < MIN_REVIEW_DIMENSION:
        quality_reason = "VERY_SMALL_IMAGE"
    elif ratio < MIN_ASPECT_RATIO or ratio > MAX_ASPECT_RATIO:
        quality_reason = "EXTREME_ASPECT_RATIO"
    elif luma_std < 8:
        quality_reason = "NEAR_UNIFORM_IMAGE"
    elif mean_luma < 12 or mean_luma > 245:
        quality_reason = "EXTREME_BRIGHTNESS"

    geometry_signal = MIN_ASPECT_RATIO <= ratio <= MAX_ASPECT_RATIO
    color_signal = mean_r > mean_g * 1.45 and mean_g > mean_b * 1.08 and red_fraction >= 0.40
    texture_signal = luma_std >= 12
    field_signal = center_edge_delta >= 10 or (mean_luma < 150 and red_fraction >= 0.55)
    fundus_signals = sum((geometry_signal, color_signal, texture_signal, field_signal))

    # Four weak signals are deliberately required for automatic acceptance. A readable
    # image that misses any signal remains reviewable instead of being rejected.
    modality = "FUNDUS_ACCEPTED" if quality_reason is None and fundus_signals >= 4 else "NEEDS_REVIEW"
    quality = "NEEDS_REVIEW" if quality_reason else "NOT_EVALUATED"
    return modality, quality, quality_reason


def inspect_file(path: Path, *, source_reference: str | None = None) -> tuple[dict, BridgeImage | None]:
    """Inspect one top-level input file without modifying it."""
    filename = path.name
    extension = path.suffix.lower() or "[none]"
    reference = source_reference or _source_reference(filename)
    try:
        data = path.read_bytes()
    except OSError:
        return (
            _invalid_record(
                image_id=_image_id_for_unreadable(reference),
                source_reference=reference,
                filename=filename,
                extension=extension,
                file_size_bytes=0,
                reason="FILE_READ_FAILED",
            ),
            None,
        )

    image_id = hashlib.sha256(data).hexdigest()
    if extension not in SUPPORTED_INPUT_TYPES:
        return (
            _invalid_record(
                image_id=image_id,
                source_reference=reference,
                filename=filename,
                extension=extension,
                file_size_bytes=len(data),
                reason="UNSUPPORTED_FORMAT",
            ),
            None,
        )

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            width, height = image.size
            mode = image.mode
            if width <= 0 or height <= 0:
                raise ValueError("invalid dimensions")
            modality, quality, quality_reason = _classify_decoded(image)
    except Exception:
        return (
            _invalid_record(
                image_id=image_id,
                source_reference=reference,
                filename=filename,
                extension=extension,
                file_size_bytes=len(data),
                reason="DECODE_FAILED",
            ),
            None,
        )

    record = _metadata(
        image_id=image_id,
        source_reference=reference,
        filename=filename,
        extension=extension,
        file_size_bytes=len(data),
        width=width,
        height=height,
        mode=mode,
        modality_admission=modality,
        quality_state=quality,
        admission_reason_code="FUNDUS_PLAUSIBLE" if modality == "FUNDUS_ACCEPTED" else "FUNDUS_UNCERTAIN",
        quality_reason_code=quality_reason,
    )
    return (
        record,
        BridgeImage(
            image_id,
            data,
            "PUBLIC",
            "WORKSPACE_INPUT",
            filename=filename,
            media_type=SUPPORTED_INPUT_TYPES[extension],
        ),
    )


def inspect_bytes(
    data: bytes,
    *,
    image_id: str,
    filename: str,
    source_reference: str,
) -> dict:
    """Apply the same conservative rules to an API payload without a workspace file."""
    extension = Path(filename).suffix.lower() or "[payload]"
    format_extensions = {"JPEG": ".jpg", "PNG": ".png", "TIFF": ".tiff"}
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            detected_extension = format_extensions.get(image.format or "")
            if detected_extension is None:
                return _invalid_record(
                    image_id=image_id,
                    source_reference=source_reference,
                    filename=filename,
                    extension=extension,
                    file_size_bytes=len(data),
                    reason="UNSUPPORTED_FORMAT",
                )
            extension = detected_extension
            width, height = image.size
            if width <= 0 or height <= 0:
                raise ValueError("invalid dimensions")
            mode = image.mode
            modality, quality, quality_reason = _classify_decoded(image)
    except Exception:
        return _invalid_record(
            image_id=image_id,
            source_reference=source_reference,
            filename=filename,
            extension=extension,
            file_size_bytes=len(data),
            reason="DECODE_FAILED",
        )

    return _metadata(
        image_id=image_id,
        source_reference=source_reference,
        filename=filename,
        extension=extension,
        file_size_bytes=len(data),
        width=width,
        height=height,
        mode=mode,
        modality_admission=modality,
        quality_state=quality,
        admission_reason_code="FUNDUS_PLAUSIBLE" if modality == "FUNDUS_ACCEPTED" else "FUNDUS_UNCERTAIN",
        quality_reason_code=quality_reason,
    )


def legacy_admission(image: BridgeImage) -> dict:
    """Give pre-S2A registry entries an explicit non-gradability default."""
    filename = image.filename or f"{image.image_id}.jpg"
    extension = Path(filename).suffix.lower() or ".jpg"
    try:
        with Image.open(io.BytesIO(image.data)) as pil:
            width, height = pil.size
            mode = pil.mode
    except Exception:
        width = height = None
        mode = None
    return _metadata(
        image_id=image.image_id,
        source_reference=image.source,
        filename=filename,
        extension=extension,
        file_size_bytes=len(image.data),
        width=width,
        height=height,
        mode=mode,
        modality_admission="FUNDUS_ACCEPTED",
        quality_state="NOT_EVALUATED",
        admission_reason_code="LEGACY_ADMITTED",
        quality_reason_code=None,
        method="LEGACY_COMPAT",
    )


def is_inference_eligible(record: dict) -> bool:
    return (
        record.get("modality_admission") == "FUNDUS_ACCEPTED"
        and record.get("quality_state") in {"GRADABLE", "NOT_EVALUATED"}
    )


def clinician_view(record: dict) -> dict:
    modality = record.get("modality_admission")
    quality = record.get("quality_state")
    if modality == "REJECTED_INVALID":
        return {
            "label": "Cannot analyze",
            "note": "This file could not be read as a supported image.",
            "tone": "danger",
            "action_required": False,
        }
    if modality == "REJECTED_NON_FUNDUS":
        return {
            "label": "Cannot analyze",
            "note": "This image is not eligible for retinal DR analysis.",
            "tone": "danger",
            "action_required": False,
        }
    if quality == "UNGRADABLE":
        return {
            "label": "Image quality issue",
            "note": "Image quality is not suitable for automated assessment.",
            "tone": "danger",
            "action_required": True,
        }
    if quality == "NEEDS_REVIEW":
        return {
            "label": "Image quality review",
            "note": "Please confirm image quality before analysis.",
            "tone": "warning",
            "action_required": True,
        }
    if modality == "NEEDS_REVIEW":
        return {
            "label": "Needs review",
            "note": "Please confirm this image before analysis.",
            "tone": "warning",
            "action_required": True,
        }
    return {
        "label": "Ready for analysis",
        "note": "Retinal image accepted for automated analysis.",
        "tone": "success",
        "action_required": False,
    }


def scan_input_folder(folder: str | Path) -> AdmissionScan:
    """Scan one workspace folder, top-level only, in deterministic order."""
    root = Path(folder)
    if not root.is_dir():
        return AdmissionScan({}, {}, ["Input folder is unavailable."])

    try:
        paths = sorted(
            (path for path in root.iterdir() if path.is_file() and not path.is_symlink()),
            key=lambda path: path.name.casefold(),
        )
    except OSError:
        return AdmissionScan({}, {}, ["Input folder is unavailable."])

    images: dict[str, BridgeImage] = {}
    records: dict[str, dict] = {}
    warnings: list[str] = []
    for path in paths:
        try:
            record, image = inspect_file(path)
        except Exception as exc:  # One unexpected file must not stop the scan.
            reference = _source_reference(path.name)
            record = _invalid_record(
                image_id=_image_id_for_unreadable(reference),
                source_reference=reference,
                filename=path.name,
                extension=path.suffix.lower() or "[none]",
                file_size_bytes=0,
                reason="ADMISSION_RULE_ERROR",
            )
            image = None
            warnings.append(f"{path.name}: admission could not be completed ({type(exc).__name__}).")
        records.setdefault(record["image_id"], record)
        if image is not None:
            images.setdefault(image.image_id, image)
    return AdmissionScan(images, records, warnings)
