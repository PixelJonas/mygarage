"""Which driver errors mean "another change to this vehicle is in progress".

The lock's 503 tells the user to try again. That is right for lock contention
and wrong for anything else: a disk I/O error or a dropped PostgreSQL
connection will fail the same way on retry. The classifier reads the driver's
own code, not the SQLAlchemy wrapper's class, because the wrapper class
differs by driver: asyncpg reports a lock timeout as a plain `DBAPIError`.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError

from app.services.vehicle_lock import is_lock_contention


class _DriverError(Exception):
    """Mirrors what reaches `.orig`: asyncpg through SQLAlchemy sets both
    `sqlstate` and `pgcode`, psycopg2 sets `pgcode`, psycopg sets `sqlstate`."""

    def __init__(
        self, message: str, *, sqlstate: str | None = None, pgcode: str | None = None
    ) -> None:
        super().__init__(message)
        if sqlstate is not None:
            self.sqlstate = sqlstate
        if pgcode is not None:
            self.pgcode = pgcode


def _sqlite(message: str, code: int | None) -> sqlite3.OperationalError:
    error = sqlite3.OperationalError(message)
    if code is not None:
        error.sqlite_errorcode = code
    return error


@pytest.mark.parametrize(
    "orig",
    [
        pytest.param(_sqlite("database is locked", sqlite3.SQLITE_BUSY), id="sqlite-busy"),
        pytest.param(_sqlite("database is locked", 517), id="sqlite-busy-snapshot"),
        pytest.param(
            _sqlite("database table is locked", sqlite3.SQLITE_LOCKED), id="sqlite-locked"
        ),
        pytest.param(_sqlite("database is locked", None), id="sqlite-message-only"),
        pytest.param(
            _DriverError("lock timeout", sqlstate="55P03", pgcode="55P03"), id="asyncpg-55P03"
        ),
        pytest.param(_DriverError("deadlock detected", pgcode="40P01"), id="psycopg2-40P01"),
        pytest.param(_DriverError("deadlock detected", sqlstate="40P01"), id="psycopg-40P01"),
    ],
)
def test_contention_is_recognised(orig: Exception) -> None:
    assert is_lock_contention(DBAPIError("SELECT 1", {}, orig)) is True
    assert is_lock_contention(OperationalError("SELECT 1", {}, orig)) is True


@pytest.mark.parametrize(
    "orig",
    [
        pytest.param(_sqlite("disk I/O error", sqlite3.SQLITE_IOERR), id="sqlite-ioerr"),
        pytest.param(_sqlite("database disk image is malformed", 11), id="sqlite-corrupt"),
        pytest.param(_sqlite("no active connection", None), id="aiosqlite-closed"),
        pytest.param(
            _DriverError("connection failure", sqlstate="08006", pgcode="08006"),
            id="asyncpg-08006",
        ),
        pytest.param(_DriverError("canceling statement", pgcode="57014"), id="psycopg2-57014"),
        # A PostgreSQL code outranks the message: this is not contention even
        # though the text would match the SQLite fallback.
        pytest.param(_DriverError("database is locked", sqlstate="XX000"), id="pg-code-wins"),
        pytest.param(_DriverError("connection was closed"), id="no-code"),
    ],
)
def test_anything_else_is_not(orig: Exception) -> None:
    assert is_lock_contention(OperationalError("SELECT 1", {}, orig)) is False
