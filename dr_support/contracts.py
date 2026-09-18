"""Additive Bridge v1 contracts; independent of frozen scientific protocols."""
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

LABELS = {'MA': 'MICROANEURYSM', 'HE': 'HEMORRHAGE', 'EX': 'HARD_EXUDATE', 'SE': 'SOFT_EXUDATE'}


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class InferenceRequest(Contract):
    image_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    modality: Literal['CFP', 'UWF'] = 'CFP'
    model_id: str


class Provenance(Contract):
    image_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_type: Literal['PUBLIC', 'SYNTHETIC']
    preprocessing: str
    checkpoint_sha256: dict[str, str] = Field(default_factory=dict)
    source_revision: str


class GlobalResult(Contract):
    schema_version: Literal['bridge.v1'] = 'bridge.v1'
    model_id: str
    model_version: str
    modality: Literal['CFP', 'UWF']
    state: Literal['AI_SUGGESTION', 'UNCERTAIN', 'UNGRADABLE', 'UNSUPPORTED']
    grade: int | None = Field(default=None, ge=0, le=4, strict=True)
    probabilities: list[float] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode='after')
    def valid_prediction(self):
        if self.grade is not None:
            p = self.probabilities
            if len(p) != 5 or any(x < 0 or x > 1 for x in p) or not math.isclose(sum(p), 1, abs_tol=1e-5):
                raise ValueError('Five normalized class probabilities required')
            if self.grade != max(range(5), key=p.__getitem__):
                raise ValueError('Grade must match highest class probability')
            if self.confidence is None or not math.isclose(self.confidence, max(p), abs_tol=1e-5):
                raise ValueError('Confidence must match predicted class')
        elif self.probabilities or self.confidence is not None:
            raise ValueError('Non-grading states cannot contain grading scores')
        if self.state in ('UNGRADABLE', 'UNSUPPORTED') and self.grade is not None:
            raise ValueError('Unsupported/ungradable is not a grade')
        return self


class Lesion(Contract):
    source_label: Literal['MA', 'HE', 'EX', 'SE']
    canonical_label: str
    rectangle: tuple[float, float, float, float]
    score: float = Field(ge=0, le=1)
    state: Literal['AI_SUGGESTION'] = 'AI_SUGGESTION'

    @model_validator(mode='after')
    def valid_box(self):
        x1, y1, x2, y2 = self.rectangle
        if self.canonical_label != LABELS[self.source_label] or not (0 <= x1 < x2 and 0 <= y1 < y2):
            raise ValueError('Invalid canonical label or XYXY rectangle')
        return self


class LesionResult(Contract):
    schema_version: Literal['bridge.v1'] = 'bridge.v1'
    model_id: str
    model_version: str
    modality: Literal['CFP', 'UWF']
    state: Literal['AI_SUGGESTION', 'UNSUPPORTED'] = 'AI_SUGGESTION'
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    lesions: list[Lesion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode='after')
    def in_bounds(self):
        if any(x.rectangle[2] > self.width or x.rectangle[3] > self.height for x in self.lesions):
            raise ValueError('Rectangle outside original image')
        if self.state == 'UNSUPPORTED' and self.lesions:
            raise ValueError('Unsupported modality cannot contain suggestions')
        return self
