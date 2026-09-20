"""Connection probing and safe state for provider-neutral Model APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


EXPECTED_MODELS = {
    "retfound-aptos5": "global",
    "prism-dr-5fold": "lesion-roi",
}


@dataclass(frozen=True)
class ModelConnection:
    name: str
    url: str
    token: str | None = None


@dataclass(frozen=True)
class ModelGatewayProbe:
    verified: bool
    status: str
    message: str
    models: tuple[dict[str, Any], ...] = ()


def _headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _model_summary(body: object) -> tuple[dict[str, Any], ...] | None:
    if not isinstance(body, list):
        return None
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in body:
        if not isinstance(item, dict):
            continue
        model_id = item.get("model_id")
        if model_id not in EXPECTED_MODELS or model_id in seen:
            continue
        seen.add(model_id)
        status = item.get("status")
        summaries.append({
            "model_id": model_id,
            "ready": status not in {"UNAVAILABLE", "ERROR", "ASSET_REQUIRED"},
            "status": status if isinstance(status, str) else None,
        })
    if seen != set(EXPECTED_MODELS):
        return None
    return tuple(sorted(summaries, key=lambda item: item["model_id"]))


def probe_model_connection(
    base_url: str,
    token: str | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ModelGatewayProbe:
    """Verify the existing Model API contract without changing providers."""

    headers = _headers(token)
    client_options: dict[str, Any] = {
        "timeout": httpx.Timeout(5.0),
        "follow_redirects": False,
    }
    if transport is not None:
        client_options["transport"] = transport
    try:
        with httpx.Client(**client_options) as client:
            health = client.get(f"{base_url}/health", headers=headers)
            if health.status_code != 200:
                return ModelGatewayProbe(False, "UNAVAILABLE", "Connection could not be verified.")
            models = client.get(f"{base_url}/v1/models", headers=headers)
            if models.status_code != 200:
                return ModelGatewayProbe(False, "UNAVAILABLE", "Connection could not be verified.")
            try:
                summaries = _model_summary(models.json())
            except ValueError:
                summaries = None
    except (httpx.HTTPError, ValueError, OSError):
        return ModelGatewayProbe(False, "UNAVAILABLE", "Connection could not be verified.")

    if summaries is None:
        return ModelGatewayProbe(False, "UNAVAILABLE", "Connection could not be verified.")
    return ModelGatewayProbe(True, "CONNECTED", "Connection verified.", summaries)


def response_payload(
    connection: ModelConnection | None,
    *,
    probe: ModelGatewayProbe | None = None,
) -> dict[str, Any]:
    """Build the public connection payload without ever including the token."""

    if connection is None:
        return {
            "name": None,
            "url": None,
            "token_configured": False,
            "status": "NOT_CONFIGURED",
            "message": "No Model API connection is configured.",
            "models": [],
        }
    current = probe or ModelGatewayProbe(
        False,
        "UNVERIFIED",
        "Connection could not be verified.",
    )
    return {
        "name": connection.name,
        "url": connection.url,
        "token_configured": bool(connection.token),
        "status": current.status,
        "message": current.message,
        "models": list(current.models),
    }
