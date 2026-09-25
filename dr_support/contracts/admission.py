"""Additive contracts for conservative image admission and review."""

from typing import Literal

from pydantic import Field

from ._schema import Contract
from ..imaging.contracts import IntegrityStatus, SourceDimensions, SourceMetadata
from ..imaging.contracts import SourceIntegrity


ModalityAdmission = Literal[
    "FUNDUS_ACCEPTED",
    "NEEDS_REVIEW",
    "REJECTED_NON_FUNDUS",
    "REJECTED_INVALID",
]
QualityState = Literal["GRADABLE", "UNGRADABLE", "NEEDS_REVIEW", "NOT_EVALUATED"]
RetinalModality = Literal["CFP", "UWF", "UNKNOWN"]
AdmissionMethod = Literal["AUTOMATIC", "MANUAL", "LEGACY_COMPAT", "DATASET_IMPORT"]
AdmissionReviewAction = Literal[
    "ACCEPT_RETINAL",
    "MARK_NON_FUNDUS",
    "QUALITY_ACCEPTABLE",
    "QUALITY_INADEQUATE",
    "LEAVE_UNRESOLVED",
]


class AdmissionMetadata(Contract):
    """The current auditable admission decision for one discovered file."""

    image_id: str = Field(min_length=1, max_length=160)
    source_reference: str = Field(min_length=1, max_length=1000)
    filename: str = Field(min_length=1, max_length=260)
    file_extension: str = Field(min_length=1, max_length=16)
    file_size_bytes: int = Field(ge=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    channels_or_mode: str | None = Field(default=None, max_length=40)
    modality_admission: ModalityAdmission
    quality_state: QualityState
    # Source type is independent of the fundus admission/quality decisions.
    # Missing fields on existing workspace records migrate to UNKNOWN.
    retinal_modality: RetinalModality = "UNKNOWN"
    retinal_modality_state: Literal["RESOLVED", "NEEDS_CONFIRMATION"] = "NEEDS_CONFIRMATION"
    retinal_modality_method: Literal["NONE", "MANUAL", "LEGACY_COMPAT", "DICOM_METADATA"] = "NONE"
    retinal_modality_candidate: RetinalModality | None = None
    admission_method: AdmissionMethod
    admission_reason_code: str = Field(min_length=1, max_length=80)
    quality_reason_code: str | None = Field(default=None, max_length=80)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    reviewed_by: str | None = Field(default=None, max_length=80)
    reviewed_at: str | None = Field(default=None)
    review_note: str | None = Field(default=None, max_length=1000)
    # S5A identity facts are additive; legacy admission records omit them.
    source_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    source_format: str | None = Field(default=None, min_length=1, max_length=40)
    source_media_type: str | None = Field(default=None, min_length=1, max_length=120)
    source_dimensions: SourceDimensions | None = None
    source_metadata: SourceMetadata | None = None
    integrity_status: IntegrityStatus = IntegrityStatus.OK
    integrity: SourceIntegrity = Field(default_factory=SourceIntegrity)


class AdmissionReview(Contract):
    """Clinician actions that change modality or quality state."""

    revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=80)
    action: AdmissionReviewAction
    note: str = Field(default="", max_length=1000)
