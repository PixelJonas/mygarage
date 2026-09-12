"""Serialise the writers that change where a vehicle's tires are.

The rule "one open mount period per corner per vehicle" cannot be a database
constraint: `tire_mount_periods` carries no `vin`. It is enforced by a
check-then-write in the service, and a check-then-write is only correct if
the two halves cannot interleave with another request's. This module is the
mechanism that stops them interleaving.

Why the VEHICLE row and not the tire row: two different tires being mounted
at FL would lock two different tire rows and never contend. The rule is per
vehicle, so the lock is on the shared parent.

Why not `with_for_update()` alone: SQLite has no `SELECT ... FOR UPDATE` and
SQLAlchemy compiles it away silently. Worse, the pysqlite driver runs every
statement before the first write in autocommit, so the occupant check and the
write were not serialised on SQLite at all. "SQLite's single writer serialises
anyway" is true of the WRITES and false of the check that precedes them.
Measured on 2026-09-12: two unlocked racers each saw zero rows and both wrote;
with `BEGIN IMMEDIATE` the second waited exactly the first's hold and then
read the first's row.

The contract, `LOCK_CONTRACT` below, is what the SQLite guard enforces and
what `test_tire_concurrency.py` spies on.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

LOCK_CONTRACT = (
    "lock_vehicle_for_write must be the first statement of a tire write: call it "
    "once, immediately after get_vehicle_or_403(require_write=True), and before "
    "any tire or period read"
)

LOCK_BUSY_DETAIL = "Another change to this vehicle is in progress. Try again."


async def lock_vehicle_for_write(db: AsyncSession, vin: str) -> None:
    """Take the vehicle's write lock for the rest of this transaction.

    SQLite: `BEGIN IMMEDIATE`, the database write lock, taken before any tire
    or period read so every read after it sees the last committed writer.
    Waits up to `busy_timeout`. If the driver connection is already inside a
    transaction the call is misplaced, and that is a programming error, not a
    runtime condition: it raises `RuntimeError` naming the contract rather
    than letting the driver's "cannot start a transaction within a
    transaction" surface as a 503.

    Anything else: `SELECT ... FOR UPDATE` on the vehicle row, which waits for
    a concurrent holder's commit.

    A lock that cannot be taken in time is a 503 with a sentence the user can
    act on. Before this helper the same condition was a generic 500.
    """
    dialect = db.get_bind().dialect.name
    try:
        if dialect == "sqlite":
            raw = await (await db.connection()).get_raw_connection()
            if raw.driver_connection.in_transaction:
                raise RuntimeError(LOCK_CONTRACT)
            await db.execute(text("BEGIN IMMEDIATE"))
        else:
            await db.execute(
                text("SELECT vin FROM vehicles WHERE vin = :vin FOR UPDATE"),
                {"vin": vin},
            )
    except OperationalError as exc:
        logger.warning("Vehicle write lock unavailable for %s: %s", vin, exc)
        raise HTTPException(status_code=503, detail=LOCK_BUSY_DETAIL) from exc
