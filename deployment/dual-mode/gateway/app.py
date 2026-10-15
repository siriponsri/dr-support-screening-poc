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
async def health() -> dict[str, Any]:
    # Keep liveness available on the loopback gateway while reporting the
    # aggregate readiness contract expected by the Review service.  A gateway
    # must not claim verified model readiness when any configured backend is
    # unavailable or has not verified its assets.
    backend_health = await _aggregate_backend_health()
    return {
        "status": backend_health["status"],
        "assets_verified": backend_health["assets_verified"],
        "service": "private-model-gateway",
        "network": "loopback-compose",
        "warnings": backend_health["warnings"],
    }


def _configured_backends() -> tuple[str, ...]:
    """Return unique configured provider endpoints in stable precedence order.

    A combined native model API commonly serves USPEC and PRISM from the same
    loopback endpoint.  Fetching discovery once avoids duplicate model IDs,
    which the review contract correctly rejects as an ambiguous capability
    registry.
    """
    result: list[str] = []
    seen: set[str] = set()
    for name in ("USPEC_URL", "RETFOUND_URL", "PRISM_URL"):
        backend = os.environ.get(name, "").strip().rstrip("/")
        if backend and backend not in seen:
            seen.add(backend)
            result.append(backend)
    return tuple(result)


def _merge_discovery(payloads: list[object]) -> list[dict[str, Any]]:
    """Merge backend discovery without exposing duplicate capability IDs.

    A dedicated provider endpoint may advertise the same model ID as a
    combined endpoint but with stronger readiness (for example, the combined
    service has not verified an optional provider). Prefer that ready
    descriptor while keeping the result deterministic.
    """
    result: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    for payload in payloads:
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            model_id = item.get("model_id")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            position = positions.get(model_id)
            if position is None:
                positions[model_id] = len(result)
                result.append(item)
            elif item.get("ready") is True and result[position].get("ready") is not True:
                result[position] = item
    return result


async def _aggregate_backend_health() -> dict[str, Any]:
    token = os.environ.get("REMOTE_MODEL_TOKEN", "")
    statuses: list[dict[str, Any]] = []
    warnings: list[str] = []
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        for backend in _configured_backends():
            try:
                response = await client.get(
                    backend + "/health",
                    headers={"authorization": f"Bearer {token}"} if token else {},
                )
                if not response.is_success:
                    warnings.append("A configured model backend health check failed.")
                    continue
                payload = response.json()
                if not isinstance(payload, dict):
                    warnings.append("A configured model backend returned invalid health data.")
                    continue
                statuses.append(payload)
            except (httpx.HTTPError, ValueError):
                warnings.append("A configured model backend could not be reached.")
    assets_verified = bool(statuses) and all(item.get("assets_verified") is True for item in statuses)
    all_ready = bool(statuses) and not warnings and all(
        item.get("status") in {"PASS", "PASS_WITH_WARNINGS"} for item in statuses
    )
    if all_ready and assets_verified:
        status = "PASS"
    elif statuses or warnings:
        status = "PASS_WITH_WARNINGS"
    else:
        status = "FAIL"
    return {
        "status": status,
        "assets_verified": assets_verified,
        "warnings": list(dict.fromkeys(warnings)),
    }


async def _discover(path: str) -> list[dict[str, Any]]:
    token = os.environ["REMOTE_MODEL_TOKEN"]
    payloads: list[object] = []
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        for backend in _configured_backends():
            try:
                response = await client.get(
                    backend + path,
                    headers={"authorization": f"Bearer {token}"},
                )
                if response.is_success:
                    payloads.append(response.json())
            except (httpx.HTTPError, ValueError):
                continue
    return _merge_discovery(payloads)


@app.get("/v1/models")
async def models(request: Request, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    if not _token_ok(authorization):
        raise HTTPException(status_code=401, detail="Bearer token rejected")
    return await _discover("/v1/models")


@app.get("/v1/capabilities")
async def capabilities(authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    if not _token_ok(authorization):
        raise HTTPException(status_code=401, detail="Bearer token rejected")
    return await _discover("/v1/capabilities")


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


@app.post("/v2/predict/dr")
async def predict_phase3_dr(request: Request) -> Response:
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid JSON") from exc
    return await _proxy("/v2/predict/dr", request, payload)


@app.post("/v2/predict/lesions")
async def predict_phase3_lesions(request: Request) -> Response:
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid JSON") from exc
    return await _proxy("/v2/predict/lesions", request, payload)
