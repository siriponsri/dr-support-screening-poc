"""Connection probing and safe state for provider-neutral Model APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .capability_routing import (
    EXPECTED_MODEL_TASKS,
    capability_is_qualified,
    release_status_blocked,
)


EXPECTED_MODELS = EXPECTED_MODEL_TASKS


def _actionable_capability(item: dict[str, Any], model_id: str, status: object) -> bool:
    if status != "LOADED" or item.get("ready") is False:
        return False
    if release_status_blocked(item.get("release_status")):
        return False
    return capability_is_qualified(item)


@dataclass(frozen=True)
class ModelConnection:
    name: str
    url: str
    token: str | None = None


@dataclass(frozen=True)
class ModelGatewayProbe:
    server_reachable: bool
    api_contract_valid: bool
    connection_verified: bool
    capabilities_ready: bool
    status: str
    message: str
    models: tuple[dict[str, Any], ...] = ()

    @property
    def verified(self) -> bool:
        """Compatibility alias for callers that mean connection verification."""

        return self.connection_verified


def _headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _model_summary(body: object) -> tuple[dict[str, Any], ...] | None:
    """Validate capability discovery without requiring a legacy model pair.

    The old RETFound/PRISM pair remains valid, but a future Model API may
    expose only one qualified capability or a different provider identity.
    """
    if not isinstance(body, list):
        return None
    if not body:
        return None
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in body:
        if not isinstance(item, dict):
            return None
        model_id = item.get("model_id")
        if not isinstance(model_id, str) or not model_id.strip() or model_id in seen:
            return None
        seen.add(model_id)
        status = item.get("status")
        if status is not None and (not isinstance(status, str) or not status.strip()):
            return None
        if "ready" in item and not isinstance(item["ready"], bool):
            return None
        modalities = item.get("modalities")
        if modalities is not None and (
            not isinstance(modalities, list)
            or any(not isinstance(modality, str) or not modality.strip() for modality in modalities)
        ):
            return None
        summaries.append({
            "model_id": model_id,
            "ready": _actionable_capability(item, model_id, status),
            "status": status if isinstance(status, str) else None,
            "capability_id": item.get("capability_id") if isinstance(item.get("capability_id"), str) else None,
            "task": item.get("task") if isinstance(item.get("task"), str) else EXPECTED_MODELS.get(model_id),
            "modalities": list(modalities or []) if isinstance(modalities, list) else [],
            "revision": item.get("revision") if isinstance(item.get("revision"), str) else item.get("model_version") if isinstance(item.get("model_version"), str) else None,
            "preprocessing": item.get("preprocessing") if isinstance(item.get("preprocessing"), str) else item.get("preprocessing_version") if isinstance(item.get("preprocessing_version"), str) else None,
            "release_status": item.get("release_status") if isinstance(item.get("release_status"), str) else None,
        })
    if not summaries:
        return None
    return tuple(sorted(summaries, key=lambda item: item["model_id"]))


def _health_contract_valid(body: object) -> bool:
    if not isinstance(body, dict) or body.get("status") not in {"PASS", "PASS_WITH_WARNINGS", "FAIL"}:
        return False
    if not isinstance(body.get("assets_verified"), bool):
        return False
    warnings = body.get("warnings")
    if warnings is not None and (
        not isinstance(warnings, list)
        or any(not isinstance(item, str) for item in warnings)
    ):
        return False
    if body.get("status") == "FAIL" and not warnings:
        return False
    return True


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
                return ModelGatewayProbe(
                    True, False, False, False, "UNAVAILABLE", "Model API health could not be verified."
                )
            try:
                health_body = health.json()
            except ValueError:
                return ModelGatewayProbe(
                    True, False, False, False, "UNVERIFIED", "Model API health returned invalid JSON."
                )
            if not _health_contract_valid(health_body):
                return ModelGatewayProbe(
                    True, False, False, False, "UNVERIFIED", "Model API health did not match the expected contract."
                )
            health_ok = (
                health_body["status"] in {"PASS", "PASS_WITH_WARNINGS"}
                and health_body["assets_verified"] is True
            )

            models = client.get(f"{base_url}/v1/models", headers=headers)
            if models.status_code != 200:
                return ModelGatewayProbe(
                    True, False, False, False, "UNAVAILABLE", "Model API capabilities could not be verified."
                )
            try:
                summaries = _model_summary(models.json())
            except ValueError:
                summaries = None
    except (httpx.HTTPError, ValueError, OSError):
        return ModelGatewayProbe(
            False, False, False, False, "UNAVAILABLE", "Model API server could not be reached."
        )

    if summaries is None:
        return ModelGatewayProbe(
            True, False, False, False, "UNVERIFIED", "Model API capabilities did not match the expected contract."
        )
    capabilities_ready = any(model["ready"] for model in summaries)
    if not health_ok:
        summaries = tuple({**model, "ready": False} for model in summaries)
        return ModelGatewayProbe(
            True,
            True,
            False,
            False,
            "UNAVAILABLE",
            "Model API health reports failure; connection is not verified.",
            summaries,
        )
    message = "Connection verified; at least one model capability is ready." if capabilities_ready else (
        "Connection verified, but no model capability is ready."
    )
    return ModelGatewayProbe(True, True, True, capabilities_ready, "CONNECTED", message, summaries)


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
            "server_reachable": False,
            "api_contract_valid": False,
            "connection_verified": False,
            "capabilities_ready": False,
            "models": [],
        }
    current = probe or ModelGatewayProbe(
        False,
        False,
        False,
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
        "server_reachable": current.server_reachable,
        "api_contract_valid": current.api_contract_valid,
        "connection_verified": current.connection_verified,
        "capabilities_ready": current.capabilities_ready,
        "models": list(current.models),
    }
