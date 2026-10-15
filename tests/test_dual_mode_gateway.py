"""Focused contract tests for the private portable model gateway."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
from fastapi.testclient import TestClient


_GATEWAY_PATH = Path(__file__).parents[1] / "deployment" / "dual-mode" / "gateway" / "app.py"
_SPEC = importlib.util.spec_from_file_location("dual_mode_gateway", _GATEWAY_PATH)
assert _SPEC and _SPEC.loader
_gateway = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_gateway)


def test_gateway_requires_bearer_for_metadata(monkeypatch):
    monkeypatch.setenv("REMOTE_MODEL_TOKEN", "test-token")
    client = TestClient(_gateway.app)
    assert client.get("/health").status_code == 200
    assert client.get("/v1/models").status_code == 401
    assert client.get("/v1/capabilities").status_code == 401
    assert client.get("/v1/models", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_gateway_routes_modality_and_lesions(monkeypatch):
    monkeypatch.setenv("USPEC_URL", "http://uspec")
    monkeypatch.setenv("RETFOUND_URL", "http://retfound")
    monkeypatch.setenv("PRISM_URL", "http://prism")
    assert _gateway._backend("/v1/predict/dr", {"modality": "UWF"}) == "http://uspec"
    assert _gateway._backend("/v1/predict/dr", {"modality": "CFP"}) == "http://retfound"
    assert _gateway._backend("/v1/predict/lesions") == "http://prism"

    try:
        _gateway._backend("/v1/predict/dr", {"modality": "UNKNOWN"})
    except Exception as exc:  # HTTPException without exposing backend details
        assert getattr(exc, "status_code", None) == 422
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("unknown modality was accepted")


def test_gateway_forwards_authenticated_request_without_logging_token(monkeypatch):
    monkeypatch.setenv("REMOTE_MODEL_TOKEN", "test-token")
    monkeypatch.setenv("USPEC_URL", "http://uspec")
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            del args

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs["headers"]
            captured["body"] = kwargs["content"]
            return httpx.Response(200, json={"state": "PASS"})

    monkeypatch.setattr(_gateway.httpx, "AsyncClient", FakeAsyncClient)
    client = TestClient(_gateway.app)
    response = client.post(
        "/v1/predict/dr",
        headers={"Authorization": "Bearer test-token"},
        json={"modality": "UWF", "image_id": "synthetic-case"},
    )
    assert response.status_code == 200
    assert captured["url"] == "http://uspec/v1/predict/dr"
    assert captured["headers"] == {
        "content-type": "application/json",
        "authorization": "Bearer test-token",
    }
    assert "test-token" not in response.text


def test_gateway_masks_backend_server_errors(monkeypatch):
    monkeypatch.setenv("REMOTE_MODEL_TOKEN", "test-token")
    monkeypatch.setenv("PRISM_URL", "http://prism")

    class FailedAsyncClient:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            del args

        async def post(self, *args, **kwargs):
            del args, kwargs
            return httpx.Response(500, text="backend secret and traceback")

    monkeypatch.setattr(_gateway.httpx, "AsyncClient", FailedAsyncClient)
    response = TestClient(_gateway.app).post(
        "/v1/predict/lesions",
        headers={"Authorization": "Bearer test-token"},
        json={"modality": "UWF", "image_id": "synthetic-case"},
    )
    assert response.status_code == 503
    assert "backend secret" not in response.text
    assert "Model backend unavailable" in response.text


def test_gateway_deduplicates_combined_backend_discovery(monkeypatch):
    monkeypatch.setenv("USPEC_URL", "http://combined")
    monkeypatch.setenv("RETFOUND_URL", "http://retfound")
    monkeypatch.setenv("PRISM_URL", "http://combined")

    assert _gateway._configured_backends() == ("http://combined", "http://retfound")
    assert _gateway._merge_discovery([
        [
            {"model_id": "uspec-uwf-grading"},
            {"model_id": "prism-dr-5fold"},
            {"model_id": "retfound-aptos5", "ready": False},
        ],
        [
            {"model_id": "prism-dr-5fold"},
            {"model_id": "retfound-aptos5", "ready": True},
        ],
    ]) == [
        {"model_id": "uspec-uwf-grading"},
        {"model_id": "prism-dr-5fold"},
        {"model_id": "retfound-aptos5", "ready": True},
    ]


def test_gateway_supports_versioned_prediction_routes(monkeypatch):
    monkeypatch.setenv("REMOTE_MODEL_TOKEN", "test-token")
    monkeypatch.setenv("USPEC_URL", "http://uspec")
    monkeypatch.setenv("PRISM_URL", "http://prism")
    captured: list[str] = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            del args

        async def post(self, url, **kwargs):
            del kwargs
            captured.append(url)
            return httpx.Response(200, json={"status": "PASS"})

    monkeypatch.setattr(_gateway.httpx, "AsyncClient", FakeAsyncClient)
    client = TestClient(_gateway.app)
    headers={"Authorization": "Bearer test-token"}
    assert client.post("/v2/predict/dr", headers=headers, json={"modality": "UWF"}).status_code == 200
    assert client.post("/v2/predict/lesions", headers=headers, json={"modality": "UWF"}).status_code == 200
    assert captured == ["http://uspec/v2/predict/dr", "http://prism/v2/predict/lesions"]
