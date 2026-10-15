"""Bridge v2.1 compatibility for experimental PRISM UWF processing evidence."""

from __future__ import annotations

import base64
import io
from typing import Any, Literal

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import Field, ValidationError
from PIL import Image

from dr_support.contracts import (
    Contract,
    GlobalResult,
    LesionResult,
    Phase3ResultEnvelope,
    Provenance,
)
from dr_support.images import synthetic_image
from dr_support.providers.remote import RemoteModelProvider, RemoteSchemaError
from dr_support.providers.uspec import USPEC
from dr_support.services.model_api import create_app


class StrictLegacyBridgeV2(Contract):
    """Minimal strict v2-only client model retained to assert fail-closed behavior."""

    schema_version: Literal["bridge.v2"] = "bridge.v2"
    invocation_id: str
    capability_id: str
    task: str
    model: dict[str, Any]
    input: dict[str, Any]
    result: dict[str, Any] | None = None
    explanation: dict[str, Any]
    runtime: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    status: str


def _fov_evidence(*, width: int, height: int) -> dict[str, Any]:
    mask = Image.new("L", (width, height), 255)
    stream = io.BytesIO()
    mask.save(stream, format="PNG")
    return {
        "status": "READY",
        "mask_version": "uwf_white_rim_fov_v1",
        "mask_sha256": "a" * 64,
        "source_rgb_sha256": "b" * 64,
        "image_width": width,
        "image_height": height,
        "boundary_confidence": 0.91,
        "excluded_fraction": 0.12,
        "boundary": [[5, height // 2], [width // 2, 5], [width - 5, height // 2]],
        "used_for_model_input": True,
        "field_mask_png_base64": base64.b64encode(stream.getvalue()).decode("ascii"),
    }


def _lesion_result(image_sha256: str, modality: str, *, width: int, height: int) -> LesionResult:
    return LesionResult(
        model_id="prism-dr-5fold",
        model_version="79637440a535e4f8118e939d3787121f82180125",
        modality=modality,
        width=width,
        height=height,
        lesions=[{
            "source_label": "EX",
            "canonical_label": "HARD_EXUDATE",
            "rectangle": [10.0, 12.0, 25.0, 27.0],
            "score": 0.73,
        }],
        warnings=["Experimental PRISM UWF assistance; not validated for UWF."],
        provenance=Provenance(
            image_sha256=image_sha256,
            source_type="SYNTHETIC",
            preprocessing="locked-prism-pipeline",
            source_revision="79637440a535e4f8118e939d3787121f82180125",
        ),
    )


def _processing_evidence(image_sha256: str, *, width: int, height: int) -> dict[str, Any]:
    fov = _fov_evidence(width=width, height=height)
    return {
        "input_image_sha256": image_sha256,
        "processing_mode": "PREPARED",
        "native_roi_status": "SUCCEEDED",
        "native_roi_bbox": [5, 5, width - 5, height - 5],
        "external_fov_status": "READY",
        "fov_used_for_model_input": True,
        "raw_boundary_classes": ["INSIDE_ANALYSIS_FIELD"],
        "analysis_field": fov,
    }


class _FakePrism:
    model_id = "prism-dr-5fold"
    task = "lesion-roi"
    capability_id = "core_lesion_localization"
    loaded = True
    assets_verified = True
    device = "cpu"
    last_inference_ms = 1.0

    def __init__(self) -> None:
        self.last_processing_evidence = None

    def metadata(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task": self.task,
            "capability_id": self.capability_id,
            "revision": "79637440a535e4f8118e939d3787121f82180125",
            "status": "LOADED",
            "modalities": ["CFP", "UWF"],
        }

    def infer(self, request, image) -> LesionResult:
        width, height = image.size
        if request.modality == "UWF":
            self.last_processing_evidence = _processing_evidence(
                image.sha256, width=width, height=height,
            )
        else:
            self.last_processing_evidence = None
        return _lesion_result(image.sha256, request.modality, width=width, height=height)


class _FakeUspec:
    model_id = USPEC.model_id
    task = "global"
    capability_id = USPEC.capability_id
    loaded = True
    assets_verified = True
    device = "cpu"
    last_inference_ms = 1.0

    def metadata(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task": self.task,
            "capability_id": self.capability_id,
            "revision": USPEC.model_version,
            "status": "LOADED",
            "modalities": ["UWF"],
        }

    def infer(self, request, image) -> GlobalResult:
        return GlobalResult(
            model_id=self.model_id,
            model_version=USPEC.model_version,
            modality=request.modality,
            state="AI_SUGGESTION",
            grade=1,
            probabilities=[0.1, 0.6, 0.2, 0.05, 0.05],
            confidence=0.6,
            provenance=Provenance(
                image_sha256=image.sha256,
                source_type="SYNTHETIC",
                preprocessing="uspec-source-rgb-v1",
                source_revision=USPEC.model_version,
            ),
        )


def _phase3_payload(image, *, model_id: str, task: str, modality: str) -> dict[str, Any]:
    width, height = image.size
    digest = image.sha256
    if model_id == USPEC.model_id:
        capability_id = USPEC.capability_id
        model_version = USPEC.model_version
        representation = USPEC.representation
        transform = USPEC.transform
    else:
        capability_id = "core_lesion_localization"
        model_version = "79637440a535e4f8118e939d3787121f82180125"
        representation = "uwf-source-analysis-v1" if modality == "UWF" else "original-source-v1"
        transform = "analysis-uwf-unmasked-source-v1" if modality == "UWF" else "analysis-source-v1"
    return {
        "invocation_id": f"invoke-{model_id[:16]}-{modality.lower()}",
        "capability_id": capability_id,
        "task": task,
        "model_id": model_id,
        "model_version": model_version,
        "image_id": image.image_id,
        "modality": modality,
        "image_b64": base64.b64encode(image.data).decode("ascii"),
        "image_sha256": digest,
        "source_sha256": digest,
        "source_origin": "SYNTHETIC",
        "analysis_sha256": digest,
        "representation_version": representation,
        "transform_id": transform,
        "request_case_revision": 0,
        "width": width,
        "height": height,
    }


def test_model_api_versions_only_prepared_prism_uwf_responses(monkeypatch):
    monkeypatch.setenv("APP_PROFILE", "model_api")
    monkeypatch.setenv("MODEL_RUNTIME", "local")
    monkeypatch.setenv("MODEL_API_PROVIDER_SET", "combined")
    monkeypatch.delenv("MODEL_REQUIRE_VERIFIED_ASSETS", raising=False)
    app = create_app(device_strict=False)
    app.state.providers["prism-dr-5fold"] = _FakePrism()
    app.state.providers[USPEC.model_id] = _FakeUspec()
    client = TestClient(app)
    image = synthetic_image()

    cfp = client.post(
        "/v2/predict/lesions",
        json=_phase3_payload(image, model_id="prism-dr-5fold", task="lesion-roi", modality="CFP"),
    )
    assert cfp.status_code == 200, cfp.text
    cfp_body = cfp.json()
    assert cfp_body["schema_version"] == "bridge.v2"
    assert "prism_processing" not in cfp_body
    StrictLegacyBridgeV2.model_validate(cfp_body)

    uwf = client.post(
        "/v2/predict/lesions",
        json=_phase3_payload(image, model_id="prism-dr-5fold", task="lesion-roi", modality="UWF"),
    )
    assert uwf.status_code == 200, uwf.text
    uwf_body = uwf.json()
    assert uwf_body["schema_version"] == "bridge.v2.1"
    assert uwf_body["prism_processing"]["processing_mode"] == "PREPARED"
    assert uwf_body["prism_processing"]["analysis_field"]["used_for_model_input"] is True
    assert len(uwf_body["prism_processing"]["raw_boundary_classes"]) == 1
    with pytest.raises(ValidationError):
        StrictLegacyBridgeV2.model_validate(uwf_body)

    uspec = client.post(
        "/v2/predict/dr",
        json=_phase3_payload(image, model_id=USPEC.model_id, task="global", modality="UWF"),
    )
    assert uspec.status_code == 200, uspec.text
    uspec_body = uspec.json()
    assert uspec_body["schema_version"] == "bridge.v2"
    assert "prism_processing" not in uspec_body
    StrictLegacyBridgeV2.model_validate(uspec_body)


def test_remote_provider_roundtrips_bridge_v2_1_prism_processing():
    image = synthetic_image()
    width, height = image.size
    digest = image.sha256
    invocation_id = "invoke-remote-prism-uwf"
    evidence = _processing_evidence(digest, width=width, height=height)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/predict/lesions"
        sent = __import__("json").loads(request.content)
        assert sent["model_id"] == "prism-dr-5fold"
        envelope = Phase3ResultEnvelope(
            schema_version="bridge.v2.1",
            invocation_id=invocation_id,
            capability_id="core_lesion_localization",
            task="lesion-roi",
            model={
                "id": "prism-dr-5fold",
                "version": "79637440a535e4f8118e939d3787121f82180125",
                "trained_domain": "CFP",
                "supported_modalities": ["CFP", "UWF"],
                "release_status": "RESEARCH_ONLY",
            },
            input={
                "image_id": image.image_id,
                "source_sha256": digest,
                "source_origin": "SYNTHETIC",
                "input_modality": "UWF",
                "analysis_sha256": digest,
                "representation_version": "uwf-source-analysis-v1",
                "transform_id": "analysis-uwf-unmasked-source-v1",
                "request_case_revision": 0,
            },
            result=_lesion_result(digest, "UWF", width=width, height=height),
            prism_processing=evidence,
            explanation={
                "status": "UNAVAILABLE",
                "invocation_id": invocation_id,
                "model_id": "prism-dr-5fold",
                "source_sha256": digest,
                "analysis_sha256": digest,
                "warning": "No typed explanation evidence is available.",
            },
            warnings=["Experimental PRISM UWF assistance; not validated for UWF."],
            status="APPLIED",
        )
        return httpx.Response(200, json=envelope.model_dump(mode="json", exclude_none=True))

    provider = RemoteModelProvider(
        "prism-dr-5fold",
        "lesion-roi",
        base_url="https://model-api.test",
        transport=httpx.MockTransport(handler),
    )
    request = type("ReviewRequest", (), {
        "image_id": image.image_id,
        "model_id": "prism-dr-5fold",
        "modality": "UWF",
    })()
    result = provider.infer_phase3_lesions(
        request,
        image,
        capability_id="core_lesion_localization",
        model_version="79637440a535e4f8118e939d3787121f82180125",
        source_sha256=digest,
        source_origin="SYNTHETIC",
        representation_version="uwf-source-analysis-v1",
        transform_id="analysis-uwf-unmasked-source-v1",
        request_case_revision=0,
        invocation_id=invocation_id,
    )

    assert result.model_id == "prism-dr-5fold"
    assert result.modality == "UWF"
    assert len(result.lesions) == 1
    assert provider.last_processing_evidence["processing_mode"] == "PREPARED"
    assert provider.last_processing_evidence["raw_boundary_classes"] == ["INSIDE_ANALYSIS_FIELD"]
    assert provider.last_remote_revision == "79637440a535e4f8118e939d3787121f82180125"


def test_remote_provider_rejects_v2_uwf_response_without_processing_evidence():
    image = synthetic_image()
    digest = image.sha256
    invocation_id = "invoke-remote-prism-uwf-v2-only"

    def handler(_request: httpx.Request) -> httpx.Response:
        envelope = Phase3ResultEnvelope(
            schema_version="bridge.v2",
            invocation_id=invocation_id,
            capability_id="core_lesion_localization",
            task="lesion-roi",
            model={
                "id": "prism-dr-5fold",
                "version": "79637440a535e4f8118e939d3787121f82180125",
                "trained_domain": "CFP",
                "supported_modalities": ["CFP", "UWF"],
                "release_status": "RESEARCH_ONLY",
            },
            input={
                "image_id": image.image_id,
                "source_sha256": digest,
                "source_origin": "SYNTHETIC",
                "input_modality": "UWF",
                "analysis_sha256": digest,
                "representation_version": "uwf-source-analysis-v1",
                "transform_id": "analysis-uwf-unmasked-source-v1",
                "request_case_revision": 0,
            },
            result=_lesion_result(digest, "UWF", width=image.size[0], height=image.size[1]),
            explanation={
                "status": "UNAVAILABLE",
                "invocation_id": invocation_id,
                "model_id": "prism-dr-5fold",
                "source_sha256": digest,
                "analysis_sha256": digest,
                "warning": "No typed explanation evidence is available.",
            },
            status="APPLIED",
        )
        return httpx.Response(200, json=envelope.model_dump(mode="json", exclude_none=True))

    provider = RemoteModelProvider(
        "prism-dr-5fold",
        "lesion-roi",
        base_url="https://model-api.test",
        transport=httpx.MockTransport(handler),
    )
    request = type("ReviewRequest", (), {
        "image_id": image.image_id,
        "model_id": "prism-dr-5fold",
        "modality": "UWF",
    })()

    with pytest.raises(RemoteSchemaError, match="must return Bridge v2.1"):
        provider.infer_phase3_lesions(
            request,
            image,
            capability_id="core_lesion_localization",
            model_version="79637440a535e4f8118e939d3787121f82180125",
            source_sha256=digest,
            source_origin="SYNTHETIC",
            representation_version="uwf-source-analysis-v1",
            transform_id="analysis-uwf-unmasked-source-v1",
            request_case_revision=0,
            invocation_id=invocation_id,
        )


def test_model_api_rejects_external_masked_uwf_before_provider_inference(monkeypatch):
    """An attempted external mask is rejected, not quietly applied or ignored."""
    monkeypatch.setenv("APP_PROFILE", "model_api")
    monkeypatch.setenv("MODEL_RUNTIME", "local")
    monkeypatch.setenv("MODEL_API_PROVIDER_SET", "combined")
    monkeypatch.delenv("MODEL_REQUIRE_VERIFIED_ASSETS", raising=False)
    app = create_app(device_strict=False)
    provider = _FakePrism()
    app.state.providers["prism-dr-5fold"] = provider
    app.state.providers[USPEC.model_id] = _FakeUspec()
    client = TestClient(app)
    image = synthetic_image()
    payload = _phase3_payload(
        image, model_id="prism-dr-5fold", task="lesion-roi", modality="UWF",
    )
    payload.update({
        "image_sha256": "a" * 64,
        "analysis_sha256": "a" * 64,
        "mask_version": "manual-exclusion-v1",
        "transform_id": "analysis-uwf-externally-masked-v1",
    })

    response = client.post("/v2/predict/lesions", json=payload)

    assert response.status_code == 422
    assert "externally masked UWF input is not accepted" in response.json()["detail"]
    assert provider.last_processing_evidence is None
