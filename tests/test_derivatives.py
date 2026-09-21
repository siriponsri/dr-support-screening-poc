import base64
import hashlib
import io
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from dr_support.api import create_app
from dr_support.contracts import InferenceRequest, Lesion, LesionResult, Provenance
from dr_support.images import BridgeImage
from dr_support.imaging import (
    CoordinateMapping,
    DerivativePurpose,
    DerivativeService,
    map_lesion_result_to_review,
)
from dr_support.providers.remote import RemoteGlobalProvider
from dr_support.services.admission import legacy_admission


def _raster_bytes(format_name: str, size: tuple[int, int] = (320, 240)) -> bytes:
    image = Image.new("RGB", size, (80, 35, 25))
    stream = io.BytesIO()
    image.save(stream, format=format_name)
    return stream.getvalue()


def _image(data: bytes, filename: str, source_type: str = "PUBLIC") -> BridgeImage:
    return BridgeImage(
        image_id=hashlib.sha256(data).hexdigest(),
        data=data,
        source_type=source_type,
        source="WORKSPACE_INPUT",
        filename=filename,
        media_type={".jpg": "image/jpeg", ".png": "image/png", ".tiff": "image/tiff"}[Path(filename).suffix],
    )


@pytest.mark.parametrize("format_name", ["JPEG", "PNG"])
def test_jpeg_png_display_endpoint_reuses_immutable_source_bytes(tmp_path, format_name):
    suffix = ".jpg" if format_name == "JPEG" else ".png"
    source = _raster_bytes(format_name)
    image = _image(source, f"fundus{suffix}")
    app = create_app(tmp_path / f"{format_name.lower()}.sqlite", include_samples=False)
    app.state.images[image.image_id] = image
    app.state.admissions[image.image_id] = legacy_admission(image)
    client = TestClient(app)

    case = client.get(f"/v1/cases/{image.image_id}")
    display = client.get(f"/v1/images/{image.image_id}/display")
    original = client.get(f"/v1/images/{image.image_id}")

    assert case.status_code == 200
    assert case.json()["image_url"] == f"/v1/images/{image.image_id}/display"
    assert display.status_code == 200
    assert display.headers["content-type"].startswith(image.media_type)
    assert display.content == source
    assert original.content == source
    assert display.headers["x-source-sha256"] == hashlib.sha256(source).hexdigest()
    assert display.headers["x-derivative-sha256"] == hashlib.sha256(display.content).hexdigest()


def test_tiff_display_derivative_is_browser_safe_and_source_remains_untouched(tmp_path):
    source = _raster_bytes("TIFF")
    image = _image(source, "fundus.tiff")
    app = create_app(tmp_path / "state.sqlite", include_samples=False)
    app.state.images[image.image_id] = image
    app.state.admissions[image.image_id] = legacy_admission(image)
    client = TestClient(app)

    display = client.get(f"/v1/images/{image.image_id}/display")
    original = client.get(f"/v1/images/{image.image_id}")

    assert display.status_code == 200
    assert display.headers["content-type"].startswith("image/png")
    with Image.open(io.BytesIO(display.content)) as decoded:
        assert decoded.size == image.size
        assert decoded.format == "PNG"
    assert original.content == source
    assert image.data == source
    assert display.headers["x-source-sha256"] == image.sha256
    assert display.headers["x-derivative-sha256"] != image.sha256


def test_analysis_derivative_cache_and_lineage_are_source_anchored():
    source = _raster_bytes("TIFF")
    image = _image(source, "fundus.tiff")
    service = DerivativeService()

    first = service.prepare_analysis(image)
    second = service.prepare_analysis(image)

    assert first is second
    assert first.lineage.purpose is DerivativePurpose.ANALYSIS
    assert first.lineage.source_sha256 == image.sha256
    assert first.lineage.derivative_sha256 == hashlib.sha256(first.data).hexdigest()
    assert first.lineage.derivative_sha256 != image.sha256
    assert first.audit_record()["source_sha256"] == image.sha256
    assert first.audit_record()["analysis_sha256"] == first.lineage.derivative_sha256


def test_coordinate_mapping_returns_analysis_boxes_to_canonical_pixels():
    mapping = CoordinateMapping(
        kind="SCALE",
        canonical_width=1000,
        canonical_height=500,
        analysis_width=500,
        analysis_height=250,
        scale_x=2,
        scale_y=2,
    )
    result = LesionResult(
        model_id="prism-dr-5fold",
        model_version="test",
        modality="CFP",
        width=500,
        height=250,
        lesions=[Lesion(
            source_label="MA",
            canonical_label="MICROANEURYSM",
            rectangle=(25, 10, 125, 50),
            score=0.8,
        )],
        provenance=Provenance(
            image_sha256="a" * 64,
            source_type="PUBLIC",
            preprocessing="test",
            source_revision="test",
        ),
    )

    mapped = map_lesion_result_to_review(result, mapping)

    assert mapped.width == 1000 and mapped.height == 500
    assert mapped.lesions[0].rectangle == (50, 20, 250, 100)
    assert mapping.map_review_point(250, 100) == (125, 50)


def test_remote_payload_hashes_exact_analysis_bytes(monkeypatch):
    source = _raster_bytes("TIFF")
    image = _image(source, "fundus.tiff")
    analysis_image, derivative = DerivativeService().analysis_image(image)
    captured = {}

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured["payload"] = payload
        raw = base64.b64decode(payload["image_b64"], validate=True)
        body = {
            "schema_version": "bridge.v1",
            "model_id": "retfound-aptos5",
            "model_version": "remote-test",
            "modality": "CFP",
            "state": "UNSUPPORTED",
            "grade": None,
            "probabilities": [],
            "confidence": None,
            "warnings": [],
            "provenance": {
                "image_sha256": hashlib.sha256(raw).hexdigest(),
                "source_type": "PUBLIC",
                "preprocessing": "remote-test",
                "source_revision": "remote-test",
                "checkpoint_sha256": {},
            },
        }
        return httpx.Response(200, json=body)

    monkeypatch.setenv("REMOTE_MODEL_URL", "https://remote.test")
    provider = RemoteGlobalProvider(transport=httpx.MockTransport(handle))
    result = provider.infer(
        InferenceRequest(image_id=image.image_id, model_id=provider.model_id),
        analysis_image,
    )

    payload = captured["payload"]
    transmitted = base64.b64decode(payload["image_b64"], validate=True)
    assert transmitted == derivative.data
    assert payload["image_sha256"] == hashlib.sha256(transmitted).hexdigest()
    assert payload["image_sha256"] == derivative.lineage.derivative_sha256
    assert payload["image_sha256"] != image.sha256
    assert result.provenance.image_sha256 == payload["image_sha256"]


def test_s5c_inference_persists_lineage_and_s4_keeps_source_identity(monkeypatch, tmp_path):
    source = _raster_bytes("TIFF")
    image = _image(source, "fundus.tiff")
    captured = {}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=[])
        payload = json.loads(request.content)
        captured["payload"] = payload
        return httpx.Response(200, json={
            "schema_version": "bridge.v1",
            "model_id": "retfound-aptos5",
            "model_version": "remote-test",
            "modality": "CFP",
            "state": "UNSUPPORTED",
            "grade": None,
            "probabilities": [],
            "confidence": None,
            "warnings": [],
            "provenance": {
                "image_sha256": payload["image_sha256"],
                "source_type": "PUBLIC",
                "preprocessing": "remote-test",
                "source_revision": "remote-test",
                "checkpoint_sha256": {},
            },
        })

    monkeypatch.setenv("MODEL_RUNTIME", "remote")
    monkeypatch.setenv("REMOTE_MODEL_URL", "https://remote.test")
    app = create_app(tmp_path / "state.sqlite", include_samples=False)
    app.state.images[image.image_id] = image
    app.state.admissions[image.image_id] = legacy_admission(image)
    for provider in app.state.providers.values():
        provider._transport = httpx.MockTransport(handle)
    client = TestClient(app)

    response = client.post("/v1/infer/global", json={
        "image_id": image.image_id,
        "modality": "CFP",
        "model_id": "retfound-aptos5",
    })
    case = client.get(f"/v1/cases/{image.image_id}").json()
    manifest = client.get("/v1/dataset/manifest").json()

    assert response.status_code == 200
    assert captured["payload"]["image_sha256"] != image.sha256
    assert case["image_sha256"] == image.sha256
    assert case["source_sha256"] == image.sha256
    assert case["analysis_derivative"]["source_sha256"] == image.sha256
    assert case["analysis_derivative"]["analysis_sha256"] == captured["payload"]["image_sha256"]
    assert manifest["images"][0]["image_sha256"] == image.sha256
