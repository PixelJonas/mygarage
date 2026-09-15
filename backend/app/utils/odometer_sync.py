"""Utility for auto-syncing odometer records from service and fuel records.

Metric-canonical since v2.26.2: `odometer_km` (Decimal kilometers).

Since v2.27.0 the helper supports a `commit` flag so callers (e.g. the
extended fuel-tracking flow) can compose this into a single outer
transaction with other side effects.
"""

from collections.abc import Iterable, Sequence
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OdometerRecord
from app.utils.odometer_tolerance import odometer_below


def auto_sync_marker(source_type: str, source_id: int) -> str:
    """The note that marks an odometer row as owned by one source record.

    Written here and matched by the cleanup paths that remove a synced row when
    its source is deleted. Those paths used to hardcode the format string, so
    the writer and the matcher were one edit apart from silently disagreeing --
    and a mismatch does not fail loudly, it just orphans the row.
    """
    return f"[AUTO-SYNC from {source_type} #{source_id}]"


async def same_day_records(db: AsyncSession, vin: str, date: date_type) -> Sequence[OdometerRecord]:
    """Every odometer record of `vin` on `date`, newest first.

    By SQL, so a caller on a session that does not autoflush must flush a
    pending move or delete before asking.
    """
    result = await db.execute(
        select(OdometerRecord)
        .where(OdometerRecord.vin == vin)
        .where(OdometerRecord.date == date)
        .order_by(OdometerRecord.id.desc())
    )
    return result.scalars().all()


def reads_at_or_above(records: Iterable[OdometerRecord], odometer_km: Decimal) -> bool:
    """Whether any of `records` reads at or above `odometer_km`.

    Within the same-reading tolerance (`app.utils.odometer_tolerance`): a record
    a few parts per million below counts as the same figure, so only records
    below by more than the tolerance leave the figure higher than the day's.
    """
    return any(not odometer_below(record.odometer_km, odometer_km) for record in records)


async def sync_odometer_from_record(
    db: AsyncSession,
    vin: str,
    date: date_type,
    odometer_km: Decimal | None,
    source_type: str,
    source_id: int,
    *,
    commit: bool = True,
    claim_other_records: bool = True,
) -> OdometerRecord | None:
    """Create or update an odometer record from a service/fuel record.

    Behavior:
        - Skips sync if odometer_km is None
        - Checks for existing odometer record on same (vin, date)
        - If exists and was auto-synced or from livelink: updates odometer_km
          (user-entered fuel/service data is more authoritative than LiveLink)
        - If exists and was manual: does not overwrite
        - If not exists: creates new odometer record with source marker

    With `claim_other_records=False` the source never touches a record it did
    not create. A record on that date carrying this source's own marker has
    its value updated. Otherwise, when any other record on that date (manual,
    LiveLink, or another source's automatic one) reads at or above the figure
    (`reads_at_or_above`), nothing is written: the day already has a reading
    at least as high. Otherwise, with no record on the date or only lower
    ones, a record with this source's marker is created; being the day's
    highest reading, it is the vehicle's current reading for that day (the
    highest reading on the latest date).
    The tire paths publish this way: a tire event's record is later moved or
    deleted by marker, so a record it had re-marked would take another
    source's reading with it.

    Args:
        commit: When True (default) the helper commits and refreshes within
            its own unit of work. When False the caller is responsible for
            committing — the helper still flushes so the row gets an id and
            any FK side effects are visible to subsequent queries inside the
            same transaction.
        claim_other_records: When True (default) the one-reading-per-day
            policy above applies, and an automatic or LiveLink record on the
            date becomes this source's. When False, see above.
    """
    if odometer_km is None:
        return None

    # idx_odometer_vin_date is NOT unique, and multiple readings on one date are
    # legitimate (a manual entry plus a device reading, start/end of a trip day).
    # scalar_one_or_none() therefore raised MultipleResultsFound and surfaced as
    # a 500 on any fuel/service record sharing that date. Newest first, ordered
    # deterministically so repeated syncs pick the same target.
    same_day = await same_day_records(db, vin, date)

    marker = auto_sync_marker(source_type, source_id)

    # Migration 055 added odometer_records.fuel_record_id with ON DELETE
    # CASCADE for fuel-sourced rows. Set it when source is 'fuel' so the
    # database can clean orphans when a fuel record is deleted; for
    # service/livelink the FK stays NULL (no fuel parent to cascade from).
    fk_value = source_id if source_type == "fuel" else None

    if claim_other_records:
        existing = same_day[0] if same_day else None
        if existing is not None:
            is_auto_synced = existing.notes and "[AUTO-SYNC from" in existing.notes
            is_livelink = existing.source == "livelink"
            if not (is_auto_synced or is_livelink):
                return None
    else:
        # Found by marker, not by being the day's newest: a record added
        # beside this source's own does not stop its figure being corrected.
        existing = next((row for row in same_day if row.notes == marker), None)
        if existing is None and reads_at_or_above(same_day, odometer_km):
            return None

    if existing is not None:
        existing.odometer_km = odometer_km
        existing.notes = marker
        existing.source = source_type
        existing.fuel_record_id = fk_value
        if commit:
            await db.commit()
            await db.refresh(existing)
        else:
            await db.flush()
        return existing

    odometer_record = OdometerRecord(
        vin=vin,
        date=date,
        odometer_km=odometer_km,
        notes=marker,
        source=source_type,
        fuel_record_id=fk_value,
    )
    db.add(odometer_record)
    if commit:
        await db.commit()
        await db.refresh(odometer_record)
    else:
        await db.flush()
    return odometer_record
