"""Shared, PHI-free contracts for source images and derived representations.

This module deliberately describes identity and provenance only.  It does not
decode DICOM, persist image bytes, or change the existing ``image_id``
contract used by the review workflow.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import Field

from ..contracts._schema import Contract


SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class DerivativePurpose(StrEnum):
    """The role of a representation derived from an immutable source."""

    DISPLAY = "DISPLAY"
    ANALYSIS = "ANALYSIS"
    MASTER = "MASTER"


class IntegrityStatus(StrEnum):
    """Technical states shared by future ingestion and integrity lanes."""

    OK = "OK"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    SOURCE_MISSING = "SOURCE_MISSING"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    DICOM_CODEC_REQUIRED = "DICOM_CODEC_REQUIRED"
    DICOM_MULTIFRAME_UNSUPPORTED = "DICOM_MULTIFRAME_UNSUPPORTED"
    DECODE_FAILED = "DECODE_FAILED"
    DERIVATIVE_FAILED = "DERIVATIVE_FAILED"


class SourceDimensions(Contract):
    """Pixel dimensions and optional technical depth facts for a source."""

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    bit_depth: int | None = Field(default=None, gt=0)
    channels: int | None = Field(default=None, gt=0)


class SourceMetadata(Contract):
    """Safe technical identity for immutable source bytes.

    ``source_sha256`` is the hash of the exact source-file bytes.  This
    contract intentionally contains no patient, person, institution, UID, or
    local-path fields.
    """

    source_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    source_format: str = Field(min_length=1, max_length=40)
    source_media_type: str = Field(min_length=1, max_length=120)
    dimensions: SourceDimensions
    integrity_status: IntegrityStatus = IntegrityStatus.OK

    @property
    def source_dimensions(self) -> SourceDimensions:
        """Compatibility spelling for callers that use the explicit name."""

        return self.dimensions


class SourceAlias(Contract):
    """A safe, workspace-relative reference to the same source bytes."""

    filename: str = Field(min_length=1, max_length=260)
    source_reference: str = Field(min_length=1, max_length=1000)


class SourceChange(Contract):
    """Evidence that one logical source reference now has different bytes."""

    filename: str = Field(min_length=1, max_length=260)
    source_reference: str = Field(min_length=1, max_length=1000)
    previous_source_sha256: str = Field(pattern=SHA256_PATTERN.pattern)


class SourceIntegrity(Contract):
    """Non-destructive integrity facts attached to an admission record."""

    status: IntegrityStatus = IntegrityStatus.OK
    aliases: list[SourceAlias] = Field(default_factory=list, max_length=500)
    duplicate_content: bool = False
    previous_source_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN.pattern)
    changed_sources: list[SourceChange] = Field(default_factory=list, max_length=500)


class DerivativeLineage(Contract):
    """Auditable identity and transform facts for one derivative."""

    source_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    derivative_sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    purpose: DerivativePurpose
    format: str = Field(min_length=1, max_length=40)
    media_type: str = Field(min_length=1, max_length=120)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    bit_depth: int | None = Field(default=None, gt=0)
    transform_id: str = Field(min_length=1, max_length=120)
    transform_description: str = Field(min_length=1, max_length=1000)
    coordinate_space: str = Field(min_length=1, max_length=120)
    created_at: str = Field(min_length=1, max_length=80)

    @property
    def derivative_dimensions(self) -> SourceDimensions:
        """Expose derivative dimensions in the same shape as source facts."""

        return SourceDimensions(width=self.width, height=self.height, bit_depth=self.bit_depth)


class DerivativeArtifact(Contract):
    """Metadata envelope returned by a later derivative builder.

    The bytes remain an implementation concern of the delivery lane and are
    therefore not part of this public JSON-safe contract.
    """

    lineage: DerivativeLineage


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 of exact bytes."""

    if not isinstance(data, bytes):
        raise TypeError("Image bytes must be bytes")
    return hashlib.sha256(data).hexdigest()


def validate_derivative_lineage(
    lineage: DerivativeLineage | dict[str, Any],
    *,
    source_sha256: str | None = None,
) -> DerivativeLineage:
    """Validate a derivative lineage record and, when supplied, its source.

    The source hash is mandatory in the contract.  The optional comparison is
    useful at adapter boundaries where a builder is given a concrete source
    record and must not accidentally attach its output to another source.
    """

    validated = DerivativeLineage.model_validate(lineage)
    if source_sha256 is not None:
        if not SHA256_PATTERN.fullmatch(source_sha256):
            raise ValueError("Source SHA-256 must be 64 lowercase hexadecimal characters")
        if validated.source_sha256 != source_sha256:
            raise ValueError("Derivative lineage source SHA-256 does not match the source")
    return validated


def lineage_for_bytes(
    *,
    source_sha256: str,
    data: bytes,
    purpose: DerivativePurpose,
    output_format: str,
    media_type: str,
    width: int,
    height: int,
    transform_id: str,
    transform_description: str,
    coordinate_space: str,
    bit_depth: int | None = None,
    created_at: str | None = None,
) -> DerivativeLineage:
    """Build lineage using the exact bytes produced by a derivative builder."""

    return validate_derivative_lineage({
        "source_sha256": source_sha256,
        "derivative_sha256": sha256_bytes(data),
        "purpose": purpose,
        "format": output_format,
        "media_type": media_type,
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "transform_id": transform_id,
        "transform_description": transform_description,
        "coordinate_space": coordinate_space,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }, source_sha256=source_sha256)


# Explicit aliases make the contract useful to callers that use the terms from
# the S5 specification without creating separate, potentially divergent types.
ImageDimensions = SourceDimensions
SourceIdentity = SourceMetadata
