"""Versioned Phase 3 model context and result contracts.

Bridge v1 remains deliberately frozen.  These contracts carry the additional
identity and transform context needed by qualified Phase 3 providers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ._schema import Contract, GlobalResult, LesionResult


SourceOrigin = Literal["PUBLIC", "SYNTHETIC", "WORKSPACE", "HOSPITAL_AUTHORIZED", "UNKNOWN"]


class Phase3ModelIdentity(Contract):
    id: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=160)
    artifact_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    trained_domain: str
    supported_modalities: list[str] = Field(default_factory=list)
    release_status: str


class Phase3InputContext(Contract):
    image_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_origin: SourceOrigin
    input_modality: Literal["CFP", "UWF"]
    analysis_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    representation_version: str = Field(min_length=1, max_length=160)
    transform_id: str = Field(min_length=1, max_length=160)
    mask_version: str | None = Field(default=None, max_length=160)
    request_case_revision: int = Field(ge=0)


class Phase3Runtime(Contract):
    runtime_id: str = Field(min_length=1, max_length=160)
    device: str = Field(min_length=1, max_length=160)
    latency_ms: float | None = Field(default=None, ge=0)


class Phase3Explanation(Contract):
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    kind: str | None = Field(default=None, max_length=120)
    version: str | None = Field(default=None, max_length=120)
    invocation_id: str
    model_id: str
    source_sha256: str
    analysis_sha256: str
    warning: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_state(self):
        if self.status == "AVAILABLE" and (not self.kind or not self.version):
            raise ValueError("Available explanation evidence requires kind and version")
        if self.status == "UNAVAILABLE" and self.payload:
            raise ValueError("Unavailable explanation evidence cannot contain payload")
        return self


class PrismAnalysisFieldEvidence(Contract):
    status: Literal["READY"]
    mask_version: str = Field(min_length=1, max_length=120)
    mask_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_rgb_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    boundary_confidence: float = Field(ge=0, le=1)
    excluded_fraction: float = Field(ge=0, le=1)
    boundary: list[tuple[int, int]] = Field(min_length=3, max_length=20000)
    used_for_model_input: bool
    field_mask_png_base64: str | None = Field(default=None, max_length=20_000_000)

    @model_validator(mode="after")
    def mask_matches_processing(self):
        if self.used_for_model_input and not self.field_mask_png_base64:
            raise ValueError("Prepared PRISM input requires the exact FOV mask bytes")
        if not self.used_for_model_input and self.field_mask_png_base64 is not None:
            raise ValueError("Unapplied FOV evidence must not be presented as model input")
        return self


class PrismProcessingEvidence(Contract):
    input_image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    processing_mode: Literal["LEGACY", "PREPARED", "FALLBACK"]
    native_roi_status: Literal["SUCCEEDED", "FAILED"]
    native_roi_bbox: tuple[int, int, int, int] | None = None
    native_roi_failure_code: str | None = Field(default=None, max_length=120)
    external_fov_status: Literal["READY", "UNCERTAIN", "UNAVAILABLE", "NOT_APPLICABLE"]
    external_fov_reason_code: str | None = Field(default=None, max_length=120)
    fov_used_for_model_input: bool
    raw_boundary_classes: list[
        Literal[
            "INSIDE_ANALYSIS_FIELD", "NEAR_CAMERA_RIM",
            "OUTSIDE_ANALYSIS_FIELD", "INVALID_BOX",
        ] | None
    ] = Field(default_factory=list)
    analysis_field: PrismAnalysisFieldEvidence | None = None

    @model_validator(mode="after")
    def consistent_processing_state(self):
        if self.processing_mode == "PREPARED":
            if self.external_fov_status != "READY" or not self.fov_used_for_model_input:
                raise ValueError("PREPARED requires trusted FOV evidence used for model input")
            if self.analysis_field is None or not self.analysis_field.used_for_model_input:
                raise ValueError("PREPARED requires the exact applied analysis-field mask")
        elif self.fov_used_for_model_input:
            raise ValueError("Only PREPARED may apply the external FOV mask")
        if self.native_roi_status == "SUCCEEDED" and self.native_roi_bbox is None:
            raise ValueError("Successful native ROI requires its bounding box")
        if self.native_roi_status == "FAILED" and self.native_roi_bbox is not None:
            raise ValueError("Failed native ROI cannot advertise a bounding box")
        if self.external_fov_status != "READY" and self.analysis_field is not None:
            raise ValueError("Untrusted FOV evidence must not fabricate analysis-field geometry")
        return self


class Phase3ResultEnvelope(Contract):
    schema_version: Literal["bridge.v2", "bridge.v2.1"] = "bridge.v2"
    invocation_id: str = Field(min_length=8, max_length=120)
    capability_id: str = Field(min_length=1, max_length=120)
    task: Literal["global", "lesion-roi", "longitudinal", "comparator"]
    model: Phase3ModelIdentity
    input: Phase3InputContext
    result: GlobalResult | LesionResult | None = None
    prism_processing: PrismProcessingEvidence | None = None
    explanation: Phase3Explanation
    runtime: Phase3Runtime | None = None
    warnings: list[str] = Field(default_factory=list)
    status: Literal["APPLIED", "UNSUPPORTED", "BLOCKED", "STALE_RESULT", "DUPLICATE"]

    @model_validator(mode="after")
    def prism_processing_matches_result(self):
        if (self.schema_version == "bridge.v2.1") != (self.prism_processing is not None):
            raise ValueError("Bridge v2.1 is reserved for typed PRISM processing evidence")
        if self.prism_processing is not None:
            if self.model.id != "prism-dr-5fold" or self.task != "lesion-roi":
                raise ValueError("PRISM processing evidence is only valid for PRISM lesion assistance")
            if self.prism_processing.input_image_sha256 != self.input.analysis_sha256:
                raise ValueError("PRISM processing evidence must be bound to the analyzed image bytes")
            if isinstance(self.result, LesionResult) and (
                len(self.prism_processing.raw_boundary_classes) != len(self.result.lesions)
            ):
                raise ValueError("PRISM boundary metadata must preserve one entry per raw lesion result")
        return self


class Phase3PredictRequest(Contract):
    """A provenance-bound versioned Model API request.

    ``image_sha256`` is the exact bytes transmitted to the Model API and must
    equal ``analysis_sha256``.  ``source_sha256`` identifies the immutable
    source image that produced those bytes.
    """

    invocation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,120}$")
    capability_id: str = Field(min_length=1, max_length=120)
    task: Literal["global", "lesion-roi"]
    model_id: str = Field(min_length=1, max_length=160)
    model_version: str = Field(min_length=1, max_length=160)
    image_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    modality: Literal["CFP", "UWF"]
    image_b64: str = Field(min_length=1, max_length=20_000_000)
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_origin: SourceOrigin
    analysis_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    representation_version: str = Field(min_length=1, max_length=160)
    transform_id: str = Field(min_length=1, max_length=160)
    mask_version: str | None = Field(default=None, max_length=160)
    request_case_revision: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @model_validator(mode="after")
    def bind_analysis_bytes(self):
        if self.image_sha256 != self.analysis_sha256:
            raise ValueError("image_sha256 must match analysis_sha256")
        return self


class Phase3ReviewInferenceRequest(Contract):
    """Versioned invocation context for the review workstation proxy."""

    invocation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,120}$")
    capability_id: str = Field(min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=160)
    model_version: str = Field(min_length=1, max_length=160)
    image_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    modality: Literal["CFP", "UWF"]
    request_case_revision: int = Field(ge=0)
