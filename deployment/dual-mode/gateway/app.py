"""Private modality-aware gateway for the portable deployment.

The gateway is deliberately stateless: it routes only validated model requests
between the review service and isolated provider containers. It never stores
images, records, model weights, or secrets and has no public bind by default.
"""
from __future__ import annotations

import hmac
import os
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

app = FastAPI(title="DR Screening private model gateway", version="1.0.0")


def _token_ok(authorization: str | None) -> bool:
    expected = os.environ.get("REMOTE_MODEL_TOKEN", "")
    if not expected:
        return False
    presented = (authorization or "").removeprefix("Bearer ").strip()
    if not presented or len(presented) != len(expected):
        return False
    return hmac.compare_digest(presented, expected)


def _backend(path: str, payload: dict[str, Any] | None = None) -> str:
    if path.endswith("/predict/lesions"):
        name = "PRISM_URL"
    elif path.endswith("/predict/dr"):
        modality = (payload or {}).get("modality")
        if modality == "UWF":
            name = "USPEC_URL"
        elif modality == "CFP":
            name = "RETFOUND_URL"
        else:
            raise HTTPException(status_code=422, detail="Unsupported model modality")
    else:
        raise HTTPException(status_code=404, detail="Gateway route not found")
    backend = os.environ.get(name, "").strip()
    if not backend:
        raise HTTPException(status_code=503, detail="Model backend is not configured")
    return backend
    raise HTTPException(status_code=404, detail="Gateway route not found")


async def _proxy(path: str, request: Request, payload: dict[str, Any] | None = None) -> Response:
    authorization = request.headers.get("authorization")
    if not _token_ok(authorization):
        raise HTTPException(status_code=401, detail="Bearer token rejected")
    backend = _backend(path, payload)
    token = os.environ["REMOTE_MODEL_TOKEN"]
    try:
        async with httpx.AsyncClient(timeout=float(os.environ.get("GATEWAY_TIMEOUT_SECONDS", "60")), follow_redirects=False) as client:
            response = await client.post(
                backend + path,
                content=await request.body(),
                headers={"content-type": "application/json", "authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Model backend unavailable") from exc
    if response.status_code >= 500:
        return Response(
            content=b'{"detail":"Model backend unavailable"}',
            status_code=503,
            media_type="application/json",
        )
    return Response(content=response.content, status_code=response.status_code, media_type="application/json")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "PASS", "service": "private-model-gateway", "network": "loopback-compose"}


@app.get("/v1/models")
async def models(request: Request, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    if not _token_ok(authorization):
        raise HTTPException(status_code=401, detail="Bearer token rejected")
    result: list[dict[str, Any]] = []
    token = os.environ["REMOTE_MODEL_TOKEN"]
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        for name in ("USPEC_URL", "RETFOUND_URL", "PRISM_URL"):
            backend = os.environ.get(name, "").strip()
            if not backend:
                continue
            try:
                response = await client.get(backend + "/v1/models", headers={"authorization": f"Bearer {token}"})
                if response.is_success:
                    result.extend(response.json())
            except (httpx.HTTPError, ValueError):
                continue
    return result


@app.get("/v1/capabilities")
async def capabilities(authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    if not _token_ok(authorization):
        raise HTTPException(status_code=401, detail="Bearer token rejected")
    result: list[dict[str, Any]] = []
    token = os.environ["REMOTE_MODEL_TOKEN"]
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        for name in ("USPEC_URL", "RETFOUND_URL", "PRISM_URL"):
            backend = os.environ.get(name, "").strip()
            if not backend:
                continue
            try:
                response = await client.get(backend + "/v1/capabilities", headers={"authorization": f"Bearer {token}"})
                if response.is_success:
                    result.extend(response.json())
            except (httpx.HTTPError, ValueError):
                continue
    return result


@app.post("/v1/predict/dr")
async def predict_dr(request: Request) -> Response:
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid JSON") from exc
    return await _proxy("/v1/predict/dr", request, payload)


@app.post("/v1/predict/lesions")
async def predict_lesions(request: Request) -> Response:
    return await _proxy("/v1/predict/lesions", request)
