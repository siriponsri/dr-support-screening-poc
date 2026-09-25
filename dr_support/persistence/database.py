"""Small connection, session, and transaction boundary for PostgreSQL."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import Connection

from .config import PostgresSettings


class DatabaseUnavailableError(RuntimeError):
    """A configured PostgreSQL target could not be reached."""


class PostgresDatabase:
    """Own connection creation and explicit transaction lifetimes."""

    def __init__(
        self,
        settings: PostgresSettings,
        *,
        connector: Callable[..., Connection[Any]] = psycopg.connect,
    ) -> None:
        self.settings = settings
        self._connector = connector

    def connect(self, *, autocommit: bool = True) -> Connection[Any]:
        """Open a connection or raise a credential-safe availability error."""

        try:
            return self._connector(
                self.settings.dsn,
                autocommit=autocommit,
                connect_timeout=self.settings.connect_timeout_seconds,
                application_name=self.settings.application_name,
            )
        except psycopg.Error as exc:
            raise DatabaseUnavailableError(
                f"PostgreSQL is configured but unavailable ({self.settings.safe_target})"
            ) from exc

    @contextmanager
    def session(self, *, autocommit: bool = True) -> Iterator[Connection[Any]]:
        """Yield one connection and always close it after use."""

        connection = self.connect(autocommit=autocommit)
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[Connection[Any]]:
        """Commit a successful unit of work and roll back any exception."""

        with self.session(autocommit=True) as connection:
            with connection.transaction():
                yield connection

    def verify_available(self) -> None:
        """Fail clearly when an explicitly configured target cannot serve queries."""

        try:
            with self.session() as connection:
                connection.execute("SELECT 1").fetchone()
        except DatabaseUnavailableError:
            raise
        except psycopg.Error as exc:
            raise DatabaseUnavailableError(
                f"PostgreSQL is configured but unavailable ({self.settings.safe_target})"
            ) from exc
