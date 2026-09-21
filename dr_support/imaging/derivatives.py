"""Deterministic display and analysis representations for admitted images.

The source bytes stay owned by ``BridgeImage``.  This module only prepares
read-only representations and records the mapping needed to return model
geometry to canonical review-image pixels.
"""

from __future__ import annotations

import io
import base64
from dataclasses import dataclass
from typing import Literal

from PIL import Image
from pydantic import Field

from ..images import BridgeImage
from ..contracts._schema import Contract
from .contracts import (
    DerivativeLineage,
    DerivativePurpose,
    SourceDimensions,
    SourceMetadata,
    lineage_for_bytes,
)
from .registry import default_image_handler_registry


DISPLAY_SOURCE_TRANSFORM = "display-source-v1"
DISPLAY_TIFF_PNG_TRANSFORM = "display-tiff-png-rgb-v1"
ANALYSIS_SOURCE_TRANSFORM = "analysis-source-v1"
ANALYSIS_TIFF_PNG_TRANSFORM = "analysis-tiff-png-rgb-v1"
REMOTE_IMAGE_B64_LIMIT = 20_000_000


class DerivativeError(RuntimeError):
    """Raised when a safe deterministic representation cannot be prepared."""


class DerivativePayloadTooLargeError(DerivativeError):
    """Raised when a validated representation exceeds the model API limit."""


class CoordinateMapping(Contract):
    """Reversible scale mapping from analysis pixels to review pixels."""

    kind: Literal["IDENTITY", "SCALE"]
    canonical_width: int = Field(gt=0)
    canonical_height: int = Field(gt=0)
    analysis_width: int = Field(gt=0)
    analysis_height: int = Field(gt=0)
    scale_x: float = Field(gt=0)
    scale_y: float = Field(gt=0)

    @classmethod
    def for_dimensions(
        cls,
        canonical: SourceDimensions,
        analysis: SourceDimensions,
    ) -> "CoordinateMapping":
        scale_x = canonical.width / analysis.width
        scale_y = canonical.height / analysis.height
        kind = "IDENTITY" if canonical.width == analysis.width and canonical.height == analysis.height else "SCALE"
        return cls(
            kind=kind,
            canonical_width=canonical.width,
            canonical_height=canonical.height,
            analysis_width=analysis.width,
            analysis_height=analysis.height,
            scale_x=scale_x,
            scale_y=scale_y,
        )

    def map_point(self, x: float, y: float) -> tuple[float, float]:
        if not 0 <= x <= self.analysis_width or not 0 <= y <= self.analysis_height:
            raise DerivativeError("Analysis geometry is outside the analysis image")
        return x * self.scale_x, y * self.scale_y

    def map_review_point(self, x: float, y: float) -> tuple[float, float]:
        """Map canonical review pixels back into analysis pixels."""

        if not 0 <= x <= self.canonical_width or not 0 <= y <= self.canonical_height:
            raise DerivativeError("Review geometry is outside the canonical image")
        return x / self.scale_x, y / self.scale_y

    def map_rectangle(self, rectangle: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        x1, y1 = self.map_point(rectangle[0], rectangle[1])
        x2, y2 = self.map_point(rectangle[2], rectangle[3])
        if not x1 < x2 or not y1 < y2:
            raise DerivativeError("Analysis geometry is not a valid rectangle")
        return x1, y1, x2, y2


@dataclass(frozen=True)
class PreparedDerivative:
    """Bytes plus the additive provenance needed by a delivery consumer."""

    data: bytes
    media_type: str
    source: SourceMetadata
    lineage: DerivativeLineage
    coordinate_mapping: CoordinateMapping

    @property
    def analysis_dimensions(self) -> SourceDimensions:
        return SourceDimensions(
            width=self.lineage.width,
            height=self.lineage.height,
            bit_depth=self.lineage.bit_depth,
        )

    def audit_record(self) -> dict:
        """Return a JSON-safe source-to-analysis record for the case audit."""

        record = {
            "source_sha256": self.source.source_sha256,
            "derivative_sha256": self.lineage.derivative_sha256,
            "purpose": self.lineage.purpose,
            "transform_id": self.lineage.transform_id,
            "transform_description": self.lineage.transform_description,
            "source_dimensions": self.source.dimensions.model_dump(mode="json"),
            "analysis_dimensions": self.analysis_dimensions.model_dump(mode="json"),
            "coordinate_mapping": self.coordinate_mapping.model_dump(mode="json"),
            "lineage": self.lineage.model_dump(mode="json"),
        }
        if self.lineage.purpose is DerivativePurpose.ANALYSIS:
            record["analysis_sha256"] = self.lineage.derivative_sha256
        return record


def map_lesion_result_to_review(result, mapping: CoordinateMapping):
    """Map provider lesion boxes back to canonical review-image pixels."""

    if result.width != mapping.analysis_width or result.height != mapping.analysis_height:
        raise DerivativeError("Model lesion dimensions do not match the analysis payload")
    lesions = [
        lesion.model_copy(update={"rectangle": mapping.map_rectangle(lesion.rectangle)})
        for lesion in result.lesions
    ]
    return result.model_copy(
        update={
            "width": mapping.canonical_width,
            "height": mapping.canonical_height,
            "lesions": lesions,
        }
    )


class DerivativeService:
    """Cache deterministic representations by source identity and transform."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, DerivativePurpose], PreparedDerivative] = {}

    def prepare_display(self, image: BridgeImage) -> PreparedDerivative:
        return self._prepare(image, DerivativePurpose.DISPLAY)

    def prepare_analysis(self, image: BridgeImage) -> PreparedDerivative:
        return self._prepare(image, DerivativePurpose.ANALYSIS)

    def analysis_image(self, image: BridgeImage) -> tuple[BridgeImage, PreparedDerivative]:
        prepared = self.prepare_analysis(image)
        return (
            BridgeImage(
                image_id=image.image_id,
                data=prepared.data,
                source_type=image.source_type,
                source=image.source,
                modality=image.modality,
                filename=image.filename,
                media_type=prepared.media_type,
            ),
            prepared,
        )

    def _prepare(self, image: BridgeImage, purpose: DerivativePurpose) -> PreparedDerivative:
        source_sha256 = image.sha256
        key = (source_sha256, purpose)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        try:
            source = default_image_handler_registry().inspect(
                image.data,
                filename=image.filename,
                media_type=image.media_type,
            )
        except Exception as exc:
            raise DerivativeError("The admitted image could not be inspected for delivery") from exc

        if source.source_format in {"JPEG", "PNG"}:
            data = image.data
            media_type = source.source_media_type
            output_format = source.source_format
            transform_id = (
                DISPLAY_SOURCE_TRANSFORM if purpose is DerivativePurpose.DISPLAY
                else ANALYSIS_SOURCE_TRANSFORM
            )
            description = "Original browser/model-compatible source bytes reused"
        elif source.source_format == "TIFF":
            data = _tiff_to_png(image.data)
            media_type = "image/png"
            output_format = "PNG"
            transform_id = (
                DISPLAY_TIFF_PNG_TRANSFORM if purpose is DerivativePurpose.DISPLAY
                else ANALYSIS_TIFF_PNG_TRANSFORM
            )
            description = "Deterministic TIFF decode and RGB PNG representation; source bytes unchanged"
        else:
            raise DerivativeError("This image format has no validated delivery representation")

        output_dimensions = _dimensions(data)
        if purpose is DerivativePurpose.ANALYSIS and len(base64.b64encode(data)) > REMOTE_IMAGE_B64_LIMIT:
            raise DerivativePayloadTooLargeError(
                "The analysis representation exceeds the remote model payload limit; "
                "no automatic downscaling or recompression was applied"
            )
        mapping = CoordinateMapping.for_dimensions(source.dimensions, output_dimensions)
        lineage = lineage_for_bytes(
            source_sha256=source.source_sha256,
            data=data,
            purpose=purpose,
            output_format=output_format,
            media_type=media_type,
            width=output_dimensions.width,
            height=output_dimensions.height,
            bit_depth=output_dimensions.bit_depth,
            transform_id=transform_id,
            transform_description=description,
            coordinate_space="analysis_pixels",
        )
        prepared = PreparedDerivative(
            data=data,
            media_type=media_type,
            source=source,
            lineage=lineage,
            coordinate_mapping=mapping,
        )
        self._cache[key] = prepared
        return prepared


def _dimensions(data: bytes) -> SourceDimensions:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return SourceDimensions(width=image.width, height=image.height, bit_depth=8, channels=len(image.getbands()))
    except Exception as exc:
        raise DerivativeError("The generated image representation could not be decoded") from exc


def _tiff_to_png(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise DerivativeError("Multi-frame TIFF display requires explicit frame selection")
            image.load()
            rgb = image.convert("RGB")
            output = io.BytesIO()
            rgb.save(output, format="PNG", optimize=False, compress_level=9)
            return output.getvalue()
    except DerivativeError:
        raise
    except Exception as exc:
        raise DerivativeError("The TIFF source could not be converted to a browser-safe representation") from exc


__all__ = [
    "ANALYSIS_SOURCE_TRANSFORM",
    "ANALYSIS_TIFF_PNG_TRANSFORM",
    "CoordinateMapping",
    "DerivativeError",
    "DerivativePayloadTooLargeError",
    "DerivativeService",
    "DISPLAY_SOURCE_TRANSFORM",
    "DISPLAY_TIFF_PNG_TRANSFORM",
    "PreparedDerivative",
    "REMOTE_IMAGE_B64_LIMIT",
    "map_lesion_result_to_review",
]
