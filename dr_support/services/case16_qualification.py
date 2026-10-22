"""Exact-case16 qualification attestation, separate from recorded provenance.

No environment/HTTP registration. This is not a clinical admission, model-use
license, signature service, process supervisor or inference authorization API.
"""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
import re
from pathlib import Path
from threading import RLock

from .prism_remote_transport import TransportError, canonical, require_sha256

SOURCE_SHA256 = "07bc59b885de06bdd0260c771aabde195c26125e824269a691eb566a61a5cd19"
OWNER_REFERENCE = "Sentinel_d7d1e493dbd88191a76fad54af3abf37"
EXPECTED_SIZE = (1920, 835)
PROFILE = "AUTHORIZED_DEMO_CASE16_Q05_FINAL_REQUEST"
RUN_REQUESTS = 1
BASELINE_REASON = "NO_CENTER_ENCLOSING_WHITE_RIM"
# Preserve the existing demo admission's origin. Authorization is NOT an origin.
RECORDED_ORIGIN = "PUBLIC"
CLINICAL_FIELDS = (
    "reviewed_grade",
    "grade_review_source",
    "grade_status",
    "grade_reviews",
    "grade_adjudication",
    "reviewed_grade_label",
    "clinician_review",
    "review_history",
    "human_annotations",
    "annotation_confirmation",
    "ai_annotation_reviews",
    "lesion_review_state",
    "annotation_completeness",
    "annotations",
    "admission",
    "admission_history",
)


@dataclass(frozen=True)
class Case16Authorization:
    owner_reference: str
    technical_only: bool = False

    def __post_init__(self):
        if type(self.technical_only) is not bool:
            raise TransportError("TYPED_CASE16_TECHNICAL_MODE_REQUIRED")
        if self.owner_reference != OWNER_REFERENCE:
            raise TransportError("EXACT_CASE16_OWNER_REFERENCE_REQUIRED")

    @property
    def max_requests(self):
        return RUN_REQUESTS

    @property
    def image_id(self):
        return SOURCE_SHA256  # Existing demo's content-addressed case ID.

    @property
    def origin(self):
        return RECORDED_ORIGIN

    @property
    def attestation(self):
        value = {
            "profile": PROFILE,
            "owner_reference": OWNER_REFERENCE,
            "case_alias": "case16",
            "source_sha256": SOURCE_SHA256,
            "recorded_origin_preserved": RECORDED_ORIGIN,
            "max_fresh_plans": self.max_requests,
            "max_executions": self.max_requests,
            "applied_mask_allowed": False,
            "worker_seconds_including_cleanup_max": 600,
            "whole_session_seconds_max": 1800,
            "gpu_index": 0,
            "vram_mib_max": 10240,
            "rss_bytes_max": 24 * 1024**3,
        }
        if self.technical_only:
            value.update(
                technical_only=True,
                admission_state_preserved=True,
                clinical_use=False,
                new_quality_confirmation=False,
                new_clinical_confirmation=False,
            )
        return value

    def eligible(self, admission):
        qualities = {"GRADABLE", "NOT_EVALUATED", "NEEDS_REVIEW"} if self.technical_only else {"GRADABLE"}
        modalities = {"FUNDUS_ACCEPTED", "NEEDS_REVIEW"} if self.technical_only else {"FUNDUS_ACCEPTED"}
        if (
            admission.get("source_origin") != self.origin
            or admission.get("retinal_modality") != "UWF"
            or admission.get("modality_admission") not in modalities
            or admission.get("quality_state") not in qualities
        ):
            raise TransportError(
                "CASE16_EXISTING_ELIGIBILITY_REQUIRED_NO_REVIEW_BYPASS"
            )

    def input(self, image, case, admission):
        self.eligible(admission)
        if (
            image.image_id != self.image_id
            or case.get("image_id") != self.image_id
            or admission.get("image_id") != self.image_id
            or image.source_type != self.origin
            or image.source_origin != self.origin
            or image.modality != "UWF"
            or image.size != EXPECTED_SIZE
            or any(
                value != SOURCE_SHA256
                for value in (
                    image.sha256,
                    case.get("source_sha256"),
                    case.get("image_sha256"),
                    admission.get("source_sha256"),
                )
            )
            or admission.get("integrity_status") != "OK"
            or (admission.get("integrity") or {}).get("status", "OK") != "OK"
            or (admission.get("integrity") or {}).get("changed_sources")
        ):
            raise TransportError("CASE16_RECORDED_SOURCE_OR_CASE_CHANGED")
        self.wire(image.data)

    def wire(self, data):
        if (
            not isinstance(data, bytes)
            or hashlib.sha256(data).hexdigest() != SOURCE_SHA256
        ):
            raise TransportError("CASE16_IMMUTABLE_ORIGINAL_WIRE_REQUIRED")

    def context(self, value):
        self.eligible(value["admission"])
        source = value["recorded_source_identity"]
        if (
            value["image_id"] != self.image_id
            or value["source_sha256"] != SOURCE_SHA256
            or source["source_origin"] != self.origin
            or source["integrity_status"] != "OK"
            or any(
                source.get(key) != SOURCE_SHA256
                for key in (
                    "case_source_sha256",
                    "admission_source_sha256",
                    "image_recorded_sha256",
                )
            )
            or source["case_revision"] != value["case_revision"]
            or source["admission_sha256"] != value["admission_sha256"]
        ):
            raise TransportError("CASE16_RECORDED_CONTEXT_CHANGED")
        require_sha256(value["admission_sha256"])

    def candidate(self, candidate):
        if (
            candidate.get("status") != "UNCERTAIN"
            or candidate.get("reason_code") != BASELINE_REASON
            or candidate.get("mask_png") is not None
            or candidate.get("mask_version") is not None
        ):
            raise TransportError("CASE16_NO_APPLIED_MASK_SCOPE_ONLY")

    def binding(self, value):
        self.context(value)
        if (
            value.get("modality") != "UWF"
            or value.get("model_id") != "prism-dr-5fold"
            or value.get("wire_sha256") != SOURCE_SHA256
            or value.get("external_fov_status") != "UNCERTAIN"
            or value.get("external_fov_reason_code") != BASELINE_REASON
            or any(
                value.get(key) is not None
                for key in ("mask_sha256", "mask_png_sha256", "mask_version")
            )
        ):
            raise TransportError("CASE16_NO_APPLIED_MASK_SCOPE_ONLY")

    def worker_policy(self, policy, *, whole_session_seconds):
        # Existing owned controller is stricter (300s) and remains unchanged.
        if (
            type(whole_session_seconds) not in (int, float)
            or not 0 < whole_session_seconds <= 1800
            or policy.model_id != "prism-dr-5fold"
            or policy.max_jobs > self.max_requests
            or policy.max_seconds + policy.drain_seconds > 600
            or policy.max_vram_mib > 10240
            or policy.max_rss_bytes > 24 * 1024**3
        ):
            raise TransportError("CASE16_APPROVED_BUDGET_EXCEEDED")


def checked_authorization(value):
    if value is not None and type(value) is not Case16Authorization:
        # Explicit offline batch opt-in only; no environment/HTTP mode flag and
        # no duck typing. Absent batch package retains ordinary case16 policy.
        try:
            from prism_batch_scope import is_batch_authorization
        except ImportError:
            raise TransportError("TYPED_EXACT_CASE16_ATTESTATION_REQUIRED") from None
        if not is_batch_authorization(value):
            raise TransportError("TYPED_EXACT_CASE16_ATTESTATION_REQUIRED")
    return value


class QualificationMemoryStore:
    """Only a copied case, no injectable production store/DB or human writer."""

    def __init__(self, case, *, evidence, authorization=None):
        self.lock = RLock()
        self._case, self._original = deepcopy(case), deepcopy(case)
        self._evidence, self._writes = Path(evidence), 0
        self._authorization = checked_authorization(authorization) or Case16Authorization(OWNER_REFERENCE)

    def get(self, key):
        if key != SOURCE_SHA256:
            raise TransportError("EXACT_CASE16_ONLY")
        with self.lock:
            return deepcopy(self._case)

    def put(self, case):
        with self.lock:
            if case.get("image_id") != SOURCE_SHA256 or any(
                case.get(key) != self._original.get(key) for key in CLINICAL_FIELDS
            ):
                raise TransportError("CASE16_CLINICAL_MUTATION_OR_OUTPUT_CAP_REJECTED")
            previous, current = (
                self._case.get("inference_history", []),
                case.get("inference_history", []),
            )
            if current == previous:
                self._case = deepcopy(
                    case
                )  # Existing initial hydration, no new AI evidence.
                return
            if (
                self._writes >= self._authorization.max_requests
                or len(current) != len(previous) + 1
                or current[:-1] != previous
            ):
                raise TransportError("CASE16_IMMUTABLE_HISTORY_OR_OUTPUT_CAP_REJECTED")
            self._writes += 1
            # Only model evidence is persisted. No patient/context/review copy.
            payload = {
                "attestation": self._authorization.attestation,
                "output_number": self._writes,
                "new_inference_evidence": current[-1],
            }
            self._evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
            with (self._evidence / f"output-{self._writes}.json").open("xb") as output:
                output.write(canonical(payload))
                output.flush()
                os.fsync(output.fileno())
            self._case = deepcopy(case)

    def all_cases(self):
        return [self.get(SOURCE_SHA256)]


def authorized_case16_session(
    directory,
    *,
    authorization,
    image,
    case,
    admission,
    provider,
    authenticated_status_reader,
):
    """Explicit disabled-profile assembly; validates actual bytes BEFORE files."""
    if checked_authorization(authorization) is None:
        raise TransportError("EXACT_CASE16_ATTESTATION_REQUIRED")
    authorization.input(image, case, admission)
    root = Path(directory)
    if (
        re.fullmatch(r"case16-owned-qualification-q[0-9]{2}", root.name) is None
        or root.exists()
        or root.is_symlink()
    ):
        raise TransportError("FRESH_CASE16_QUALIFICATION_DIRECTORY_REQUIRED")
    root.mkdir(mode=0o700)  # Never adopt/overwrite a previous run.
    from .prism_fixed_session import FixedQASession

    storage = QualificationMemoryStore(case, evidence=root / "testdata", authorization=authorization)
    session = FixedQASession(
        root / "journal",
        store=storage,
        images={image.image_id: image},
        admissions={image.image_id: deepcopy(admission)},
        provider=provider,
        authenticated_status_reader=authenticated_status_reader,
        demo_authorization=authorization,
    )
    try:
        with (root / "AUTHORIZATION.json").open("x", encoding="utf-8") as output:
            json.dump(authorization.attestation, output, sort_keys=True)
    except BaseException as error:
        close_failed_session(session, error)
        raise
    return session


def close_failed_session(session, error):
    """Preserve construction failure and explicit cleanup proof independently."""
    try:
        session.close()
    except BaseException:
        blocked = TransportError('LOCAL_SESSION_CLEANUP_UNCONFIRMED', 503)
        blocked.cleanup_unconfirmed = True
        raise blocked from None
    error.local_session_cleanup_confirmed = True
