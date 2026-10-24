"""Metadata-only binding to the immutable admitted source; no file reads or inference."""
import re

SHA256 = re.compile(r"^[a-f0-9]{64}$")
RECORDED_KEYS = ("source_sha256", "image_sha256")
_SOUND_INTEGRITY = {"OK", "DUPLICATE_CONTENT"}


def admitted_source_hash(case, admission):
    """The admission-time hash a case may record, or None.

    Shared by case creation and the one-time projection (recorded source
    identity amendment). The value only ever comes from the admission record.
    """
    admission = admission or {}
    digest = admission.get("source_sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest) or digest != case.get("image_id"):
        return None
    integrity = admission.get("integrity") or {}
    if (admission.get("integrity_status") not in _SOUND_INTEGRITY
            or integrity.get("status", "OK") not in _SOUND_INTEGRITY or integrity.get("changed_sources")):
        return None
    metadata = admission.get("source_metadata") or {}
    if (metadata.get("source_sha256") not in {None, digest}
            or metadata.get("integrity_status") not in {None, *_SOUND_INTEGRITY}):
        return None
    return digest


def record_source_identity_on_creation(case, admission):
    """Write-once projection for a case being created; never repairs an existing case.

    Call before the first admission projection is stored on the case.
    """
    creating = case.get("revision") == 0 and case.get("admission") is None and not case.get("admission_history")
    if not creating or any(case.get(key) is not None for key in RECORDED_KEYS):
        return False
    digest = admitted_source_hash(case, admission)
    if digest is None:
        return False
    case.update(source_sha256=digest, image_sha256=digest)
    return True


def source_identity_reason(case, image, admission):
    if image is None:
        return "SOURCE_UNAVAILABLE"
    current = getattr(image, "sha256", None)
    admitted = (admission or {}).get("source_sha256")
    if not SHA256.fullmatch(str(current)) or not SHA256.fullmatch(str(admitted)):
        return "MISSING_SOURCE_IDENTITY"
    if current != admitted:
        return "SOURCE_HASH_MISMATCH"
    recorded = case.get("image_sha256") or case.get("source_sha256")
    if recorded is not None and recorded != current:
        return "SOURCE_HASH_MISMATCH"
    integrity = (admission or {}).get("integrity") or {}
    for status in [(admission or {}).get("integrity_status"), integrity.get("status")]:
        if status is not None and status not in {"OK", "DUPLICATE_CONTENT"}:
            return "SOURCE_INTEGRITY_FAILED"
    if integrity.get("changed_sources"):
        return "SOURCE_INTEGRITY_FAILED"
    return None
