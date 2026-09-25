"""Shared PostgreSQL foundation for M1 persistence implementations."""

from .config import DatabaseConfigurationError, PostgresSettings
from .database import DatabaseUnavailableError, PostgresDatabase
from .migrations import LATEST_SCHEMA_VERSION, MigrationError, MigrationResult, SchemaMigrator
from .schema import CASE_ID_COLUMN, CASES_TABLE, INITIAL_REVISION, REVISION_COLUMN
from .schema import WORKSPACE_ID_COLUMN, WORKSPACES_TABLE

__all__ = [
    "CASES_TABLE",
    "CASE_ID_COLUMN",
    "DatabaseConfigurationError",
    "DatabaseUnavailableError",
    "INITIAL_REVISION",
    "LATEST_SCHEMA_VERSION",
    "MigrationError",
    "MigrationResult",
    "PostgresDatabase",
    "PostgresSettings",
    "REVISION_COLUMN",
    "SchemaMigrator",
    "WORKSPACES_TABLE",
    "WORKSPACE_ID_COLUMN",
]
