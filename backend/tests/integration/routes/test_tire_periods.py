"""Mount periods: the odometer records they publish, the contradictions the
writers refuse, and the editor (Task 6 adds that class).

Every tire operation that takes an odometer publishes it as a vehicle
odometer record so the distance calculation can see it. Before this file
mount, dismount, retire AND every tread reading published with one marker,
`[AUTO-SYNC from tire #<tire_id>]`, so nothing could later say which event a
record came from. Now each period event has its own marker, which is what
lets the editor move the right record and only that one.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.models.odometer import OdometerRecord
from app.models.tire import TireMountPeriod
from app.models.vehicle import Vehicle
from app.services.tire_service import (
    ODOMETER_SOURCE_TIRE,
    ODOMETER_SOURCE_TIRE_DISMOUNT,
    ODOMETER_SOURCE_TIRE_MOUNT,
)
from app.utils.odometer_sync import auto_sync_marker


@pytest.fixture
async def vehicle(db_session, test_user):
    vin = f"TIREPER{uuid.uuid4().hex[:10].upper()}"[:17]
    db_session.add(
        Vehicle(
            vin=vin,
            user_id=test_user["id"],
            nickname="Periods",
            vehicle_type="Car",
            year=2020,
            make="Honda",
            model="Fit",
        )
    )
    await db_session.commit()
    yield vin
    await db_session.execute(delete(OdometerRecord).where(OdometerRecord.vin == vin))
    await db_session.execute(delete(Vehicle).where(Vehicle.vin == vin))
    await db_session.commit()


async def _records(db_session, vin: str) -> list[OdometerRecord]:
    db_session.expire_all()
    return list(
        (
            await db_session.execute(
                select(OdometerRecord)
                .where(OdometerRecord.vin == vin)
                .order_by(OdometerRecord.date, OdometerRecord.id)
            )
        )
        .scalars()
        .all()
    )


async def _periods(db_session, tire_id: int) -> list[TireMountPeriod]:
    db_session.expire_all()
    return list(
        (
            await db_session.execute(
                select(TireMountPeriod)
                .where(TireMountPeriod.tire_id == tire_id)
                .order_by(TireMountPeriod.id)
            )
        )
        .scalars()
        .all()
    )


@pytest.mark.asyncio
class TestOdometerMarkers:
    async def test_mount_and_dismount_publish_period_owned_records(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        base = f"/api/vehicles/{vehicle}/tires"
        made = await client.post(
            f"{base}/create-and-mount",
            headers=auth_headers,
            json={
                "vin": vehicle,
                "position": "FL",
                "brand": "M",
                "mounted_on": "2026-01-10",
                "mounted_odometer_km": "10000",
            },
        )
        assert made.status_code == 201, made.text
        tire_id = made.json()["id"]
        (period,) = await _periods(db_session, tire_id)
        # Captured immediately: `_records` below calls `expire_all()`, and
        # reading an expired attribute off an async-session object outside an
        # `await` raises MissingGreenlet. The id itself is what every
        # assertion below needs, not the live ORM handle.
        period_id = period.id
        (rec,) = await _records(db_session, vehicle)
        assert rec.date == date(2026, 1, 10) and rec.odometer_km == Decimal("10000")
        assert rec.notes == auto_sync_marker(ODOMETER_SOURCE_TIRE_MOUNT, period_id)
        assert rec.source == ODOMETER_SOURCE_TIRE_MOUNT

        off = await client.post(
            f"{base}/{tire_id}/dismount",
            headers=auth_headers,
            json={"dismounted_on": "2026-03-10", "dismounted_odometer_km": "12000"},
        )
        assert off.status_code == 200, off.text
        recs = await _records(db_session, vehicle)
        assert [r.notes for r in recs] == [
            auto_sync_marker(ODOMETER_SOURCE_TIRE_MOUNT, period_id),
            auto_sync_marker(ODOMETER_SOURCE_TIRE_DISMOUNT, period_id),
        ]

    async def test_a_reading_keeps_the_tire_level_marker(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        base = f"/api/vehicles/{vehicle}/tires"
        made = await client.post(
            f"{base}/create-and-mount",
            headers=auth_headers,
            json={"vin": vehicle, "position": "FR", "brand": "R"},
        )
        assert made.status_code == 201, made.text
        tire_id = made.json()["id"]
        read = await client.post(
            f"{base}/{tire_id}/readings",
            headers=auth_headers,
            json={"recorded_at": "2026-02-01", "tread_depth_mm": "7.0", "odometer_km": "11000"},
        )
        assert read.status_code == 201, read.text
        (rec,) = [r for r in await _records(db_session, vehicle) if r.date == date(2026, 2, 1)]
        assert rec.notes == auto_sync_marker(ODOMETER_SOURCE_TIRE, tire_id)

    async def test_delete_removes_the_periods_records_too(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        base = f"/api/vehicles/{vehicle}/tires"
        made = await client.post(
            f"{base}/create-and-mount",
            headers=auth_headers,
            json={
                "vin": vehicle,
                "position": "RL",
                "brand": "D",
                "mounted_on": "2026-01-10",
                "mounted_odometer_km": "10000",
            },
        )
        tire_id = made.json()["id"]
        await client.post(
            f"{base}/{tire_id}/dismount",
            headers=auth_headers,
            json={"dismounted_on": "2026-03-10", "dismounted_odometer_km": "12000"},
        )
        assert len(await _records(db_session, vehicle)) == 2
        gone = await client.delete(f"{base}/{tire_id}", headers=auth_headers)
        assert gone.status_code == 204, gone.text
        assert await _records(db_session, vehicle) == []
