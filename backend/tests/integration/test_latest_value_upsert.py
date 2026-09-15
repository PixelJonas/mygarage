"""SD-card backfill must never double-insert a latest telemetry value.

`_update_latest_if_newer` used to SELECT then `db.add` an ORM row without a
flush. Production sessions do not autoflush (`app/database.py`), so a second
row for a param with no existing latest row, in the same 500-row commit
batch, could not see the first row's `add` and added again, and the batch's
commit failed on the unique key `(vin, param_key)`. That left the file's
watermark unmoved, so the device's SD backfill retried the same file
forever.

These tests build their own `autoflush=False` sessionmaker over `test_engine`
(the pattern in `tests/integration/routes/test_tire_periods.py`), pinning
production's setting directly rather than depending on conftest's
`test_sessionmaker`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.livelink_device import LiveLinkDevice
from app.models.vehicle import Vehicle
from app.models.vehicle_telemetry import VehicleTelemetry, VehicleTelemetryLatest
from app.services.sd_log_parser import SdRow
from app.services.telemetry_service import TelemetryService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

T0 = datetime(2026, 9, 1, 12, 0, 0)


def _maker(test_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


async def _seed_vehicle(maker: async_sessionmaker[AsyncSession], suffix: str) -> tuple[str, str]:
    """A committed vehicle and a linked device; returns (vin, device_id)."""
    tag = uuid.uuid4().hex[:8].upper()
    vin = f"LATUP{suffix}{tag}"[:17]
    device_id = f"latupdev{suffix}{tag}"[:20]
    async with maker() as db:
        db.add(Vehicle(vin=vin, nickname=f"Latest upsert {suffix}", vehicle_type="Car"))
        await db.flush()
        db.add(LiveLinkDevice(device_id=device_id, vin=vin, enabled=True))
        await db.commit()
    return vin, device_id


async def _latest_row(maker: async_sessionmaker[AsyncSession], vin: str) -> VehicleTelemetryLatest:
    async with maker() as db:
        return (
            await db.execute(
                select(VehicleTelemetryLatest).where(VehicleTelemetryLatest.vin == vin)
            )
        ).scalar_one()


class TestRepeatedParamInOneBatch:
    async def test_a_param_seen_twice_in_one_batch_keeps_the_newer_value(
        self, test_engine, db_session
    ):
        maker = _maker(test_engine)
        vin, _device_id = await _seed_vehicle(maker, "A")

        async with maker() as db:
            service = TelemetryService(db)
            await service._update_latest_if_newer(vin, "SPEED", 50.0, T0)
            await service._update_latest_if_newer(vin, "SPEED", 60.0, T0 + timedelta(minutes=1))
            await db.commit()

        async with maker() as db:
            rows = (
                (
                    await db.execute(
                        select(VehicleTelemetryLatest).where(VehicleTelemetryLatest.vin == vin)
                    )
                )
                .scalars()
                .all()
            )
        assert len(rows) == 1, f"expected exactly one latest row, got {len(rows)}"
        assert rows[0].value == 60.0
        assert rows[0].timestamp == T0 + timedelta(minutes=1)


class TestOrderingGuards:
    async def test_an_older_row_never_replaces_a_newer_stored_value(self, test_engine, db_session):
        maker = _maker(test_engine)
        vin, _device_id = await _seed_vehicle(maker, "B")

        async with maker() as db:
            await TelemetryService(db)._update_latest_if_newer(vin, "SPEED", 99.0, T0)
            await db.commit()

        async with maker() as db:
            await TelemetryService(db)._update_latest_if_newer(
                vin, "SPEED", 10.0, T0 - timedelta(hours=1)
            )
            await db.commit()

        row = await _latest_row(maker, vin)
        assert row.value == 99.0
        assert row.timestamp == T0

    async def test_a_live_value_written_between_commits_survives_older_history(
        self, test_engine, db_session
    ):
        """Two independent sessions interleave commits around one row.

        Session A writes an old backfilled value and commits. Session B, a
        completely separate session/connection, then writes a newer live
        value through `_upsert_latest_value` and commits. Session A -- the
        SAME session and service object it used the first time, not a new
        one -- then writes a second backfilled value that is newer than its
        own first write but still older than session B's live write. The
        stored row must still hold session B's live value: the conditional
        upsert compares against the row in the database, never against
        whatever session A last saw in its own memory.
        """
        maker = _maker(test_engine)
        vin, _device_id = await _seed_vehicle(maker, "C")

        session_a = maker()
        service_a = TelemetryService(session_a)
        try:
            await service_a._update_latest_if_newer(vin, "SPEED", 10.0, T0 - timedelta(hours=1))
            await session_a.commit()

            async with maker() as session_b:
                await TelemetryService(session_b)._upsert_latest_value(vin, "SPEED", 99.0, T0, T0)
                await session_b.commit()

            await service_a._update_latest_if_newer(vin, "SPEED", 20.0, T0 - timedelta(minutes=30))
            await session_a.commit()
        finally:
            await session_a.close()

        row = await _latest_row(maker, vin)
        assert row.value == 99.0, "an older backfilled write clobbered the newer live value"
        assert row.timestamp == T0


class TestBulkBackfillWithARepeatedNewParam:
    async def test_bulk_backfill_imports_a_file_whose_new_param_repeats(
        self, test_engine, db_session
    ):
        maker = _maker(test_engine)
        vin, device_id = await _seed_vehicle(maker, "D")

        rows = [
            SdRow(param_key="SPEED", value=45.0, timestamp=T0),
            SdRow(param_key="SPEED", value=50.0, timestamp=T0 + timedelta(minutes=1)),
            SdRow(param_key="SPEED", value=55.0, timestamp=T0 + timedelta(minutes=2)),
        ]

        async with maker() as db:
            inserted = await TelemetryService(db).bulk_backfill(vin, device_id, rows)

        assert inserted == 3

        async with maker() as db:
            telemetry_rows = (
                (
                    await db.execute(
                        select(VehicleTelemetry).where(
                            VehicleTelemetry.vin == vin, VehicleTelemetry.param_key == "SPEED"
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(telemetry_rows) == 3

        row = await _latest_row(maker, vin)
        assert row.value == 55.0
        assert row.timestamp == T0 + timedelta(minutes=2)
