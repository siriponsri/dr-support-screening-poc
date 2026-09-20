"""Contracts for the local S2 workspace manager."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ._schema import Contract


_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def is_absolute_local_path(value: str) -> bool:
    """Return whether *value* is an absolute filesystem path, not a URI.

    The review workstation accepts paths for the host on which the FastAPI
    process is running. Windows-shaped paths are recognized for contract
    validation on non-Windows test hosts, but they are not opened there.
    """
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    candidate = value.strip()
    lowered = candidate.lower()
    if "://" in candidate or lowered.startswith(("file:", "http:", "https:", "s3:", "gs:")):
        return False
    if os.name == "nt":
        return Path(candidate).is_absolute()
    return Path(candidate).is_absolute() or bool(_WINDOWS_DRIVE_PATH.match(candidate))


def _clean_local_path(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Path must be a string")
    cleaned = value.strip()
    if not is_absolute_local_path(cleaned):
        raise ValueError("Path must be an absolute local path")
    return cleaned


class WorkspaceProfile(Contract):
    """Durable local identity for one review workspace."""

    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    input_folder: str
    output_folder: str
    database_path: str
    note: str | None = Field(default=None, max_length=500)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    last_opened: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Workspace name must be a string")
        return value.strip()

    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Workspace note must be a string")
        cleaned = value.strip()
        return cleaned or None

    @field_validator("input_folder", "output_folder", "database_path", mode="before")
    @classmethod
    def clean_paths(cls, value: str) -> str:
        return _clean_local_path(value)

    @field_validator("created_at", "updated_at", "last_opened")
    @classmethod
    def validate_timestamp(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Timestamp must be an RFC 3339 value") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError("Timestamp must include a UTC offset")
        return value


class WorkspaceInput(Contract):
    """The common body for workspace creation and profile edits."""

    name: str = Field(min_length=1, max_length=120)
    input_folder: str
    output_folder: str
    database_path: str
    note: str | None = Field(default=None, max_length=500)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Workspace name must be a string")
        return value.strip()

    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Workspace note must be a string")
        cleaned = value.strip()
        return cleaned or None

    @field_validator("input_folder", "output_folder", "database_path", mode="before")
    @classmethod
    def clean_paths(cls, value: str) -> str:
        return _clean_local_path(value)


class FolderPickerRequest(Contract):
    purpose: Literal["input", "output"]
    initial_path: str | None = None

    @field_validator("initial_path", mode="before")
    @classmethod
    def validate_initial_path(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return _clean_local_path(value)


class DatabasePickerRequest(Contract):
    mode: Literal["open", "create"]
    initial_path: str | None = None
    suggested_name: str = Field(default="review.sqlite", min_length=1, max_length=120)

    @field_validator("initial_path", mode="before")
    @classmethod
    def validate_initial_path(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return _clean_local_path(value)

    @field_validator("suggested_name", mode="before")
    @classmethod
    def clean_suggested_name(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Suggested database name must be a string")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Suggested database name must not be empty")
        return cleaned


class PickerResult(Contract):
    status: Literal["selected", "cancelled", "unavailable"]
    path: str | None = None
    code: str | None = None
    message: str | None = None

    @model_validator(mode="after")
    def valid_selection(self):
        if self.status == "selected":
            if self.path is None or not is_absolute_local_path(self.path):
                raise ValueError("Selected picker result must contain an absolute local path")
        elif self.path is not None:
            raise ValueError("Cancelled or unavailable picker results cannot contain a path")
        return self
