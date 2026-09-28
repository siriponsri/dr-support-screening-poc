"""Shared PostgreSQL foundation for M1 persistence implementations."""

from .cases import (
    CaseConflictError,
    CaseImportConflictError,
    CaseImportError,
    CaseImportResult,
    PostgresCaseStore,
    PostgresStore,
)
from .config import (
    CASE_STORE_MODE_ENV,
    DATABASE_URL_ENV,
    DEFAULT_CASE_STORE_MODE,
    WORKSPACE_ID_ENV,
    DatabaseConfigurationError,
    PostgresSettings,
)
from .database import DatabaseUnavailableError, PostgresDatabase
from .migrations import LATEST_SCHEMA_VERSION, MigrationError, MigrationResult, SchemaMigrator
from .workspaces import MANAGED_STORAGE_LABEL, PostgresWorkspaceCatalog
from .schema import (
    ARCHIVED_AT_COLUMN,
    CASE_ID_COLUMN,
    CASES_TABLE,
    INITIAL_REVISION,
    REVISION_COLUMN,
    WORKSPACE_ID_COLUMN,
    WORKSPACES_TABLE,
)

__all__ = [
    "CASES_TABLE",
    "CASE_ID_COLUMN",
    "ARCHIVED_AT_COLUMN",
    "CaseConflictError",
    "CaseImportConflictError",
    "CaseImportError",
    "CaseImportResult",
    "CASE_STORE_MODE_ENV",
    "DATABASE_URL_ENV",
    "DatabaseConfigurationError",
    "DatabaseUnavailableError",
    "DEFAULT_CASE_STORE_MODE",
    "INITIAL_REVISION",
    "LATEST_SCHEMA_VERSION",
    "MigrationError",
    "MigrationResult",
    "MANAGED_STORAGE_LABEL",
    "PostgresDatabase",
    "PostgresCaseStore",
    "PostgresSettings",
    "PostgresWorkspaceCatalog",
    "PostgresStore",
    "REVISION_COLUMN",
    "SchemaMigrator",
    "WORKSPACES_TABLE",
    "WORKSPACE_ID_COLUMN",
    "WORKSPACE_ID_ENV",
]
