import hashlib
import io

import pytest
from PIL import Image
from pydantic import ValidationError

from dr_support.images import BridgeImage
from dr_support.imaging import (
    DerivativeLineage,
    DerivativePurpose,
    IntegrityStatus,
    SourceMetadata,
    UnsupportedImageHandlerError,
    default_image_handler_registry,
    lineage_for_bytes,
    validate_derivative_lineage,
)
from dr_support.services.admission import inspect_file


def _raster_bytes(format_name: str = "PNG") -> bytes:
    image = Image.new("RGB", (320, 240), (80, 35, 25))
    stream = io.BytesIO()
    image.save(stream, format=format_name)
    return stream.getvalue()


@pytest.mark.parametrize(
    ("filename", "format_name", "media_type"),
    [
        ("fundus.jpg", "JPEG", "image/jpeg"),
        ("fundus.png", "PNG", "image/png"),
        ("fundus.tiff", "TIFF", "image/tiff"),
    ],
)
def test_raster_handler_preserves_existing_bridge_identity_and_dimensions(
    tmp_path, filename, format_name, media_type
):
    data = _raster_bytes(format_name)
    path = tmp_path / filename
    path.write_bytes(data)

    record, image = inspect_file(path)
    source = default_image_handler_registry().inspect(data, filename=path.name)

    assert isinstance(image, BridgeImage)
    assert image.image_id == hashlib.sha256(data).hexdigest()
    assert image.sha256 == source.source_sha256
    assert record["image_id"] == image.image_id
    assert (record["width"], record["height"]) == (source.dimensions.width, source.dimensions.height)
    assert source.source_format == format_name
    assert source.source_media_type == media_type
    assert source.integrity_status is IntegrityStatus.OK


def test_source_and_derivative_identity_are_separate_and_hash_exact_bytes():
    source_data = _raster_bytes("PNG")
    derivative_data = _raster_bytes("JPEG")
    source = default_image_handler_registry().inspect(source_data, filename="source.png")

    lineage = lineage_for_bytes(
        source_sha256=source.source_sha256,
        data=derivative_data,
        purpose=DerivativePurpose.DISPLAY,
        output_format="JPEG",
        media_type="image/jpeg",
        width=320,
        height=240,
        transform_id="test-jpeg-v1",
        transform_description="Test display representation",
        coordinate_space="source_pixels",
    )

    assert lineage.source_sha256 == source.source_sha256
    assert lineage.derivative_sha256 == hashlib.sha256(derivative_data).hexdigest()
    assert lineage.derivative_sha256 != lineage.source_sha256
    assert lineage.purpose is DerivativePurpose.DISPLAY


def test_derivative_lineage_requires_source_and_matches_concrete_source():
    with pytest.raises(ValidationError):
        DerivativeLineage(
            derivative_sha256="a" * 64,
            purpose="ANALYSIS",
            format="PNG",
            media_type="image/png",
            width=10,
            height=10,
            transform_id="analysis-v1",
            transform_description="Analysis representation",
            coordinate_space="source_pixels",
            created_at="2026-09-21T00:00:00+00:00",
        )

    values = {
        "source_sha256": "b" * 64,
        "derivative_sha256": "a" * 64,
        "purpose": "ANALYSIS",
        "format": "PNG",
        "media_type": "image/png",
        "width": 10,
        "height": 10,
        "transform_id": "analysis-v1",
        "transform_description": "Analysis representation",
        "coordinate_space": "source_pixels",
        "created_at": "2026-09-21T00:00:00+00:00",
    }
    with pytest.raises(ValueError, match="does not match"):
        validate_derivative_lineage(values, source_sha256="c" * 64)


def test_unknown_format_fails_conservatively_without_fallback():
    registry = default_image_handler_registry()

    assert registry.find(media_type="application/dicom") is None
    assert registry.find(media_type="application/dicom", filename="image.jpg") is None
    with pytest.raises(UnsupportedImageHandlerError) as error:
        registry.resolve(media_type="application/dicom")
    assert error.value.status is IntegrityStatus.UNSUPPORTED_FORMAT


def test_public_imaging_contracts_have_no_phi_or_path_fields():
    public_fields = set(SourceMetadata.model_fields) | set(DerivativeLineage.model_fields)
    forbidden_fragments = {
        "patient",
        "name",
        "mrn",
        "dob",
        "accession",
        "institution",
        "person",
        "uid",
        "path",
    }

    assert not any(
        any(fragment in field.lower() for fragment in forbidden_fragments)
        for field in public_fields
    )
