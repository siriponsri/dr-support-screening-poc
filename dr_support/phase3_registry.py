"""Deterministic, repository-safe Phase 3 capability registry.

This file contains model identity and readiness metadata only.  It never
selects a checkpoint by filesystem order and never contains weights or
credentials.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import Field

from .contracts._schema import Contract


class CapabilityDescriptor(Contract):
    capability_id: str = Field(min_length=1, max_length=120)
    provider_id: str = Field(min_length=1, max_length=120)
    task: str
    model_id: str
    model_version: str
    artifact_role: str
    artifact_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    supported_modalities: list[str] = Field(default_factory=list)
    trained_domain: str
    input_representation: str
    taxonomy_or_class_order: list[str | int] = Field(default_factory=list)
    preprocessing_version: str
    postprocessing_version: str
    explanation_types: list[str] = Field(default_factory=list)
    required_runtime_profile: str
    runtime_status: str
    domain_status: str
    clinical_validation_status: str
    rights_status: str
    release_status: str
    enabled: bool = False
    status: str
    warnings: list[str] = Field(default_factory=list)


_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "capability_id": "dr_grade",
        "provider_id": "retfound",
        "task": "global",
        "model_id": "retfound-aptos5",
        "model_version": "ae9a9ecf37857cf47b8aa9f87cd6f710d75db287",
        "artifact_role": "legacy_cfp_comparator",
        "artifact_digest": "a96b9dbcb78eff373912fb0a48d316dc35ffb0715bb2a1b9128b096d780edbbf",
        "supported_modalities": ["CFP"],
        "trained_domain": "CFP_DOMAIN",
        "input_representation": "Phase3 provider input; CFP only",
        "taxonomy_or_class_order": [0, 1, 2, 3, 4],
        "preprocessing_version": "retfound-cfp-v1",
        "postprocessing_version": "softmax-score-v1",
        "explanation_types": [],
        "required_runtime_profile": "legacy-cfp-model-api",
        "runtime_status": "NOT_LOADED",
        "domain_status": "NOT_VALIDATED_FOR_UWF",
        "clinical_validation_status": "NOT_ESTABLISHED",
        "rights_status": "RESEARCH_NON_COMMERCIAL",
        "release_status": "RESEARCH_ONLY",
        "enabled": False,
        "status": "NOT_LOADED",
        "warnings": [
            "CFP comparator; not validated for UWF.",
            "Raw model scores are not calibrated clinical probabilities.",
        ],
    },
    {
        "capability_id": "core_lesion_localization",
        "provider_id": "prism",
        "task": "lesion-roi",
        "model_id": "prism-dr-5fold",
        "model_version": "79637440a535e4f8118e939d3787121f82180125",
        "artifact_role": "legacy_cfp_comparator",
        "artifact_digest": None,
        "supported_modalities": ["CFP"],
        "trained_domain": "CFP_DOMAIN",
        "input_representation": "Phase3 provider input; CFP only",
        "taxonomy_or_class_order": ["MA", "HE", "EX", "SE"],
        "preprocessing_version": "prism-cfp-v1",
        "postprocessing_version": "review-policy-v1",
        "explanation_types": ["LESION_PROPOSALS"],
        "required_runtime_profile": "legacy-cfp-model-api",
        "runtime_status": "NOT_LOADED",
        "domain_status": "NOT_VALIDATED_FOR_UWF",
        "clinical_validation_status": "NOT_ESTABLISHED",
        "rights_status": "ACADEMIC_USE_REVIEW_REQUIRED",
        "release_status": "COMPARATOR_ONLY",
        "enabled": False,
        "status": "NOT_LOADED",
        "warnings": [
            "CFP comparator; not validated for UWF.",
            "Empty proposals do not mean that no lesions exist.",
        ],
    },
    {
        "capability_id": "dr_grade",
        "provider_id": "uspec",
        "task": "global",
        "model_id": "uspec-uwf-grading",
        "model_version": "grading_state.pt-candidate",
        "artifact_role": "trained_inference_checkpoint",
        "artifact_digest": "8f07eb11859f638faee368a56c7c532ca946fee320f92f030a0cf25c63b769ac",
        "supported_modalities": ["UWF"],
        "trained_domain": "UWF_RESEARCH_CANDIDATE",
        "input_representation": "Phase2 selected UWF analysis representation",
        "taxonomy_or_class_order": [0, 1, 2, 3, 4],
        "preprocessing_version": "UNVERIFIED",
        "postprocessing_version": "UNVERIFIED",
        "explanation_types": ["ATTENTION_GRID"],
        "required_runtime_profile": "phase3-qualified-model-api",
        "runtime_status": "BLOCKED_ARTIFACT",
        "domain_status": "UWF_RESEARCH_CANDIDATE",
        "clinical_validation_status": "NOT_ESTABLISHED",
        "rights_status": "UNVERIFIED",
        "release_status": "DISABLED",
        "enabled": False,
        "status": "BLOCKED_ARTIFACT",
        "warnings": [
            "Observed checkpoint bytes and safe runtime load are not available in this environment.",
            "No clinical or production claim is made.",
        ],
    },
    {
        "capability_id": "core_lesion_localization",
        "provider_id": "none",
        "task": "lesion-roi",
        "model_id": "native-uwf-lesion-localizer",
        "model_version": "none-qualified",
        "artifact_role": "none",
        "artifact_digest": None,
        "supported_modalities": ["UWF"],
        "trained_domain": "UWF_NATIVE_TARGET",
        "input_representation": "not available",
        "taxonomy_or_class_order": ["MA", "HE", "EX", "SE"],
        "preprocessing_version": "not available",
        "postprocessing_version": "not available",
        "explanation_types": [],
        "required_runtime_profile": "none",
        "runtime_status": "NOT_PRESENT",
        "domain_status": "DEFERRED_NO_QUALIFIED_CANDIDATE",
        "clinical_validation_status": "NOT_ESTABLISHED",
        "rights_status": "UNVERIFIED",
        "release_status": "DEFERRED",
        "enabled": False,
        "status": "DEFERRED_NO_QUALIFIED_CANDIDATE",
        "warnings": ["No qualified native UWF lesion localizer is present."],
    },
    {
        "capability_id": "longitudinal_change",
        "provider_id": "none",
        "task": "longitudinal",
        "model_id": "longitudinal-disabled",
        "model_version": "none-qualified",
        "artifact_role": "none",
        "artifact_digest": None,
        "supported_modalities": ["CFP", "UWF"],
        "trained_domain": "NOT_ESTABLISHED",
        "input_representation": "manual comparison only",
        "taxonomy_or_class_order": [],
        "preprocessing_version": "not available",
        "postprocessing_version": "not available",
        "explanation_types": [],
        "required_runtime_profile": "none",
        "runtime_status": "DISABLED",
        "domain_status": "NOT_ESTABLISHED",
        "clinical_validation_status": "NOT_ESTABLISHED",
        "rights_status": "UNVERIFIED",
        "release_status": "DISABLED",
        "enabled": False,
        "status": "DISABLED",
        "warnings": ["Learned longitudinal change remains disabled."],
    },
    {
        "capability_id": "decision_comparator",
        "provider_id": "clef",
        "task": "comparator",
        "model_id": "clef-comparator",
        "model_version": "not-evaluated",
        "artifact_role": "research_comparator",
        "artifact_digest": None,
        "supported_modalities": ["CFP", "UWF"],
        "trained_domain": "GENERAL_MULTIMODAL",
        "input_representation": "research-only",
        "taxonomy_or_class_order": [],
        "preprocessing_version": "not-evaluated",
        "postprocessing_version": "not-evaluated",
        "explanation_types": [],
        "required_runtime_profile": "research-only",
        "runtime_status": "NOT_RUN",
        "domain_status": "NOT_VALIDATED_FOR_UWF",
        "clinical_validation_status": "NOT_ESTABLISHED",
        "rights_status": "RESEARCH_REVIEW_REQUIRED",
        "release_status": "COMPARATOR_ONLY",
        "enabled": False,
        "status": "NOT_RUN",
        "warnings": ["Comparator output is not exposed in clinician workflow."],
    },
)


def registry_entries() -> tuple[dict[str, Any], ...]:
    """Return immutable-by-convention copies for tests and audit surfaces."""

    return tuple(deepcopy(entry) for entry in _REGISTRY)


def _fallback_entry(item: dict[str, Any]) -> dict[str, Any]:
    task = str(item.get("task") or "unknown")
    return {
        "capability_id": "dr_grade" if task == "global" else "core_lesion_localization",
        "provider_id": str(item.get("model_id") or "unknown"),
        "task": task,
        "model_id": str(item.get("model_id") or "unknown"),
        "model_version": str(item.get("revision") or item.get("model_version") or "unknown"),
        "artifact_role": "runtime-advertised",
        "artifact_digest": None,
        "supported_modalities": list(item.get("modalities") or []),
        "trained_domain": "UNKNOWN",
        "input_representation": "runtime-advertised",
        "taxonomy_or_class_order": list(item.get("class_order") or []),
        "preprocessing_version": str(item.get("preprocessing") or "UNKNOWN"),
        "postprocessing_version": "UNKNOWN",
        "explanation_types": [],
        "required_runtime_profile": str(item.get("runtime") or "UNKNOWN"),
        "runtime_status": str(item.get("status") or "UNKNOWN"),
        "domain_status": "UNKNOWN",
        "clinical_validation_status": "NOT_ESTABLISHED",
        "rights_status": "UNKNOWN",
        "release_status": "RESEARCH_ONLY",
        "enabled": False,
        "status": str(item.get("status") or "UNKNOWN"),
        "warnings": list(item.get("warnings") or []),
    }


def capability_descriptors(
    runtime_items: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    *,
    include_registry: bool = True,
) -> list[dict[str, Any]]:
    """Merge live provider metadata with committed registry metadata.

    Registry-only entries remain visible as explicit unavailable/deferred
    capabilities.  A runtime descriptor can refine status and latency, but it
    cannot promote domain, rights, or release status by implication.
    """

    registry = {entry["model_id"]: entry for entry in _REGISTRY}
    descriptors: dict[str, dict[str, Any]] = {}
    for item in runtime_items:
        model_id = str(item.get("model_id") or "unknown")
        merged = deepcopy(registry.get(model_id, _fallback_entry(item)))
        for key, value in item.items():
            if key in {"release_status", "domain_status", "clinical_validation_status", "rights_status"}:
                continue
            if value is not None:
                merged[key] = value
        merged["model_version"] = str(item.get("revision") or item.get("model_version") or merged["model_version"])
        merged["runtime_status"] = str(item.get("status") or merged["runtime_status"])
        merged["status"] = str(item.get("status") or merged["status"])
        merged["warnings"] = list(dict.fromkeys([*merged.get("warnings", []), *(item.get("warnings") or [])]))
        descriptors[model_id] = merged
    if include_registry:
        for entry in _REGISTRY:
            descriptors.setdefault(entry["model_id"], deepcopy(entry))
    return sorted(descriptors.values(), key=lambda item: (item["capability_id"], item["model_id"]))


def descriptor_for(model_id: str) -> dict[str, Any]:
    """Return the committed identity for a model, or a safe unknown record."""

    for entry in _REGISTRY:
        if entry["model_id"] == model_id:
            return deepcopy(entry)
    return _fallback_entry({"model_id": model_id})
