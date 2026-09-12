"""Shared odometer read helpers (used by dashboard + vehicle-detail routes)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OdometerRecord


async def latest_odometer_km_and_date(
    db: AsyncSession, vin: str
) -> tuple[Decimal | None, date | None]:
    """Return the single most-recent odometer reading (km) and its date for a vin.

    Deterministic on SQLite (prod) AND PostgreSQL (CI): the odometer model has an
    integer PK and no VIN/date uniqueness (app/models/odometer.py), so multiple
    readings can share a date. Ordering by ``date DESC, id DESC`` (not date alone)
    resolves a same-date tie to the SAME row on both dialects. Fetched ONCE per
    call; callers reuse the returned km for both the displayed reading and the
    mileage-reminder evaluation, so those can never disagree. Returns
    ``(None, None)`` when the vehicle has no odometer reading.
    """
    row = (
        await db.execute(
            select(OdometerRecord.odometer_km, OdometerRecord.date)
            .where(OdometerRecord.vin == vin)
            .order_by(OdometerRecord.date.desc(), OdometerRecord.id.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None, None
    return row[0], row[1]


async def nearest_odometer(db: AsyncSession, vin: str, on: date) -> OdometerRecord | None:
    """The odometer record closest to `on` by day distance, or None.

    Two indexed queries, the latest on-or-before and the earliest after, then
    the smaller distance. A tie goes to the earlier one: an installation at
    date D happened at or after the last reading before D. Same-day
    duplicates resolve to the newest row, the rule
    `latest_odometer_km_and_date` documents, so repeated calls pick the same
    record on both dialects.
    """
    before = (
        await db.execute(
            select(OdometerRecord)
            .where(OdometerRecord.vin == vin, OdometerRecord.date <= on)
            .order_by(OdometerRecord.date.desc(), OdometerRecord.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    after = (
        await db.execute(
            select(OdometerRecord)
            .where(OdometerRecord.vin == vin, OdometerRecord.date > on)
            .order_by(OdometerRecord.date.asc(), OdometerRecord.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if before is None:
        return after
    if after is None:
        return before
    return before if (on - before.date) <= (after.date - on) else after
