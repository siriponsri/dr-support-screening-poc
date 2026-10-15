"""Explicit source-origin and private authorization policy.

The hospital lane is deliberately opt-in and narrowly bound to one configured
private root. It never changes an unknown/workspace upload into a hospital
record, and it never grants dataset export authorization.
"""

from __future__ import annotations

import os
import hashlib
import hmac
from pathlib import Path

PUBLIC_ORIGINS = frozenset({"PUBLIC", "SYNTHETIC"})
HOSPITAL_ORIGIN = "HOSPITAL_AUTHORIZED"
WORKSPACE_ORIGINS = frozenset({"WORKSPACE", "UNKNOWN"})
KNOWN_ORIGINS = PUBLIC_ORIGINS | WORKSPACE_ORIGINS | {HOSPITAL_ORIGIN}
PRIVATE_PROJECT_SCOPE = "PRIVATE_PROJECT_EVALUATION"
HOSPITAL_MODALITIES = frozenset({"CFP", "UWF"})
HOSPITAL_LINKAGE_KEY_ENV = "DR_SUPPORT_HOSPITAL_LINKAGE_KEY"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip() == "1"


def authorized_hospital_root() -> Path | None:
    value = os.environ.get("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOT", "").strip()
    if not value:
        return None
    candidate = Path(value)
    return candidate.resolve() if candidate.is_absolute() else None


def hospital_ingest_enabled(folder: str | Path) -> bool:
    """Return true only for the exact owner-configured private root.

    The directory must not be group/world accessible and a source modality
    must be explicitly configured. This is a local access guard, not a
    substitute for an institutional data-steward approval.
    """

    root = authorized_hospital_root()
    if (
        root is None
        or not _truthy("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL")
        or authorized_hospital_modality() is None
    ):
        return False
    try:
        if Path(folder).resolve() != root or not root.is_dir():
            return False
        return (root.stat().st_mode & 0o077) == 0
    except OSError:
        return False


def authorized_hospital_modality() -> str | None:
    """Return an explicitly configured source modality, never a path guess."""

    modality = os.environ.get("DR_SUPPORT_AUTHORIZED_HOSPITAL_MODALITY", "").strip().upper()
    return modality if modality in HOSPITAL_MODALITIES else None


def hospital_model_access_enabled(*, model_api: bool = False) -> bool:
    """Require an explicit private-evaluation opt-in at each model boundary."""

    scope_name = "MODEL_HOSPITAL_SCOPE" if model_api else "DR_SUPPORT_HOSPITAL_SCOPE"
    if os.environ.get(scope_name, "").strip() != PRIVATE_PROJECT_SCOPE:
        return False
    if model_api:
        return (
            _truthy("MODEL_ALLOW_AUTHORIZED_HOSPITAL")
            and bool(os.environ.get("REMOTE_MODEL_TOKEN", "").strip())
        )
    return _truthy("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL")


def source_allowed_for_model(origin: str, *, model_api: bool = False) -> bool:
    return origin in PUBLIC_ORIGINS or (
        origin == HOSPITAL_ORIGIN and hospital_model_access_enabled(model_api=model_api)
    )


def source_origin_is_known(origin: object) -> bool:
    return origin in KNOWN_ORIGINS


def hospital_linkage_key() -> bytes | None:
    """Return the private key used to make hospital identity references opaque.

    The key is intentionally supplied by the private runtime and is never
    committed or derived from a patient identifier.  Without it, the
    authorized admission path remains usable but does not infer longitudinal
    linkage.
    """
    value = os.environ.get(HOSPITAL_LINKAGE_KEY_ENV, "").strip()
    if len(value) < 32:
        return None
    return value.encode("utf-8")


def opaque_hospital_patient_key(patient_candidate: str) -> str | None:
    """Map a trusted private patient token to a stable opaque external ID."""
    key = hospital_linkage_key()
    if key is None or not patient_candidate:
        return None
    digest = hmac.new(key, patient_candidate.strip().upper().encode("utf-8"), hashlib.sha256).hexdigest()
    return f"HOSPITAL-{digest[:24].upper()}"
