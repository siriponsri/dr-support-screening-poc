"""Versioned Phase 3 model context and result contracts.

Bridge v1 remains deliberately frozen.  These contracts carry the additional
identity and transform context needed by qualified Phase 3 providers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ._schema import Contract, GlobalResult, LesionResult


SourceOrigin = Literal["PUBLIC", "SYNTHETIC", "WORKSPACE", "UNKNOWN"]


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


class Phase3ResultEnvelope(Contract):
    schema_version: Literal["bridge.v2"] = "bridge.v2"
    invocation_id: str = Field(min_length=8, max_length=120)
    capability_id: str = Field(min_length=1, max_length=120)
    task: Literal["global", "lesion-roi", "longitudinal", "comparator"]
    model: Phase3ModelIdentity
    input: Phase3InputContext
    result: GlobalResult | LesionResult | None = None
    explanation: Phase3Explanation
    runtime: Phase3Runtime | None = None
    warnings: list[str] = Field(default_factory=list)
    status: Literal["APPLIED", "UNSUPPORTED", "BLOCKED", "STALE_RESULT", "DUPLICATE"]


class Phase3PredictRequest(Contract):
    """A public/synthetic-only versioned Model API request.

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
