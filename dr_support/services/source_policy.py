"""Explicit source-origin and private authorization policy.

The hospital lane is deliberately opt-in and narrowly bound to one configured
private root. It never changes an unknown/workspace upload into a hospital
record. Admission alone grants nothing: dataset export authorization is the
single rule in ``EXPORT_AUTHORIZATION`` below, used by every export path.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path

from .filesystem_privacy import has_reparse_component, private_hospital_root

PUBLIC_ORIGINS = frozenset({"PUBLIC", "SYNTHETIC"})
HOSPITAL_ORIGIN = "HOSPITAL_AUTHORIZED"
WORKSPACE_ORIGINS = frozenset({"WORKSPACE", "UNKNOWN"})
KNOWN_ORIGINS = PUBLIC_ORIGINS | WORKSPACE_ORIGINS | {HOSPITAL_ORIGIN}
PRIVATE_PROJECT_SCOPE = "PRIVATE_PROJECT_EVALUATION"
HOSPITAL_MODALITIES = frozenset({"CFP", "UWF"})
HOSPITAL_LINKAGE_KEY_ENV = "DR_SUPPORT_HOSPITAL_LINKAGE_KEY"
HOSPITAL_ROOTS_ENV = "DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS"
HOSPITAL_WINDOWS_READERS_ENV = "DR_SUPPORT_HOSPITAL_WINDOWS_READ_ONLY_SIDS"

# One export rule for every dataset path (owner decision, 2026-10-24): consented
# HOSPITAL_AUTHORIZED images and labels may be copied to a local folder the user
# chose. The app never sends them to a cloud service; WORKSPACE and UNKNOWN
# origins stay blocked. AI predictions and physician-confirmed labels stay in
# separate manifest fields.
EXPORT_AUTHORIZATION = {
    "PUBLIC": "ALLOWED_ENGINEERING_PUBLIC",
    "SYNTHETIC": "ALLOWED_ENGINEERING_SYNTHETIC",
    "WORKSPACE": "BLOCKED_WORKSPACE_NOT_AUTHORIZED",
    HOSPITAL_ORIGIN: "ALLOWED_LOCAL_AUTHORIZED_HOSPITAL",
    "UNKNOWN": "BLOCKED_UNKNOWN_ORIGIN",
}
LOCAL_ONLY_EXPORTS = frozenset({"ALLOWED_LOCAL_AUTHORIZED_HOSPITAL"})
_CLOUD_SYNC_FOLDERS = frozenset({"dropbox", "google drive", "googledrive", "my drive", "icloud drive",
                                 "iclouddrive", "box", "box sync"})
_CLOUD_SYNC_ENV = ("OneDrive", "OneDriveCommercial", "OneDriveConsumer")


def export_authorization(source_origin: str) -> str:
    """Return the export decision for a source origin (unknown values are blocked)."""
    return EXPORT_AUTHORIZATION.get(source_origin, "BLOCKED_UNKNOWN_ORIGIN")


def local_export_destination_reason(folder: str | Path) -> str | None:
    """Why a folder is not a local-only export destination, or None when it is.

    Network shares and folders a cloud client synchronizes would send hospital
    records off this computer without an explicit user action.
    """
    text = str(folder)
    if text.startswith(("\\\\", "//")):
        return "NETWORK_SHARE"
    resolved = Path(folder).resolve(strict=False)
    for name in _CLOUD_SYNC_ENV:
        root = os.environ.get(name)
        if root and resolved.is_relative_to(Path(root).resolve(strict=False)):
            return "CLOUD_SYNC_FOLDER"
    for part in resolved.parts:
        folded = part.casefold()
        if folded in _CLOUD_SYNC_FOLDERS or folded.startswith("onedrive"):
            return "CLOUD_SYNC_FOLDER"
    return None


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip() == "1"


def _resolved_private_root(value: object) -> Path | None:
    """Resolve one configured root without accepting a symlink as the root."""
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value.strip())
    if not candidate.is_absolute():
        return None
    try:
        if has_reparse_component(candidate):
            return None
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_dir() else None


def authorized_hospital_root() -> Path | None:
    """Return the legacy single authorized root, if configured."""
    value = os.environ.get("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOT", "").strip()
    return _resolved_private_root(value)


def _configured_hospital_roots() -> tuple[tuple[Path, str], ...] | None:
    """Parse the explicit multi-root hospital binding, failing closed on error.

    The value is a server-only JSON object such as
    ``{"UWF":"/private/uwf","CFP":"/private/cfp"}``.  Modality is
    configuration, never inferred from a filename or directory name.
    """
    raw = os.environ.get(HOSPITAL_ROOTS_ENV, "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    if not isinstance(payload, dict) or set(payload) != HOSPITAL_MODALITIES:
        return ()
    roots: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for modality in ("UWF", "CFP"):
        root = _resolved_private_root(payload.get(modality))
        if root is None or root in seen:
            return ()
        seen.add(root)
        roots.append((root, modality))
    return tuple(roots)


def hospital_roots_configured() -> bool:
    """Return whether the operator supplied the multi-root binding.

    This distinguishes an absent configuration (where legacy workspace
    behavior may remain available) from a malformed or unavailable explicit
    hospital binding, which must fail closed rather than fall through to a
    workspace directory. The legacy single-root setting is included so a
    missing modality cannot silently downgrade the same directory to a
    workspace source.
    """
    return bool(
        os.environ.get(HOSPITAL_ROOTS_ENV, "").strip()
        or os.environ.get("DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOT", "").strip()
    )


def authorized_hospital_roots() -> tuple[tuple[Path, str], ...]:
    """Return the active explicit hospital root/modality bindings.

    A configured multi-root value takes precedence over the legacy single-root
    value. Invalid multi-root configuration returns an empty tuple, so a typo
    cannot silently broaden admission to a workspace folder.
    """
    configured = _configured_hospital_roots()
    if configured is not None:
        return configured
    root = authorized_hospital_root()
    modality = authorized_hospital_modality()
    return ((root, modality),) if root is not None and modality is not None else ()


def _windows_read_only_sids(root: Path) -> tuple[str, ...] | None:
    """Bind an explicitly approved Windows managed reader SID to an exact root.

    The private operator config maps canonical hospital roots to one verified
    machine/domain group SID each. Names and client-supplied claims are never
    authority. Missing config keeps the strict default; malformed config denies.
    This does not modify ACLs and is ignored on POSIX hosts.
    """
    if os.name != "nt":
        return ()
    raw = os.environ.get(HOSPITAL_WINDOWS_READERS_ENV, "").strip()
    if not raw:
        return ()
    if os.environ.get("DR_SUPPORT_HOSPITAL_SCOPE", "").strip() != PRIVATE_PROJECT_SCOPE:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or not payload:
        return None
    authorized = {path for path, _ in authorized_hospital_roots()}
    bindings: dict[Path, tuple[str, ...]] = {}
    for value, sids in payload.items():
        bound = _resolved_private_root(value)
        if bound is None or bound not in authorized or bound in bindings:
            return None
        # Exclude Everyone, Users, Authenticated Users and other well-known SIDs.
        # The verified managed SID is supplied only by private operator config.
        if (
            not isinstance(sids, list) or len(sids) != 1
            or not isinstance(sids[0], str)
            or re.fullmatch(r"S-1-5-21-(?:[0-9]+-){3}[0-9]+", sids[0]) is None
        ):
            return None
        bindings[bound] = tuple(sids)
    return bindings.get(root, ())


def hospital_ingest_enabled(folder: str | Path) -> bool:
    """Return true only for an exact private root with an explicit modality."""
    if not _truthy("DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL"):
        return False
    candidate = Path(folder)
    for root, modality in authorized_hospital_roots():
        if modality is None:
            continue
        try:
            readers = _windows_read_only_sids(root)
            if readers is None:
                return False
            if (
                not has_reparse_component(candidate)
                and candidate.resolve() == root
                and private_hospital_root(root, read_only_sids=readers)
            ):
                return True
        except OSError:
            return False
    return False


def authorized_hospital_modality(folder: str | Path | None = None) -> str | None:
    """Return the explicitly configured modality for a root, never a path guess."""
    if folder is not None:
        try:
            candidate = Path(folder).resolve()
        except OSError:
            return None
        for root, modality in authorized_hospital_roots():
            if candidate == root:
                return modality
        return None
    # Preserve the legacy API for callers that do not have a root value.
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
