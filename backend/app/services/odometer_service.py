"""Shared odometer read helpers (used by dashboard + vehicle-detail routes)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OdometerRecord


async def latest_odometer_km_and_date(
    db: AsyncSession, vin: str
) -> tuple[Decimal | None, date | None]:
    """Return the vehicle's current odometer reading (km) and its date for a vin.

    The current reading is the HIGHEST reading on the latest date. The odometer
    model has an integer PK and no VIN/date uniqueness (app/models/odometer.py),
    so several readings can share a date (a service visit and the tire mount it
    did, a fuel-up and a LiveLink reading), and an odometer does not run
    backwards within a day, so which source wrote its row first says nothing
    about which figure is current. Ordering by ``date DESC, odometer_km DESC,
    id DESC`` picks that reading, with the id making an exact tie resolve to
    the SAME row on SQLite (prod) AND PostgreSQL (CI). Fetched ONCE per
    call; callers reuse the returned km for both the displayed reading and the
    mileage-reminder evaluation, so those can never disagree. Returns
    ``(None, None)`` when the vehicle has no odometer reading.
    """
    row = (
        await db.execute(
            select(OdometerRecord.odometer_km, OdometerRecord.date)
            .where(OdometerRecord.vin == vin)
            .order_by(
                OdometerRecord.date.desc(),
                OdometerRecord.odometer_km.desc(),
                OdometerRecord.id.desc(),
            )
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
    date D happened at or after the last reading before D. Each side picks
    one reading of its day, and several readings of one day resolve to the
    highest, the rule `latest_odometer_km_and_date` documents (an odometer does
    not run backwards within a day), then to the newest row, so repeated calls
    pick the same record on both dialects.
    """
    before = (
        await db.execute(
            select(OdometerRecord)
            .where(OdometerRecord.vin == vin, OdometerRecord.date <= on)
            .order_by(
                OdometerRecord.date.desc(),
                OdometerRecord.odometer_km.desc(),
                OdometerRecord.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    after = (
        await db.execute(
            select(OdometerRecord)
            .where(OdometerRecord.vin == vin, OdometerRecord.date > on)
            .order_by(
                OdometerRecord.date.asc(),
                OdometerRecord.odometer_km.desc(),
                OdometerRecord.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if before is None:
        return after
    if after is None:
        return before
    return before if (on - before.date) <= (after.date - on) else after
