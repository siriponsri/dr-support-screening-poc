"""Additive API contract for patient and eye confirmation."""

from typing import Literal

from pydantic import Field

from ._schema import Contract


Laterality = Literal["LEFT", "RIGHT", "UNKNOWN"]


class ResolverReview(Contract):
    revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=80)
    patient_action: Literal["KEEP", "CONFIRM", "SET", "LEAVE_UNLINKED"] = "KEEP"
    patient_key: str | None = Field(default=None, max_length=32)
    laterality_action: Literal["KEEP", "SET"] = "KEEP"
    laterality: Laterality | None = None
    note: str = Field(default="", max_length=1000)
