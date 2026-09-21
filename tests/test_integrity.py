import hashlib
import io

from fastapi.testclient import TestClient
from PIL import Image

from dr_support.api import create_app
from dr_support.services.admission import scan_input_folder


def _image_bytes(format_name="PNG", *, color=(120, 45, 30), size=(320, 240)):
    image = Image.new("RGB", size, color)
    stream = io.BytesIO()
    image.save(stream, format=format_name)
    return stream.getvalue()


def _workspace_client(tmp_path):
    app = create_app(tmp_path / "fallback.sqlite", include_samples=False)
    client = TestClient(app)
    input_folder = tmp_path / "input"
    output_folder = tmp_path / "output"
    input_folder.mkdir()
    output_folder.mkdir()
    response = client.post("/v1/workspaces", json={
        "name": "Integrity fixtures",
        "input_folder": str(input_folder),
        "output_folder": str(output_folder),
        "database_path": str(tmp_path / "workspace.sqlite"),
    })
    assert response.status_code == 200
    return app, client, input_folder


def test_raster_source_integrity_preserves_jpeg_png_and_tiff(tmp_path):
    expected = {
        "source.jpg": ("JPEG", "image/jpeg"),
        "source.png": ("PNG", "image/png"),
        "source.tiff": ("TIFF", "image/tiff"),
    }
    for filename, (source_format, media_type) in expected.items():
        path = tmp_path / filename
        path.write_bytes(_image_bytes(source_format))
        scan = scan_input_folder(tmp_path)
        record = next(item for item in scan.records.values() if item["filename"] == filename)
        source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

        assert record["source_sha256"] == source_sha256
        assert record["source_format"] == source_format
        assert record["source_media_type"] == media_type
        assert record["source_dimensions"] == {
            "width": 320, "height": 240, "bit_depth": 8, "channels": 3,
        }
        assert record["integrity_status"] == "OK"


def test_byte_identical_aliases_are_reported_without_merging_source_references(tmp_path):
    data = _image_bytes("PNG")
    (tmp_path / "first.png").write_bytes(data)
    (tmp_path / "second.png").write_bytes(data)

    scan = scan_input_folder(tmp_path)

    assert len(scan.records) == 1
    record = next(iter(scan.records.values()))
    assert record["image_id"] == hashlib.sha256(data).hexdigest()
    assert record["integrity_status"] == "DUPLICATE_CONTENT"
    assert record["integrity"]["duplicate_content"] is True
    assert [alias["filename"] for alias in record["integrity"]["aliases"]] == [
        "first.png", "second.png",
    ]
    assert not scan.warnings


def test_same_source_reference_changed_bytes_gets_new_case_without_review_transfer(tmp_path):
    app, client, input_folder = _workspace_client(tmp_path)
    source = input_folder / "reviewed.png"
    source.write_bytes(_image_bytes("PNG", color=(130, 35, 25)))
    client.post("/v1/admissions/scan")
    first = next(item for item in client.get("/v1/cases").json() if item["filename"] == "reviewed.png")
    reviewed = client.post(f"/v1/cases/{first['image_id']}/admission", json={
        "revision": first["revision"],
        "reviewer": "Integrity clinician",
        "action": "ACCEPT_RETINAL",
    })
    assert reviewed.status_code == 200
    old_case = reviewed.json()

    source.write_bytes(_image_bytes("PNG", color=(20, 70, 150)))
    rescanned = client.post("/v1/admissions/scan")
    assert rescanned.status_code == 200
    current = next(item for item in rescanned.json()["records"] if item["filename"] == "reviewed.png")

    assert current["image_id"] != first["image_id"]
    assert current["integrity_status"] == "SOURCE_CHANGED"
    assert current["integrity"]["previous_source_sha256"] == first["image_id"]
    assert current["integrity"]["changed_sources"][0]["source_reference"] == \
        "WORKSPACE_INPUT/reviewed.png"
    assert current["admission_method"] == "AUTOMATIC"
    current_case = client.get(f"/v1/cases/{current['image_id']}").json()
    assert current_case["revision"] == 0
    assert current_case["clinician_review"] is None
    assert current_case["human_annotations"] == []
    assert old_case["admission"]["admission_method"] == "MANUAL"
    assert app.state.store.get(first["image_id"])["admission"]["admission_method"] == "MANUAL"


def test_corrupt_and_unsupported_sources_are_safe_and_keep_byte_hashes(tmp_path):
    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"not a jpeg")
    unsupported = tmp_path / "notes.txt"
    unsupported.write_bytes(b"not an image")
    mismatched = tmp_path / "png-named-as-jpeg.jpg"
    mismatched.write_bytes(_image_bytes("PNG"))

    scan = scan_input_folder(tmp_path)
    records = {record["filename"]: record for record in scan.records.values()}

    assert records["corrupt.jpg"]["integrity_status"] == "DECODE_FAILED"
    assert records["corrupt.jpg"]["source_sha256"] == hashlib.sha256(corrupt.read_bytes()).hexdigest()
    assert records["notes.txt"]["integrity_status"] == "UNSUPPORTED_FORMAT"
    assert records["notes.txt"]["source_sha256"] == hashlib.sha256(unsupported.read_bytes()).hexdigest()
    assert records["png-named-as-jpeg.jpg"]["integrity_status"] == "UNSUPPORTED_FORMAT"
    assert records["png-named-as-jpeg.jpg"]["admission_reason_code"] == "FORMAT_EXTENSION_MISMATCH"
    assert records["png-named-as-jpeg.jpg"]["source_metadata"]["integrity_status"] == "UNSUPPORTED_FORMAT"
    assert records["corrupt.jpg"]["modality_admission"] == "REJECTED_INVALID"
    assert records["notes.txt"]["modality_admission"] == "REJECTED_INVALID"


def test_missing_source_is_recorded_without_returning_a_deleted_case(tmp_path):
    app, client, input_folder = _workspace_client(tmp_path)
    source = input_folder / "vanished.png"
    source.write_bytes(_image_bytes("PNG"))
    client.post("/v1/admissions/scan")
    first = next(item for item in client.get("/v1/cases").json() if item["filename"] == "vanished.png")

    source.unlink()
    rescanned = client.post("/v1/admissions/scan")

    assert rescanned.status_code == 200
    assert rescanned.json()["records"] == []
    assert any("vanished.png" in warning and "missing" in warning for warning in rescanned.json()["warnings"])
    assert all(item["filename"] != "vanished.png" for item in client.get("/v1/cases").json())
    assert app.state.store.get(first["image_id"])["admission"]["integrity_status"] == "SOURCE_MISSING"


def test_scan_order_and_source_bytes_are_deterministic_and_read_only(tmp_path):
    paths = {
        "zeta.png": _image_bytes("PNG", color=(10, 50, 90)),
        "Alpha.JPG": _image_bytes("JPEG", color=(90, 30, 20)),
        "middle.tiff": _image_bytes("TIFF", color=(40, 80, 30)),
    }
    for filename, data in paths.items():
        (tmp_path / filename).write_bytes(data)
    before = {filename: (tmp_path / filename).read_bytes() for filename in paths}

    first = scan_input_folder(tmp_path)
    second = scan_input_folder(tmp_path)

    assert list(first.records) == list(second.records)
    assert [record["filename"] for record in first.records.values()] == [
        "Alpha.JPG", "middle.tiff", "zeta.png",
    ]
    assert {filename: (tmp_path / filename).read_bytes() for filename in paths} == before
