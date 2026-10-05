"""Capability and modality routing for review-time model requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


READY_STATUSES = frozenset({"LOADED", "SYNTHETIC_FIXTURE"})
BLOCKED_RELEASE_STATUSES = frozenset({"DISABLED", "COMPARATOR_ONLY", "DEFERRED"})
CFP_ONLY_MODEL_IDS = frozenset({"retfound-aptos5", "prism-dr-5fold"})


class CapabilityRoutingError(ValueError):
    """Raised when a request cannot use the advertised capability."""


def release_status_blocked(status: object) -> bool:
    normalized = str(status or "").strip().upper()
    return (
        normalized in BLOCKED_RELEASE_STATUSES
        or normalized.startswith("BLOCKED")
        or normalized.startswith("DEFERRED")
    )


def model_supports_modality(model_id: str, modality: str) -> bool:
    """Keep known CFP model identities from being routed to UWF input."""

    return not (modality == "UWF" and model_id in CFP_ONLY_MODEL_IDS)


@dataclass(frozen=True)
class CapabilityRoute:
    model_id: str
    task: str
    modality: str
    capability_id: str | None
    supported_modalities: tuple[str, ...]
    status: str


def _advertised_modalities(descriptor: Mapping[str, Any]) -> tuple[str, ...]:
    values = descriptor.get("modalities")
    if not isinstance(values, list):
        values = descriptor.get("supported_modalities")
    if not isinstance(values, list):
        return ()
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value.strip()))


def route_capability(
    descriptor: Mapping[str, Any],
    *,
    model_id: str,
    task: str,
    modality: str,
) -> CapabilityRoute:
    """Validate a request against one current, advertised provider descriptor.

    The descriptor is intentionally supplied by the live provider metadata
    path. Committed registry entries can explain unavailable capabilities but
    cannot make a request actionable by themselves.
    """

    if str(descriptor.get("model_id") or "") != model_id:
        raise CapabilityRoutingError("The selected model is not currently advertised by the Model API.")
    if str(descriptor.get("task") or "") != task:
        raise CapabilityRoutingError("The selected model does not provide the requested review task.")
    status = str(descriptor.get("status") or "")
    if status not in READY_STATUSES:
        raise CapabilityRoutingError("No ready model is advertised for this request; manual review remains available.")
    if release_status_blocked(descriptor.get("release_status")):
        raise CapabilityRoutingError("The selected model is not available for review use; manual review remains available.")
    if not model_supports_modality(model_id, modality):
        raise CapabilityRoutingError("This model is validated for CFP images only; manual review remains available.")
    modalities = _advertised_modalities(descriptor)
    if modality not in modalities:
        raise CapabilityRoutingError("No ready model is advertised for this image type; manual review remains available.")
    if task == "global" and modality == "UWF" and "UWF" not in modalities:
        raise CapabilityRoutingError("UWF grading requires an advertised ready UWF grading capability.")
    return CapabilityRoute(
        model_id=model_id,
        task=task,
        modality=modality,
        capability_id=(str(descriptor["capability_id"]) if descriptor.get("capability_id") else None),
        supported_modalities=modalities,
        status=status,
    )
