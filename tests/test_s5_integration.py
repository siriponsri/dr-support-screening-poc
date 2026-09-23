import hashlib
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

np = pytest.importorskip("numpy")
pytest.importorskip("pydicom")

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.uid import ExplicitVRLittleEndian, JPEGBaseline8Bit, MRImageStorage, generate_uid

from dr_support.api import create_app
from dr_support.imaging import DicomImageHandler, IntegrityStatus


OPHTHALMIC_PHOTOGRAPHY_8BIT = "1.2.840.10008.5.1.4.1.1.77.1.4.1"


def _file_meta(transfer_syntax, sop_class_uid=OPHTHALMIC_PHOTOGRAPHY_8BIT):
    meta = FileMetaDataset()
    meta.FileMetaInformationVersion = b"\x00\x01"
    meta.MediaStorageSOPClassUID = sop_class_uid
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = transfer_syntax
    meta.ImplementationClassUID = generate_uid()
    return meta


def _dicom_bytes(*, frames=1, transfer_syntax=ExplicitVRLittleEndian, sop_class_uid=OPHTHALMIC_PHOTOGRAPHY_8BIT):
    pixels = np.arange(frames * 12 * 16 * 3, dtype=np.uint8).reshape(frames, 12, 16, 3)
    dataset = FileDataset(
        "synthetic.dcm",
        {},
        file_meta=_file_meta(transfer_syntax, sop_class_uid),
        preamble=b"\x00" * 128,
    )
    dataset.SOPClassUID = sop_class_uid
    dataset.SOPInstanceUID = generate_uid()
    dataset.StudyInstanceUID = generate_uid()
    dataset.SeriesInstanceUID = generate_uid()
    dataset.PatientName = "INTEGRATION^MUST_NOT_LEAK"
    dataset.PatientID = "SYNTHETIC-PHI-MUST-NOT-LEAK"
    dataset.InstitutionName = "Synthetic Hospital"
    dataset.Modality = "OP"
    dataset.Rows = 12
    dataset.Columns = 16
    dataset.SamplesPerPixel = 3
    dataset.PhotometricInterpretation = "RGB"
    dataset.PlanarConfiguration = 0
    dataset.BitsAllocated = 8
    dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    dataset.ImageLaterality = "L"
    if frames > 1:
        dataset.NumberOfFrames = frames
    dataset.PixelData = pixels.tobytes()
    output = io.BytesIO()
    dataset.save_as(output, write_like_original=False)
    return output.getvalue()


def _compressed_dicom_bytes():
    image = Image.new("RGB", (16, 12))
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            pixels[x, y] = ((x * 17) % 256, (y * 23) % 256, ((x + y) * 31) % 256)
    encoded = io.BytesIO()
    image.save(encoded, format="JPEG", quality=80)

    dataset = FileDataset(
        "synthetic-compressed.dcm",
        {},
        file_meta=_file_meta(JPEGBaseline8Bit),
        preamble=b"\x00" * 128,
    )
    dataset.SOPClassUID = OPHTHALMIC_PHOTOGRAPHY_8BIT
    dataset.SOPInstanceUID = generate_uid()
    dataset.Rows = 12
    dataset.Columns = 16
    dataset.SamplesPerPixel = 3
    dataset.PhotometricInterpretation = "YBR_FULL_422"
    dataset.PlanarConfiguration = 0
    dataset.BitsAllocated = 8
    dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    dataset.ImageLaterality = "R"
    dataset.PixelData = encapsulate([encoded.getvalue()])
    dataset["PixelData"].is_undefined_length = True
    output = io.BytesIO()
    dataset.save_as(output, write_like_original=False)
    return output.getvalue()


def _workspace_client(tmp_path):
    app = create_app(tmp_path / "fallback.sqlite", include_samples=False)
    client = TestClient(app)
    input_folder = tmp_path / "input"
    output_folder = tmp_path / "output"
    input_folder.mkdir()
    output_folder.mkdir()
    response = client.post("/v1/workspaces", json={
        "name": "S5 integration fixtures",
        "input_folder": str(input_folder),
        "output_folder": str(output_folder),
        "database_path": str(tmp_path / "reviews.sqlite"),
    })
    assert response.status_code == 200
    return app, client, input_folder


def test_uncompressed_dicom_admission_display_and_privacy(tmp_path):
    data = _dicom_bytes()
    source_sha256 = hashlib.sha256(data).hexdigest()
    app, client, input_folder = _workspace_client(tmp_path)
    source = input_folder / "fundus.dcm"
    source.write_bytes(data)

    scan = client.post("/v1/admissions/scan")
    assert scan.status_code == 200
    record = next(item for item in scan.json()["records"] if item["filename"] == "fundus.dcm")
    assert record["image_id"] == source_sha256
    assert record["source_sha256"] == source_sha256
    assert record["source_format"] == "DICOM"
    assert record["source_media_type"] == "application/dicom"
    assert record["source_dimensions"] == {"width": 16, "height": 12, "bit_depth": 8, "channels": 3}
    assert record["modality_admission"] == "NEEDS_REVIEW"
    assert app.state.images[source_sha256].data == data
    assert app.state.images[source_sha256].size == (16, 12)

    case = client.get(f"/v1/cases/{source_sha256}")
    display = client.get(f"/v1/images/{source_sha256}/display")
    original = client.get(f"/v1/images/{source_sha256}")

    assert case.status_code == 200
    assert case.json()["source_sha256"] == source_sha256
    assert case.json()["image_url"] == f"/v1/images/{source_sha256}/display"
    assert case.json()["source_image_url"] == f"/v1/images/{source_sha256}"
    assert display.status_code == 200
    assert display.headers["content-type"].startswith("image/png")
    assert display.headers["x-source-sha256"] == source_sha256
    assert display.headers["x-derivative-sha256"] == hashlib.sha256(display.content).hexdigest()
    assert display.content != data
    assert original.content == data
    with Image.open(io.BytesIO(display.content)) as decoded:
        assert decoded.format == "PNG"
        assert decoded.size == (16, 12)

    manifest = client.get("/v1/dataset/manifest")
    assert manifest.status_code == 200
    public_json = json.dumps({"case": case.json(), "manifest": manifest.json()})
    for forbidden in (
        "PatientName",
        "PatientID",
        "InstitutionName",
        "INTEGRATION^MUST_NOT_LEAK",
        "SYNTHETIC-PHI-MUST-NOT-LEAK",
    ):
        assert forbidden not in public_json


def test_grouped_export_uses_dicom_display_derivative_without_exporting_source_metadata(tmp_path):
    data = _dicom_bytes()
    source_sha256 = hashlib.sha256(data).hexdigest()
    app, client, input_folder = _workspace_client(tmp_path)
    source = input_folder / "fundus.dcm"
    source.write_bytes(data)
    assert client.post("/v1/admissions/scan").status_code == 200

    case = client.get(f"/v1/cases/{source_sha256}").json()
    accepted = client.post(f"/v1/cases/{source_sha256}/admission", json={
        "revision": case["revision"],
        "reviewer": "Synthetic clinician",
        "action": "ACCEPT_RETINAL",
    })
    assert accepted.status_code == 200
    reviewed = client.post(f"/v1/cases/{source_sha256}/review", json={
        "revision": accepted.json()["revision"],
        "reviewer": "Synthetic clinician",
        "action": "CORRECT_GRADE",
        "grade": 2,
    })
    assert reviewed.status_code == 200

    display = client.get(f"/v1/images/{source_sha256}/display")
    assert display.status_code == 200
    result = client.post("/v1/dataset/export/grouped-by-grade", json={})
    assert result.status_code == 200

    output = tmp_path / "output" / "grouped_by_grade"
    exported = next((output / "dr_grade_2").glob("*.png"))
    with Image.open(exported) as decoded:
        assert decoded.format == "PNG"
        assert decoded.size == (16, 12)
    manifest_path = output / "_manifest" / "grouped_export_manifest.json"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    item = next(row for row in manifest["items"] if row["image_id"] == source_sha256)
    assert item["source_was_dicom"] is True
    assert item["source_sha256"] == source_sha256
    assert item["rendered_derivative_sha256"] == display.headers["x-derivative-sha256"]
    assert item["export_sha256"] == hashlib.sha256(exported.read_bytes()).hexdigest()
    assert "INTEGRATION^MUST_NOT_LEAK" not in manifest_text
    assert "SYNTHETIC-PHI-MUST-NOT-LEAK" not in manifest_text
    assert source.read_bytes() == data
    assert app.state.images[source_sha256].data == data


def test_dicom_display_dispatches_compressed_supported_codec_when_available(tmp_path):
    data = _compressed_dicom_bytes()
    result = DicomImageHandler().decode(data)
    if result.status is IntegrityStatus.DICOM_CODEC_REQUIRED:
        pytest.skip("JPEG Baseline DICOM decoder is not available")
    assert result.status is IntegrityStatus.OK, result.message

    app, client, input_folder = _workspace_client(tmp_path)
    source = input_folder / "compressed.dcm"
    source.write_bytes(data)
    scan = client.post("/v1/admissions/scan")
    image_id = hashlib.sha256(data).hexdigest()

    assert scan.status_code == 200
    assert next(item for item in scan.json()["records"] if item["image_id"] == image_id)["source_format"] == "DICOM"
    display = client.get(f"/v1/images/{image_id}/display")
    assert display.status_code == 200
    assert display.headers["content-type"].startswith("image/png")
    with Image.open(io.BytesIO(display.content)) as decoded:
        assert decoded.size == (16, 12)


def test_multiframe_dicom_is_reviewable_but_not_admitted_for_display(tmp_path):
    data = _dicom_bytes(frames=2)
    app, client, input_folder = _workspace_client(tmp_path)
    source = input_folder / "series.dcm"
    source.write_bytes(data)
    image_id = hashlib.sha256(data).hexdigest()

    scan = client.post("/v1/admissions/scan")
    record = next(item for item in scan.json()["records"] if item["image_id"] == image_id)

    assert record["modality_admission"] == "NEEDS_REVIEW"
    assert record["integrity_status"] == "DICOM_MULTIFRAME_UNSUPPORTED"
    assert record["source_sha256"] == image_id
    assert image_id not in app.state.images
    display = client.get(f"/v1/images/{image_id}/display")
    assert display.status_code == 409
    assert "frame selection" in display.json()["detail"].lower()


def test_non_ophthalmic_dicom_reports_unsupported_modality(tmp_path):
    data = _dicom_bytes(sop_class_uid=str(MRImageStorage))
    app, client, input_folder = _workspace_client(tmp_path)
    source = input_folder / "brain-mri.dcm"
    source.write_bytes(data)
    image_id = hashlib.sha256(data).hexdigest()

    scan = client.post("/v1/admissions/scan")
    record = next(item for item in scan.json()["records"] if item["image_id"] == image_id)

    assert record["modality_admission"] == "REJECTED_INVALID"
    assert record["integrity_status"] == "UNSUPPORTED_FORMAT"
    assert record["admission_reason_code"] == "DICOM_UNSUPPORTED_MODALITY"
    assert image_id not in app.state.images

    case = client.get(f"/v1/cases/{image_id}")
    assert case.status_code == 200
    assert case.json()["admission_ui"] == {
        "label": "Unsupported modality",
        "note": "This DICOM has an unsupported modality; it is not an ophthalmic retinal image for DR analysis.",
        "tone": "danger",
        "action_required": False,
    }
    display = client.get(f"/v1/images/{image_id}/display")
    assert display.status_code == 409
    assert "unsupported" in display.json()["detail"].lower()
    assert "ophthalmic retinal image" in display.json()["detail"].lower()

    grouped = client.post("/v1/dataset/export/grouped-by-grade", json={})
    assert grouped.status_code == 200
    grouped_manifest = json.loads(
        (tmp_path / "output" / "grouped_by_grade" / "_manifest" / "grouped_export_manifest.json")
        .read_text(encoding="utf-8")
    )
    rejected = next(row for row in grouped_manifest["items"] if row["image_id"] == image_id)
    assert rejected["source_was_dicom"] is True
    assert rejected["status"] == "SKIPPED_NOT_FUNDUS_ACCEPTED"
    assert rejected["output_path"] is None


def test_corrupt_dicom_is_safe_invalid_admission_and_display_failure(tmp_path):
    data = b"not a dicom"
    app, client, input_folder = _workspace_client(tmp_path)
    source = input_folder / "corrupt.dcm"
    source.write_bytes(data)
    image_id = hashlib.sha256(data).hexdigest()

    scan = client.post("/v1/admissions/scan")
    record = next(item for item in scan.json()["records"] if item["image_id"] == image_id)

    assert record["modality_admission"] == "REJECTED_INVALID"
    assert record["integrity_status"] == "UNSUPPORTED_FORMAT"
    assert record["source_sha256"] == image_id
    assert image_id not in app.state.images
    display = client.get(f"/v1/images/{image_id}/display")
    assert display.status_code == 409
    assert "dicom" in display.json()["detail"].lower()
    assert "DICM" not in display.text


@pytest.mark.parametrize("format_name, suffix, media_type", [
    ("JPEG", ".jpg", "image/jpeg"),
    ("PNG", ".png", "image/png"),
    ("TIFF", ".tiff", "image/png"),
])
def test_raster_display_dispatch_regression(tmp_path, format_name, suffix, media_type):
    image = Image.new("RGB", (16, 12), (80, 35, 25))
    encoded = io.BytesIO()
    image.save(encoded, format=format_name)
    data = encoded.getvalue()
    app = create_app(tmp_path / "state.sqlite", include_samples=False)
    from dr_support.images import BridgeImage
    from dr_support.services.admission import legacy_admission

    image_id = hashlib.sha256(data).hexdigest()
    app.state.images[image_id] = BridgeImage(
        image_id,
        data,
        "PUBLIC",
        "WORKSPACE_INPUT",
        filename=f"fundus{suffix}",
        media_type="image/tiff" if format_name == "TIFF" else media_type,
    )
    app.state.admissions[image_id] = legacy_admission(app.state.images[image_id])
    response = TestClient(app).get(f"/v1/images/{image_id}/display")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(media_type)
