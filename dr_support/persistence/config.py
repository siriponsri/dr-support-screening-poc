"""Server-side PostgreSQL configuration with secret-safe diagnostics."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from psycopg.conninfo import conninfo_to_dict
from psycopg.errors import ProgrammingError


DATABASE_URL_ENV = "DR_SUPPORT_DATABASE_URL"
DATABASE_SCHEMA_ENV = "DR_SUPPORT_DATABASE_SCHEMA"
DATABASE_CONNECT_TIMEOUT_ENV = "DR_SUPPORT_DATABASE_CONNECT_TIMEOUT"
DEFAULT_SCHEMA = "dr_support"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
_SCHEMA_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class DatabaseConfigurationError(RuntimeError):
    """PostgreSQL configuration is absent or invalid."""


@dataclass(frozen=True)
class PostgresSettings:
    """Validated settings whose representation never includes the database DSN."""

    dsn: str = field(repr=False)
    schema: str = DEFAULT_SCHEMA
    connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS
    application_name: str = "dr-support-workbench"

    def __post_init__(self) -> None:
        dsn = self.dsn.strip()
        if not dsn:
            raise DatabaseConfigurationError("PostgreSQL configuration is missing")
        try:
            parameters = conninfo_to_dict(dsn)
        except ProgrammingError as exc:
            raise DatabaseConfigurationError("PostgreSQL configuration is invalid") from exc
        if not parameters.get("dbname"):
            raise DatabaseConfigurationError("PostgreSQL configuration must name a database")
        if not _SCHEMA_PATTERN.fullmatch(self.schema):
            raise DatabaseConfigurationError(
                "PostgreSQL schema must use lowercase letters, digits, and underscores"
            )
        if not 1 <= self.connect_timeout_seconds <= 60:
            raise DatabaseConfigurationError(
                "PostgreSQL connect timeout must be between 1 and 60 seconds"
            )
        object.__setattr__(self, "dsn", dsn)

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        url_variable: str = DATABASE_URL_ENV,
    ) -> PostgresSettings:
        """Load an explicit PostgreSQL target; never select a SQLite fallback."""

        source = os.environ if environ is None else environ
        dsn = (source.get(url_variable) or "").strip()
        if not dsn:
            raise DatabaseConfigurationError(f"{url_variable} is required for PostgreSQL mode")
        schema = (source.get(DATABASE_SCHEMA_ENV) or DEFAULT_SCHEMA).strip()
        raw_timeout = (
            source.get(DATABASE_CONNECT_TIMEOUT_ENV)
            or str(DEFAULT_CONNECT_TIMEOUT_SECONDS)
        ).strip()
        try:
            timeout = int(raw_timeout)
        except ValueError as exc:
            raise DatabaseConfigurationError(
                f"{DATABASE_CONNECT_TIMEOUT_ENV} must be an integer"
            ) from exc
        return cls(dsn=dsn, schema=schema, connect_timeout_seconds=timeout)

    @property
    def safe_target(self) -> str:
        """Return a credential-free target for operator-facing failures."""

        parameters = conninfo_to_dict(self.dsn)
        host = parameters.get("host") or "local socket"
        port = parameters.get("port") or "default port"
        database = parameters.get("dbname") or "unknown database"
        return f"database {database!r} at {host}:{port}"
