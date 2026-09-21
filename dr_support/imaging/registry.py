"""Bounded handler and derivative-builder extension points for S5 lanes."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from PIL import Image

from .contracts import (
    DerivativeArtifact,
    DerivativePurpose,
    IntegrityStatus,
    SourceDimensions,
    SourceMetadata,
    sha256_bytes,
)


RASTER_FORMATS = frozenset({"JPEG", "PNG", "TIFF"})
RASTER_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/tiff"})
RASTER_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff"})
FORMAT_MEDIA_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "TIFF": "image/tiff",
}


class UnsupportedImageHandlerError(ValueError):
    """Raised when no registered handler can safely own a source."""

    status = IntegrityStatus.UNSUPPORTED_FORMAT


class ImageDecodeError(ValueError):
    """Raised when a selected handler cannot decode source bytes."""

    status = IntegrityStatus.DECODE_FAILED


@runtime_checkable
class ImageHandler(Protocol):
    """Minimal adapter contract for format-specific source inspection."""

    name: str
    formats: frozenset[str]
    media_types: frozenset[str]
    extensions: frozenset[str]

    def can_handle(
        self,
        *,
        source_format: str | None = None,
        media_type: str | None = None,
        filename: str | None = None,
    ) -> bool: ...

    def inspect(
        self,
        data: bytes,
        *,
        filename: str | None = None,
        media_type: str | None = None,
    ) -> SourceMetadata: ...


@runtime_checkable
class DerivativeBuilder(Protocol):
    """Hook for later display, analysis, or master derivative lanes."""

    name: str
    purpose: DerivativePurpose

    def can_build(self, source: SourceMetadata) -> bool: ...

    def build(self, source: SourceMetadata, data: bytes) -> DerivativeArtifact: ...


class RasterImageHandler:
    """Read-only Pillow adapter for the existing JPEG/PNG/TIFF baseline."""

    name = "raster"
    formats = RASTER_FORMATS
    media_types = RASTER_MEDIA_TYPES
    extensions = RASTER_EXTENSIONS

    def can_handle(
        self,
        *,
        source_format: str | None = None,
        media_type: str | None = None,
        filename: str | None = None,
    ) -> bool:
        if source_format is not None:
            return source_format.upper() in self.formats
        if media_type is not None:
            return media_type.lower().split(";", 1)[0].strip() in self.media_types
        return bool(filename and Path(filename).suffix.lower() in self.extensions)

    def inspect(
        self,
        data: bytes,
        *,
        filename: str | None = None,
        media_type: str | None = None,
    ) -> SourceMetadata:
        if not isinstance(data, bytes) or not data:
            raise ImageDecodeError("Raster source bytes are empty or invalid")

        try:
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                image_format = (image.format or "").upper()
                if image_format not in self.formats:
                    raise ImageDecodeError("Raster format is unsupported")
                width, height = image.size
                channels = len(image.getbands())
                bit_depth = _bit_depth(image.mode)
        except ImageDecodeError:
            raise
        except Exception as exc:
            raise ImageDecodeError("Raster source could not be decoded") from exc

        actual_media_type = FORMAT_MEDIA_TYPES[image_format]
        return SourceMetadata(
            source_sha256=sha256_bytes(data),
            source_format=image_format,
            source_media_type=actual_media_type,
            dimensions=SourceDimensions(
                width=width,
                height=height,
                bit_depth=bit_depth,
                channels=channels,
            ),
            integrity_status=IntegrityStatus.OK,
        )


def _bit_depth(mode: str) -> int | None:
    if mode in {"1", "L", "LA", "P", "RGB", "RGBA", "CMYK", "YCbCr"}:
        return 8
    if mode.startswith("I;16"):
        return 16
    if mode == "I":
        return 32
    if mode == "F":
        return 32
    return None


class ImageHandlerRegistry:
    """Resolve a source to exactly one registered format handler."""

    def __init__(self, handlers: Iterable[ImageHandler] = ()) -> None:
        self._handlers: list[ImageHandler] = []
        for handler in handlers:
            self.register(handler)

    @property
    def handlers(self) -> tuple[ImageHandler, ...]:
        return tuple(self._handlers)

    def register(self, handler: ImageHandler) -> ImageHandler:
        name = getattr(handler, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise TypeError("Image handler must provide a non-empty name")
        if any(existing.name == name for existing in self._handlers):
            raise ValueError(f"Image handler is already registered: {name}")
        self._handlers.append(handler)
        return handler

    def find(
        self,
        *,
        source_format: str | None = None,
        media_type: str | None = None,
        filename: str | None = None,
    ) -> ImageHandler | None:
        for handler in self._handlers:
            if handler.can_handle(
                source_format=source_format,
                media_type=media_type,
                filename=filename,
            ):
                return handler
        return None

    def resolve(
        self,
        *,
        source_format: str | None = None,
        media_type: str | None = None,
        filename: str | None = None,
    ) -> ImageHandler:
        handler = self.find(
            source_format=source_format,
            media_type=media_type,
            filename=filename,
        )
        if handler is None:
            raise UnsupportedImageHandlerError(
                "No image handler is registered for the requested source format"
            )
        return handler

    require = resolve

    def inspect(
        self,
        data: bytes,
        *,
        source_format: str | None = None,
        media_type: str | None = None,
        filename: str | None = None,
    ) -> SourceMetadata:
        handler = self.resolve(
            source_format=source_format,
            media_type=media_type,
            filename=filename,
        )
        return handler.inspect(data, filename=filename, media_type=media_type)


class DerivativeBuilderRegistry:
    """Register purpose-specific derivative builders without coupling lanes."""

    def __init__(self, builders: Iterable[DerivativeBuilder] = ()) -> None:
        self._builders: list[DerivativeBuilder] = []
        for builder in builders:
            self.register(builder)

    @property
    def builders(self) -> tuple[DerivativeBuilder, ...]:
        return tuple(self._builders)

    def register(self, builder: DerivativeBuilder) -> DerivativeBuilder:
        name = getattr(builder, "name", None)
        purpose = getattr(builder, "purpose", None)
        if not isinstance(name, str) or not name.strip():
            raise TypeError("Derivative builder must provide a non-empty name")
        if not isinstance(purpose, DerivativePurpose):
            try:
                purpose = DerivativePurpose(purpose)
            except (TypeError, ValueError) as exc:
                raise TypeError("Derivative builder must provide a valid purpose") from exc
            builder.purpose = purpose
        if any(existing.name == name for existing in self._builders):
            raise ValueError(f"Derivative builder is already registered: {name}")
        self._builders.append(builder)
        return builder

    def find(self, purpose: DerivativePurpose) -> tuple[DerivativeBuilder, ...]:
        selected = DerivativePurpose(purpose)
        return tuple(builder for builder in self._builders if builder.purpose == selected)


def default_image_handler_registry() -> ImageHandlerRegistry:
    """Return the baseline registry; future lanes can register new handlers."""

    return ImageHandlerRegistry((RasterImageHandler(),))


def default_dicom_image_handler_registry() -> ImageHandlerRegistry:
    """Return the raster registry with the optional local DICOM handler."""

    from .dicom import DicomImageHandler

    return ImageHandlerRegistry((RasterImageHandler(), DicomImageHandler()))


__all__ = [
    "DerivativeBuilder",
    "DerivativeBuilderRegistry",
    "ImageDecodeError",
    "ImageHandler",
    "ImageHandlerRegistry",
    "RasterImageHandler",
    "UnsupportedImageHandlerError",
    "default_dicom_image_handler_registry",
    "default_image_handler_registry",
]
