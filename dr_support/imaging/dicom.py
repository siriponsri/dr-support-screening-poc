"""Conservative local DICOM inspection and single-frame pixel decoding.

The module keeps pydicom behind a small adapter boundary.  Only allowlisted
technical facts leave that boundary; the source dataset, UIDs, and all
patient/person/institution fields remain local implementation details.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from .contracts import IntegrityStatus, SourceDimensions, SourceMetadata, sha256_bytes
from ..contracts._schema import Contract


PART10_PREFIX_LENGTH = 132
PART10_MAGIC = b"DICM"
MEDIA_TYPE = "application/dicom"

# Ophthalmic Photography Image Storage SOP classes.
OPHTHALMIC_PHOTOGRAPHY_8BIT_UID = "1.2.840.10008.5.1.4.1.1.77.1.4.1"
OPHTHALMIC_PHOTOGRAPHY_16BIT_UID = "1.2.840.10008.5.1.4.1.1.77.1.4.2"

SOP_CLASS_CATEGORIES = {
    OPHTHALMIC_PHOTOGRAPHY_8BIT_UID: "OPHTHALMIC_PHOTOGRAPHY_8BIT",
    OPHTHALMIC_PHOTOGRAPHY_16BIT_UID: "OPHTHALMIC_PHOTOGRAPHY_16BIT",
}

TRANSFER_SYNTAX_CATEGORIES = {
    "1.2.840.10008.1.2": "UNCOMPRESSED_IMPLICIT_VR_LITTLE_ENDIAN",
    "1.2.840.10008.1.2.1": "UNCOMPRESSED_EXPLICIT_VR_LITTLE_ENDIAN",
    "1.2.840.10008.1.2.2": "UNCOMPRESSED_EXPLICIT_VR_BIG_ENDIAN",
    "1.2.840.10008.1.2.4.50": "JPEG_BASELINE",
    "1.2.840.10008.1.2.4.51": "JPEG_EXTENDED",
    "1.2.840.10008.1.2.4.57": "JPEG_LOSSLESS",
    "1.2.840.10008.1.2.4.70": "JPEG_LOSSLESS",
    "1.2.840.10008.1.2.4.80": "JPEG_LS_LOSSLESS",
    "1.2.840.10008.1.2.4.81": "JPEG_LS_NEAR_LOSSLESS",
    "1.2.840.10008.1.2.4.90": "JPEG_2000_LOSSLESS",
    "1.2.840.10008.1.2.4.91": "JPEG_2000_LOSSY",
}

UNCOMPRESSED_CATEGORIES = frozenset({
    "UNCOMPRESSED_IMPLICIT_VR_LITTLE_ENDIAN",
    "UNCOMPRESSED_EXPLICIT_VR_LITTLE_ENDIAN",
    "UNCOMPRESSED_EXPLICIT_VR_BIG_ENDIAN",
})
TESTED_TRANSFER_SYNTAX_CATEGORIES = frozenset({
    "UNCOMPRESSED_IMPLICIT_VR_LITTLE_ENDIAN",
    "UNCOMPRESSED_EXPLICIT_VR_LITTLE_ENDIAN",
    "JPEG_BASELINE",
    "JPEG_2000_LOSSLESS",
    "JPEG_2000_LOSSY",
})
LOSSY_TRANSFER_SYNTAX_CATEGORIES = frozenset({
    "JPEG_BASELINE",
    "JPEG_EXTENDED",
    "JPEG_LS_NEAR_LOSSLESS",
    "JPEG_2000_LOSSY",
})
LOSSLESS_TRANSFER_SYNTAX_CATEGORIES = frozenset({
    "JPEG_LOSSLESS",
    "JPEG_LS_LOSSLESS",
    "JPEG_2000_LOSSLESS",
})
SAFE_PHOTOMETRIC_VALUES = frozenset({
    "MONOCHROME1",
    "MONOCHROME2",
    "PALETTE COLOR",
    "RGB",
    "YBR_FULL",
    "YBR_FULL_422",
    "YBR_PARTIAL_422",
    "YBR_ICT",
    "YBR_RCT",
})
SAFE_LOSSY_METHODS = frozenset({
    "ISO_10918_1",
    "ISO_14495_1",
    "ISO_15444_1",
    "ISO_10918_1|ISO_14495_1",
    "ISO_10918_1|ISO_15444_1",
})


class DicomIngestStatus(StrEnum):
    """Explicit outcome of local DICOM recognition and decoding."""

    SUPPORTED = "SUPPORTED"
    CODEC_REQUIRED = "CODEC_REQUIRED"
    MULTIFRAME_UNSUPPORTED = "MULTIFRAME_UNSUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    DECODE_FAILED = "DECODE_FAILED"


class DicomAdapterError(ValueError):
    """Safe, non-dataset error at the DICOM adapter boundary."""

    status = IntegrityStatus.DECODE_FAILED
    ingest_status = DicomIngestStatus.DECODE_FAILED


class DicomDependencyRequiredError(DicomAdapterError):
    """Raised when the optional pydicom dependency group is not installed."""

    status = IntegrityStatus.DICOM_CODEC_REQUIRED
    ingest_status = DicomIngestStatus.CODEC_REQUIRED


class DicomRecognitionError(DicomAdapterError):
    """Raised when bytes are not a standards-conformant Part 10 object."""

    status = IntegrityStatus.UNSUPPORTED_FORMAT
    ingest_status = DicomIngestStatus.UNSUPPORTED


class DicomCodecRequiredError(DicomAdapterError):
    """Raised when the transfer syntax needs a decoder unavailable at runtime."""

    status = IntegrityStatus.DICOM_CODEC_REQUIRED
    ingest_status = DicomIngestStatus.CODEC_REQUIRED


class DicomMultiframeError(DicomAdapterError):
    """Raised by strict callers that request a single frame from multi-frame data."""

    status = IntegrityStatus.DICOM_MULTIFRAME_UNSUPPORTED
    ingest_status = DicomIngestStatus.MULTIFRAME_UNSUPPORTED


class DicomDecodeError(DicomAdapterError):
    """Raised when a recognized single-frame object cannot be decoded."""

    status = IntegrityStatus.DECODE_FAILED
    ingest_status = DicomIngestStatus.DECODE_FAILED


class DicomUnsupportedError(DicomAdapterError):
    """Raised when a recognized DICOM is outside the supported S5B scope."""

    status = IntegrityStatus.UNSUPPORTED_FORMAT
    ingest_status = DicomIngestStatus.UNSUPPORTED


class CompressionState(StrEnum):
    UNCOMPRESSED = "UNCOMPRESSED"
    LOSSLESS = "LOSSLESS"
    LOSSY = "LOSSY"
    UNKNOWN = "UNKNOWN"


class DicomTechnicalMetadata(Contract):
    """Allowlisted DICOM facts with no patient, person, or raw UID fields."""

    sop_class_category: str = Field(min_length=1, max_length=80)
    transfer_syntax_category: str = Field(min_length=1, max_length=100)
    rows: int = Field(gt=0)
    columns: int = Field(gt=0)
    samples_per_pixel: int = Field(gt=0)
    photometric_interpretation: str = Field(min_length=1, max_length=40)
    bits_allocated: int = Field(gt=0)
    bits_stored: int = Field(gt=0)
    high_bit: int | None = Field(default=None, ge=0)
    pixel_representation: int | None = Field(default=None, ge=0, le=1)
    number_of_frames: int = Field(default=1, gt=0)
    laterality_candidate: str | None = Field(default=None, max_length=12)
    compression_state: CompressionState
    lossy_compression_method: str | None = Field(default=None, max_length=80)
    lossy_compression_ratio: float | None = Field(default=None, gt=0)


@dataclass(frozen=True)
class DicomInspection:
    """Safe metadata inspection paired with the S5F source identity."""

    source: SourceMetadata
    metadata: DicomTechnicalMetadata


@dataclass(frozen=True)
class DicomDecodedPixels:
    """Single-frame decoded pixels and their source facts.

    ``pixel_array`` is the pydicom/numpy result and is intentionally not a
    serialized API contract.  S5C owns browser/model derivative encoding.
    """

    inspection: DicomInspection
    pixel_array: Any


@dataclass(frozen=True)
class DicomIngestResult:
    """Non-throwing result suitable for scan callers and capability reports."""

    source_sha256: str
    status: IntegrityStatus
    inspection: DicomInspection | None = None
    decoded: DicomDecodedPixels | None = None
    message: str = ""

    @property
    def ingest_status(self) -> DicomIngestStatus:
        if self.status is IntegrityStatus.OK:
            return DicomIngestStatus.SUPPORTED
        if self.status is IntegrityStatus.DICOM_CODEC_REQUIRED:
            return DicomIngestStatus.CODEC_REQUIRED
        if self.status is IntegrityStatus.DICOM_MULTIFRAME_UNSUPPORTED:
            return DicomIngestStatus.MULTIFRAME_UNSUPPORTED
        if self.status is IntegrityStatus.UNSUPPORTED_FORMAT:
            return DicomIngestStatus.UNSUPPORTED
        return DicomIngestStatus.DECODE_FAILED

    @property
    def metadata(self) -> DicomTechnicalMetadata | None:
        return self.inspection.metadata if self.inspection else None

    @property
    def source(self) -> SourceMetadata | None:
        return self.inspection.source if self.inspection else None

    @property
    def pixel_array(self) -> Any:
        return self.decoded.pixel_array if self.decoded else None


def is_part10_dicom(data: bytes) -> bool:
    """Recognize only the DICOM Part 10 preamble and magic marker."""

    return (
        isinstance(data, bytes)
        and len(data) >= PART10_PREFIX_LENGTH
        and data[128:132] == PART10_MAGIC
    )


def _pydicom_modules() -> tuple[Any, Any]:
    try:
        import pydicom
        from pydicom.errors import InvalidDicomError
    except ImportError as exc:
        raise DicomDependencyRequiredError(
            "Optional DICOM support is not installed"
        ) from exc
    return pydicom, InvalidDicomError


def _read_dataset(data: bytes, *, stop_before_pixels: bool) -> Any:
    if not isinstance(data, bytes) or not data:
        raise DicomRecognitionError("DICOM source bytes are empty or invalid")
    if not is_part10_dicom(data):
        raise DicomRecognitionError("DICOM source is not a Part 10 file")

    pydicom, invalid_dicom_error = _pydicom_modules()
    try:
        return pydicom.dcmread(
            io.BytesIO(data),
            force=False,
            stop_before_pixels=stop_before_pixels,
        )
    except invalid_dicom_error as exc:
        raise DicomRecognitionError("DICOM source could not be parsed") from exc
    except (OSError, ValueError, TypeError) as exc:
        raise DicomDecodeError("DICOM source could not be parsed") from exc
    except Exception as exc:
        raise DicomDecodeError("DICOM source could not be parsed") from exc


def _string_value(dataset: Any, keyword: str) -> str | None:
    value = getattr(dataset, keyword, None)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _positive_int(dataset: Any, keyword: str, *, default: int | None = None) -> int:
    value = getattr(dataset, keyword, default)
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise DicomDecodeError("DICOM technical metadata is invalid") from exc
    if number <= 0:
        raise DicomDecodeError("DICOM technical metadata is invalid")
    return number


def _optional_int(dataset: Any, keyword: str) -> int | None:
    value = getattr(dataset, keyword, None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DicomDecodeError("DICOM technical metadata is invalid") from exc


def _laterality_candidate(dataset: Any) -> str | None:
    value = _string_value(dataset, "ImageLaterality") or _string_value(dataset, "Laterality")
    return {
        "L": "LEFT",
        "LEFT": "LEFT",
        "R": "RIGHT",
        "RIGHT": "RIGHT",
        "B": "BILATERAL",
        "BOTH": "BILATERAL",
    }.get((value or "").upper())


def _safe_photometric(dataset: Any) -> str:
    value = (_string_value(dataset, "PhotometricInterpretation") or "").upper()
    return value if value in SAFE_PHOTOMETRIC_VALUES else "UNKNOWN"


def _safe_lossy_method(dataset: Any) -> str | None:
    value = _string_value(dataset, "LossyImageCompressionMethod")
    if value is None:
        return None
    tokens = [token.strip().upper() for token in value.replace("\\", "|").split("|")]
    normalized = "|".join(token for token in tokens if token)
    return normalized if normalized in SAFE_LOSSY_METHODS else None


def _lossy_ratio(dataset: Any) -> float | None:
    value = _string_value(dataset, "LossyImageCompressionRatio")
    if value is None:
        return None
    try:
        ratio = float(value)
    except ValueError:
        return None
    return ratio if ratio > 0 else None


def _compression_state(
    transfer_syntax_category: str,
    dataset: Any,
) -> CompressionState:
    lossy_tag = (_string_value(dataset, "LossyImageCompression") or "").upper()
    if lossy_tag == "01" or transfer_syntax_category in LOSSY_TRANSFER_SYNTAX_CATEGORIES:
        return CompressionState.LOSSY
    if transfer_syntax_category in UNCOMPRESSED_CATEGORIES:
        return CompressionState.UNCOMPRESSED
    if transfer_syntax_category in LOSSLESS_TRANSFER_SYNTAX_CATEGORIES:
        return CompressionState.LOSSLESS
    return CompressionState.UNKNOWN


def _technical_metadata(dataset: Any) -> DicomTechnicalMetadata:
    file_meta = getattr(dataset, "file_meta", None)
    transfer_syntax_uid = str(getattr(file_meta, "TransferSyntaxUID", ""))
    transfer_syntax_category = TRANSFER_SYNTAX_CATEGORIES.get(
        transfer_syntax_uid,
        "COMPRESSED_UNKNOWN" if transfer_syntax_uid else "UNKNOWN",
    )
    sop_class_uid = _string_value(dataset, "SOPClassUID") or ""
    sop_class_category = SOP_CLASS_CATEGORIES.get(sop_class_uid, "OTHER")
    rows = _positive_int(dataset, "Rows")
    columns = _positive_int(dataset, "Columns")
    samples_per_pixel = _positive_int(dataset, "SamplesPerPixel")
    bits_allocated = _positive_int(dataset, "BitsAllocated")
    bits_stored = _positive_int(dataset, "BitsStored")
    if bits_stored > bits_allocated:
        raise DicomDecodeError("DICOM bit-depth metadata is invalid")
    high_bit = _optional_int(dataset, "HighBit")
    if high_bit is not None and high_bit >= bits_allocated:
        raise DicomDecodeError("DICOM bit-depth metadata is invalid")
    number_of_frames = _positive_int(dataset, "NumberOfFrames", default=1)

    return DicomTechnicalMetadata(
        sop_class_category=sop_class_category,
        transfer_syntax_category=transfer_syntax_category,
        rows=rows,
        columns=columns,
        samples_per_pixel=samples_per_pixel,
        photometric_interpretation=_safe_photometric(dataset),
        bits_allocated=bits_allocated,
        bits_stored=bits_stored,
        high_bit=high_bit,
        pixel_representation=_optional_int(dataset, "PixelRepresentation"),
        number_of_frames=number_of_frames,
        laterality_candidate=_laterality_candidate(dataset),
        compression_state=_compression_state(transfer_syntax_category, dataset),
        lossy_compression_method=_safe_lossy_method(dataset),
        lossy_compression_ratio=_lossy_ratio(dataset),
    )


def _inspection(data: bytes) -> DicomInspection:
    dataset = _read_dataset(data, stop_before_pixels=True)
    try:
        metadata = _technical_metadata(dataset)
    except DicomAdapterError:
        raise
    except Exception as exc:
        raise DicomDecodeError("DICOM technical metadata is invalid") from exc
    source = SourceMetadata(
        source_sha256=sha256_bytes(data),
        source_format="DICOM",
        source_media_type=MEDIA_TYPE,
        dimensions=SourceDimensions(
            width=metadata.columns,
            height=metadata.rows,
            bit_depth=metadata.bits_stored,
            channels=metadata.samples_per_pixel,
        ),
        integrity_status=IntegrityStatus.OK,
    )
    return DicomInspection(source=source, metadata=metadata)


def _decoder_available(dataset: Any, transfer_syntax_category: str) -> bool:
    if transfer_syntax_category in UNCOMPRESSED_CATEGORIES:
        return True
    transfer_syntax_uid = str(getattr(getattr(dataset, "file_meta", None), "TransferSyntaxUID", ""))
    try:
        from pydicom.pixels import get_decoder

        return bool(get_decoder(transfer_syntax_uid).is_available)
    except (AttributeError, ImportError, KeyError, NotImplementedError):
        try:
            import pydicom.pixel_data_handlers as handlers

            return any(
                handler.supports_transfer_syntax(transfer_syntax_uid)
                and handler.is_available()
                for handler in handlers.pixel_data_handlers
            )
        except Exception:
            return False
    except Exception:
        return False


def _safe_decode_array(dataset: Any, inspection: DicomInspection) -> Any:
    metadata = inspection.metadata
    if metadata.number_of_frames != 1:
        raise DicomMultiframeError(
            "DICOM multi-frame objects require explicit frame selection"
        )
    if metadata.sop_class_category not in {
        "OPHTHALMIC_PHOTOGRAPHY_8BIT",
        "OPHTHALMIC_PHOTOGRAPHY_16BIT",
    }:
        raise DicomUnsupportedError("DICOM SOP class is not supported for ophthalmic ingestion")
    if metadata.transfer_syntax_category not in TESTED_TRANSFER_SYNTAX_CATEGORIES:
        raise DicomUnsupportedError(
            "DICOM transfer syntax is outside the tested decoder matrix"
        )
    if not _decoder_available(dataset, metadata.transfer_syntax_category):
        raise DicomCodecRequiredError(
            "A decoder for this DICOM transfer syntax is not available"
        )
    try:
        array = dataset.pixel_array
    except Exception as exc:
        # The dataset is never included in the public error or log message.
        raise DicomDecodeError("DICOM pixel data could not be decoded") from exc

    shape = tuple(int(value) for value in getattr(array, "shape", ()))
    expected = (metadata.rows, metadata.columns)
    if metadata.samples_per_pixel > 1:
        expected = expected + (metadata.samples_per_pixel,)
    if shape != expected:
        raise DicomDecodeError("DICOM pixel dimensions do not match technical metadata")
    return array


class DicomImageHandler:
    """S5F-compatible handler for standards-conformant ophthalmic DICOM."""

    name = "dicom"
    formats = frozenset({"DICOM"})
    media_types = frozenset({MEDIA_TYPE})
    extensions = frozenset({".dcm", ".dicom"})

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
        """Inspect safe source identity/dimensions without decoding pixels."""

        return _inspection(data).source

    def inspect_details(self, data: bytes) -> DicomInspection:
        """Return the safe technical allowlist and source identity."""

        return _inspection(data)

    def decode(self, data: bytes) -> DicomIngestResult:
        """Inspect and decode a single frame without throwing readiness errors."""

        source_sha256 = sha256_bytes(data) if isinstance(data, bytes) else ""
        try:
            inspection = _inspection(data)
            dataset = _read_dataset(data, stop_before_pixels=False)
            decoded = _safe_decode_array(dataset, inspection)
        except DicomAdapterError as exc:
            return DicomIngestResult(
                source_sha256=source_sha256,
                status=exc.status,
                inspection=locals().get("inspection"),
                message=str(exc),
            )
        except Exception:
            return DicomIngestResult(
                source_sha256=source_sha256,
                status=IntegrityStatus.DECODE_FAILED,
                message="DICOM source could not be ingested",
            )
        return DicomIngestResult(
            source_sha256=source_sha256,
            status=IntegrityStatus.OK,
            inspection=inspection,
            decoded=DicomDecodedPixels(inspection=inspection, pixel_array=decoded),
            message="DICOM single-frame pixels decoded locally",
        )

    ingest = decode

    def inspect_file(self, path: str | Path) -> DicomInspection:
        """Read a source path without modifying it or exposing its absolute path."""

        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            raise DicomDecodeError("DICOM source could not be read") from exc
        return self.inspect_details(data)

    def decode_file(self, path: str | Path) -> DicomIngestResult:
        try:
            data = Path(path).read_bytes()
        except OSError:
            return DicomIngestResult(
                source_sha256="",
                status=IntegrityStatus.SOURCE_MISSING,
                message="DICOM source could not be read",
            )
        return self.decode(data)


def default_dicom_handler() -> DicomImageHandler:
    """Return a fresh handler for callers that do not need a registry."""

    return DicomImageHandler()


__all__ = [
    "CompressionState",
    "DicomAdapterError",
    "DicomCodecRequiredError",
    "DicomDecodeError",
    "DicomDecodedPixels",
    "DicomDependencyRequiredError",
    "DicomImageHandler",
    "DicomIngestResult",
    "DicomIngestStatus",
    "DicomInspection",
    "DicomMultiframeError",
    "DicomRecognitionError",
    "DicomTechnicalMetadata",
    "DicomUnsupportedError",
    "MEDIA_TYPE",
    "default_dicom_handler",
    "is_part10_dicom",
]
