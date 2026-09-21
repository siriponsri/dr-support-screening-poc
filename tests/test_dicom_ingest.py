import hashlib
import io

import pytest
from PIL import Image

np = pytest.importorskip("numpy")
pytest.importorskip("pydicom")

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.uid import (
    ExplicitVRLittleEndian,
    ImplicitVRLittleEndian,
    JPEG2000,
    JPEG2000Lossless,
    JPEGBaseline8Bit,
    SecondaryCaptureImageStorage,
    generate_uid,
)

from dr_support.imaging import (
    DicomImageHandler,
    DicomIngestStatus,
    IntegrityStatus,
    default_dicom_image_handler_registry,
    is_part10_dicom,
)


def _file_meta(transfer_syntax, *, sop_class_uid):
    meta = FileMetaDataset()
    meta.FileMetaInformationVersion = b"\x00\x01"
    meta.MediaStorageSOPClassUID = sop_class_uid
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = transfer_syntax
    meta.ImplementationClassUID = generate_uid()
    return meta


def _dicom_bytes(
    *,
    pixels,
    transfer_syntax=ExplicitVRLittleEndian,
    sop_class_uid="1.2.840.10008.5.1.4.1.1.77.1.4.1",
    photometric="RGB",
    samples_per_pixel=3,
    bits_allocated=8,
    bits_stored=None,
    number_of_frames=None,
    laterality="L",
    patient_name="SYNTHETIC^NEVER_EXPORT",
):
    bits_stored = bits_stored or bits_allocated
    array = np.asarray(pixels)
    buffer = io.BytesIO()
    dataset = FileDataset(
        "synthetic.dcm",
        {},
        file_meta=_file_meta(transfer_syntax, sop_class_uid=sop_class_uid),
        preamble=b"\x00" * 128,
    )
    dataset.is_little_endian = transfer_syntax != "1.2.840.10008.1.2.2"
    dataset.is_implicit_VR = transfer_syntax == "1.2.840.10008.1.2"
    dataset.PatientName = patient_name
    dataset.PatientID = "SYNTHETIC-ID-MUST-NOT-LEAK"
    dataset.InstitutionName = "Synthetic Hospital"
    dataset.SOPClassUID = sop_class_uid
    dataset.SOPInstanceUID = generate_uid()
    dataset.StudyInstanceUID = generate_uid()
    dataset.SeriesInstanceUID = generate_uid()
    dataset.Modality = "OP"
    dataset.Rows = array.shape[-3] if samples_per_pixel > 1 else array.shape[-2]
    dataset.Columns = array.shape[-2] if samples_per_pixel > 1 else array.shape[-1]
    dataset.SamplesPerPixel = samples_per_pixel
    dataset.PhotometricInterpretation = photometric
    if samples_per_pixel > 1:
        dataset.PlanarConfiguration = 0
    dataset.BitsAllocated = bits_allocated
    dataset.BitsStored = bits_stored
    dataset.HighBit = bits_stored - 1
    dataset.PixelRepresentation = 0
    dataset.ImageLaterality = laterality
    if number_of_frames is not None:
        dataset.NumberOfFrames = number_of_frames
    dataset.PixelData = array.tobytes()
    dataset.save_as(buffer, write_like_original=False)
    return buffer.getvalue()


def _compressed_dicom_bytes(*, transfer_syntax, image_format, photometric="RGB"):
    image = Image.new("RGB", (8, 6))
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            pixels[x, y] = ((x * 31) % 256, (y * 41) % 256, ((x + y) * 17) % 256)
    encoded = io.BytesIO()
    image.save(encoded, format=image_format, quality=75 if image_format == "JPEG" else None)
    frame = encoded.getvalue()

    dataset = FileDataset(
        "synthetic-compressed.dcm",
        {},
        file_meta=_file_meta(transfer_syntax, sop_class_uid="1.2.840.10008.5.1.4.1.1.77.1.4.1"),
        preamble=b"\x00" * 128,
    )
    dataset.SOPClassUID = "1.2.840.10008.5.1.4.1.1.77.1.4.1"
    dataset.SOPInstanceUID = generate_uid()
    dataset.Rows = 6
    dataset.Columns = 8
    dataset.SamplesPerPixel = 3
    dataset.PhotometricInterpretation = photometric
    dataset.PlanarConfiguration = 0
    dataset.BitsAllocated = 8
    dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    dataset.ImageLaterality = "R"
    dataset.PixelData = encapsulate([frame])
    dataset["PixelData"].is_undefined_length = True
    dataset.save_as(encoded := io.BytesIO(), write_like_original=False)
    return encoded.getvalue()


@pytest.fixture
def handler():
    return DicomImageHandler()


def test_part10_recognition_is_strict_and_registry_is_explicit(handler):
    valid = _dicom_bytes(pixels=np.zeros((4, 5, 3), dtype=np.uint8))

    assert is_part10_dicom(valid)
    assert not is_part10_dicom(b"DICM" + b"\x00" * 200)
    assert default_dicom_image_handler_registry().find(source_format="DICOM") is not None

    result = handler.decode(b"DICM" + b"\x00" * 200)
    assert result.status is IntegrityStatus.UNSUPPORTED_FORMAT
    assert result.ingest_status is DicomIngestStatus.UNSUPPORTED


def test_uncompressed_8bit_decodes_and_exposes_only_safe_metadata(handler):
    data = _dicom_bytes(pixels=np.arange(4 * 5 * 3, dtype=np.uint8).reshape(4, 5, 3))
    inspection = handler.inspect_details(data)
    result = handler.decode(data)

    assert result.status is IntegrityStatus.OK
    assert result.ingest_status is DicomIngestStatus.SUPPORTED
    assert result.source_sha256 == hashlib.sha256(data).hexdigest()
    assert result.pixel_array.shape == (4, 5, 3)
    assert inspection.metadata.sop_class_category == "OPHTHALMIC_PHOTOGRAPHY_8BIT"
    assert inspection.metadata.transfer_syntax_category == "UNCOMPRESSED_EXPLICIT_VR_LITTLE_ENDIAN"
    assert inspection.metadata.photometric_interpretation == "RGB"
    assert inspection.metadata.bits_allocated == 8
    assert inspection.metadata.bits_stored == 8
    assert inspection.metadata.number_of_frames == 1
    assert inspection.metadata.laterality_candidate == "LEFT"
    assert inspection.source.dimensions.width == 5
    assert inspection.source.dimensions.height == 4
    assert set(inspection.metadata.model_dump()) <= {
        "sop_class_category",
        "transfer_syntax_category",
        "rows",
        "columns",
        "samples_per_pixel",
        "photometric_interpretation",
        "bits_allocated",
        "bits_stored",
        "high_bit",
        "pixel_representation",
        "number_of_frames",
        "laterality_candidate",
        "compression_state",
        "lossy_compression_method",
        "lossy_compression_ratio",
    }
    assert "SYNTHETIC-ID-MUST-NOT-LEAK" not in repr(inspection)


def test_uncompressed_16bit_retains_bit_depth(handler):
    data = _dicom_bytes(
        pixels=np.arange(3 * 4, dtype=np.uint16).reshape(3, 4),
        sop_class_uid="1.2.840.10008.5.1.4.1.1.77.1.4.2",
        photometric="MONOCHROME2",
        samples_per_pixel=1,
        bits_allocated=16,
        bits_stored=12,
    )
    result = handler.decode(data)

    assert result.status is IntegrityStatus.OK
    assert result.pixel_array.shape == (3, 4)
    assert result.metadata.sop_class_category == "OPHTHALMIC_PHOTOGRAPHY_16BIT"
    assert result.metadata.bits_allocated == 16
    assert result.metadata.bits_stored == 12
    assert result.source.dimensions.bit_depth == 12


def test_uncompressed_implicit_little_endian_decodes(handler):
    data = _dicom_bytes(
        pixels=np.arange(4 * 5 * 3, dtype=np.uint8).reshape(4, 5, 3),
        transfer_syntax=ImplicitVRLittleEndian,
    )

    result = handler.decode(data)

    assert result.status is IntegrityStatus.OK
    assert result.metadata.transfer_syntax_category == "UNCOMPRESSED_IMPLICIT_VR_LITTLE_ENDIAN"


@pytest.mark.parametrize(
    ("transfer_syntax", "image_format", "expected_category"),
    [
        (JPEGBaseline8Bit, "JPEG", "JPEG_BASELINE"),
        (JPEG2000Lossless, "JPEG2000", "JPEG_2000_LOSSLESS"),
        (JPEG2000, "JPEG2000", "JPEG_2000_LOSSY"),
    ],
)
def test_available_compressed_codecs_are_decoded_and_facts_are_retained(
    handler, transfer_syntax, image_format, expected_category
):
    data = _compressed_dicom_bytes(
        transfer_syntax=transfer_syntax,
        image_format=image_format,
        photometric="RGB",
    )
    result = handler.decode(data)

    assert result.status is IntegrityStatus.OK, result.message
    assert result.pixel_array.shape == (6, 8, 3)
    assert result.metadata.transfer_syntax_category == expected_category
    assert result.metadata.compression_state.value in {"LOSSLESS", "LOSSY"}


def test_multiframe_is_metadata_only_and_never_reduced_to_first_frame(handler):
    frames = np.arange(2 * 4 * 5 * 3, dtype=np.uint8).reshape(2, 4, 5, 3)
    data = _dicom_bytes(pixels=frames, number_of_frames=2)
    result = handler.decode(data)

    assert result.status is IntegrityStatus.DICOM_MULTIFRAME_UNSUPPORTED
    assert result.ingest_status is DicomIngestStatus.MULTIFRAME_UNSUPPORTED
    assert result.metadata.number_of_frames == 2
    assert result.pixel_array is None


def test_missing_compressed_decoder_is_explicit(monkeypatch, handler):
    data = _compressed_dicom_bytes(
        transfer_syntax=JPEGBaseline8Bit,
        image_format="JPEG",
    )
    monkeypatch.setattr("dr_support.imaging.dicom._decoder_available", lambda *_: False)

    result = handler.decode(data)

    assert result.status is IntegrityStatus.DICOM_CODEC_REQUIRED
    assert result.ingest_status is DicomIngestStatus.CODEC_REQUIRED
    assert result.pixel_array is None


def test_corrupt_dicom_is_safe_decode_failure_without_header_dump(handler):
    result = handler.decode(b"\x00" * 512)

    assert result.status is IntegrityStatus.UNSUPPORTED_FORMAT
    assert result.ingest_status is DicomIngestStatus.UNSUPPORTED
    assert "Patient" not in result.message
    assert "DICM" not in result.message


def test_unsupported_sop_is_not_presented_as_ophthalmic_support(handler):
    data = _dicom_bytes(
        pixels=np.zeros((4, 5), dtype=np.uint8),
        sop_class_uid=str(SecondaryCaptureImageStorage),
        photometric="MONOCHROME2",
        samples_per_pixel=1,
    )
    result = handler.decode(data)

    assert result.status is IntegrityStatus.UNSUPPORTED_FORMAT
    assert result.pixel_array is None
