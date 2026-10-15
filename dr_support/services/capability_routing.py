"""Capability and modality routing for review-time model requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


READY_STATUSES = frozenset({"LOADED", "SYNTHETIC_FIXTURE", "QUALIFIED_NOT_LOADED"})
BLOCKED_RELEASE_STATUSES = frozenset({"DISABLED", "COMPARATOR_ONLY", "DEFERRED"})
CFP_ONLY_MODEL_IDS = frozenset({"retfound-aptos5"})
FIXED_MODEL_MODALITIES = {
    "retfound-aptos5": frozenset({"CFP"}),
    "uspec-uwf-grading": frozenset({"UWF"}),
}
EXPECTED_MODEL_TASKS = {
    "retfound-aptos5": "global",
    "uspec-uwf-grading": "global",
    "prism-dr-5fold": "lesion-roi",
}
SUPPORTED_TASKS = frozenset(EXPECTED_MODEL_TASKS.values())
SUPPORTED_MODALITIES = frozenset({"CFP", "UWF"})
KNOWN_RELEASE_STATUSES = frozenset({
    "AVAILABLE", "QUALIFIED", "RESEARCH_ONLY",
    "COMPARATOR_ONLY", "DISABLED", "DEFERRED",
})
QUALIFICATION_PLACEHOLDERS = frozenset({
    "UNKNOWN", "NOT_REPORTED", "NOT_AVAILABLE", "NONE", "NULL", "N/A",
})


class CapabilityRoutingError(ValueError):
    """Raised when a request cannot use the advertised capability."""


def release_status_blocked(status: object) -> bool:
    normalized = str(status or "").strip().upper()
    return (
        normalized in BLOCKED_RELEASE_STATUSES
        or normalized.startswith("BLOCKED")
        or normalized.startswith("DEFERRED")
    )


def release_status_is_known(status: object) -> bool:
    normalized = str(status or "").strip().upper()
    return (
        normalized in KNOWN_RELEASE_STATUSES
        or normalized.startswith("BLOCKED")
        or normalized.startswith("DEFERRED")
    )


def model_supports_modality(model_id: str, modality: str) -> bool:
    """Enforce fixed model domains, leaving other models to their descriptors."""

    fixed_modalities = FIXED_MODEL_MODALITIES.get(model_id)
    return modality in SUPPORTED_MODALITIES and (
        fixed_modalities is None or modality in fixed_modalities
    )


def _qualified_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value.strip().upper() not in QUALIFICATION_PLACEHOLDERS
    )


def capability_is_qualified(descriptor: Mapping[str, Any]) -> bool:
    """Require the same qualification metadata used by discovery readiness."""

    model_id = descriptor.get("model_id")
    task = descriptor.get("task")
    modalities = descriptor.get("modalities")
    if not isinstance(model_id, str) or not model_id.strip():
        return False
    if not isinstance(task, str) or task not in SUPPORTED_TASKS:
        return False
    if "ready" in descriptor and not isinstance(descriptor["ready"], bool):
        return False
    expected_task = EXPECTED_MODEL_TASKS.get(model_id)
    if expected_task is not None and task != expected_task:
        return False
    if not isinstance(modalities, list) or not modalities:
        return False
    if any(not isinstance(modality, str) or not modality.strip() for modality in modalities):
        return False
    if not any(modality in SUPPORTED_MODALITIES for modality in modalities):
        return False
    fixed_modalities = FIXED_MODEL_MODALITIES.get(model_id)
    if fixed_modalities is not None and (
        not set(modalities).issubset(fixed_modalities)
        or not set(modalities).intersection(fixed_modalities)
    ):
        return False
    if model_id == "retfound-aptos5":
        # Preserve the legacy Bridge descriptor contract while keeping RETFound
        # strictly CFP-only. Some existing /v1/models servers do not publish
        # release_status/capability_id/preprocessing fields.
        return "CFP" in modalities
    if model_id == "prism-dr-5fold" and "CFP" not in modalities:
        return False
    if not release_status_is_known(descriptor.get("release_status")):
        return False
    capability_id = descriptor.get("capability_id")
    revision = descriptor.get("revision") or descriptor.get("model_version")
    preprocessing = descriptor.get("preprocessing") or descriptor.get("preprocessing_version")
    return all(_qualified_value(value) for value in (capability_id, revision, preprocessing))


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
    if "ready" in descriptor and not isinstance(descriptor["ready"], bool):
        raise CapabilityRoutingError("The advertised model readiness value is invalid; manual review remains available.")
    if status not in READY_STATUSES:
        raise CapabilityRoutingError("No ready model is advertised for this request; manual review remains available.")
    release_status = str(descriptor.get("release_status") or "").strip().upper()
    prism_lesion_comparator = (
        model_id == "prism-dr-5fold"
        and task == "lesion-roi"
        and release_status == "COMPARATOR_ONLY"
    )
    if descriptor.get("ready") is False and not prism_lesion_comparator:
        raise CapabilityRoutingError("The advertised model capability is not ready for this request; manual review remains available.")
    if release_status_blocked(release_status) and not prism_lesion_comparator:
        raise CapabilityRoutingError("The selected model is not available for review use; manual review remains available.")
    if modality not in SUPPORTED_MODALITIES:
        raise CapabilityRoutingError(
            "Confirm a supported image type before model analysis; manual review remains available."
        )
    if not model_supports_modality(model_id, modality):
        fixed_modalities = FIXED_MODEL_MODALITIES.get(model_id)
        if fixed_modalities:
            required = next(iter(fixed_modalities))
            detail = f"This model supports {required} images only."
        else:
            detail = "This model does not advertise support for this image type."
        raise CapabilityRoutingError(f"{detail} Manual review remains available.")
    modalities = _advertised_modalities(descriptor)
    if not capability_is_qualified(descriptor):
        raise CapabilityRoutingError("The advertised model capability is incomplete; manual review remains available.")
    if modality not in modalities:
        raise CapabilityRoutingError("No ready model is advertised for this image type; manual review remains available.")
    if model_id == "prism-dr-5fold" and modality == "UWF":
        if (
            descriptor.get("trained_domain") not in {"CFP", "CFP_DOMAIN"}
            or descriptor.get("uwf_use") != "EXPERIMENTAL"
            or descriptor.get("clinical_validation_status") not in {"NOT_VALIDATED_FOR_UWF", "NOT_ESTABLISHED"}
        ):
            raise CapabilityRoutingError(
                "PRISM UWF assistance requires explicit experimental and validation warnings."
            )
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
