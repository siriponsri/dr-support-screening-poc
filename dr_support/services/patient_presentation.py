"""Durable workspace-local presentation labels; never patient identity keys."""

from __future__ import annotations

import re


DISPLAY_INDICES = "_patient_display_indices"


def hospital_patient_label(store, case: dict, *, source_origin: str) -> tuple[dict, str | None]:
    """Allocate a unique stable label using additive private case JSON only.

    Historical assignments remain in their case documents to prevent reuse after
    manual correction. The supported case store is single-runtime and locked.
    Clinical revisions, histories and identities are untouched.
    """
    key = case.get("patient_key")
    if source_origin != "HOSPITAL_AUTHORIZED" or not key:
        return case, None
    with store.lock:
        case = store.get(case["image_id"])
        key = case.get("patient_key")
        if not key:
            return case, None
        assignments = {}
        used = set()
        for stored in store.all_cases():
            for patient_key, index in stored.get(DISPLAY_INDICES, {}).items():
                if not isinstance(index, int) or isinstance(index, bool) or index < 1:
                    raise ValueError("Invalid patient display allocation")
                if patient_key in assignments and assignments[patient_key] != index:
                    raise ValueError("Conflicting patient display allocation")
                if index in used and assignments.get(patient_key) != index:
                    raise ValueError("Duplicate patient display allocation")
                assignments[patient_key] = index
                used.add(index)
        index = assignments.get(key, max(used, default=0) + 1)
        if case.get(DISPLAY_INDICES, {}).get(key) != index:
            case = {**case, DISPLAY_INDICES: {**case.get(DISPLAY_INDICES, {}), key: index}}
            store.put(case)
        return case, f"Patient {index}"


def preserves_trusted_hospital_key(case: dict, admission: dict, requested: str | None) -> bool:
    """Only the exact unchanged authoritative hospital key bypasses manual syntax."""
    key = admission.get("trusted_patient_key")
    return bool(
        admission.get("source_origin") == "HOSPITAL_AUTHORIZED"
        and admission.get("trusted_identity_method") == "AUTHORIZED_FILENAME_SEMANTICS"
        and isinstance(key, str)
        and re.fullmatch(r"HOSPITAL-[A-F0-9]{24}", key)
        and admission.get("trusted_laterality") in {"LEFT", "RIGHT"}
        and isinstance(admission.get("trusted_capture_sequence"), int)
        and not isinstance(admission.get("trusted_capture_sequence"), bool)
        and admission["trusted_capture_sequence"] >= 1
        and case.get("patient_resolution_method") == "AUTHORIZED_SOURCE"
        and requested == case.get("patient_key") == key
    )
