"""Metadata-only binding to the immutable admitted source; no file reads or inference."""
import re

SHA256 = re.compile(r"^[a-f0-9]{64}$")


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
