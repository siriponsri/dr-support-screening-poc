"""Provider-neutral configuration contracts for the review workstation."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator

from ._schema import Contract


class ModelConnectionInput(Contract):
    """A candidate remote Model API connection.

    The token is accepted only by backend request handling and is never part of
    the response contract or workspace persistence.
    """

    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2048)
    token: str | None = Field(default=None, max_length=4096)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Connection name must be a string")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Connection name must not be empty")
        return cleaned

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Model API URL must be a string")
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Model API URL must use http or https")
        if parsed.username or parsed.password:
            raise ValueError("Model API URL must not contain credentials")
        return cleaned


class ModelConnectionModel(Contract):
    """Safe readiness summary for one advertised model."""

    model_id: str
    ready: bool
    status: str | None = None


class ModelConnectionResponse(Contract):
    """Clinician-safe connection state; no token field is exposed."""

    name: str | None = None
    url: str | None = None
    token_configured: bool = False
    status: Literal["CONNECTED", "NOT_CONFIGURED", "UNAVAILABLE", "UNVERIFIED"]
    message: str
    models: list[ModelConnectionModel] = Field(default_factory=list)
