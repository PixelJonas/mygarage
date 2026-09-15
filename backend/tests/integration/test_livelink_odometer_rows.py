"""LiveLink's odometer rows on a day that already holds other readings.

A day can hold several odometer rows: a service visit and the tire mount it
did, a LiveLink row and a tread reading above it. The ingest looked up "the"
row of the day and raised MultipleResultsFound on every odometer-bearing
message that day, rolling back the whole message, and on a day whose only row
belonged to another source it never recorded the device's higher reading.

LiveLink owns only rows whose source is `livelink`: it updates the day's own
row, or creates one beside whatever else the day holds, and never modifies a
row of another source. Both live ingest paths (MQTT and the HTTPS payload
route) reach the odometer record through `TelemetryService.store_telemetry`,
so these tests drive that method.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.models.livelink_device import LiveLinkDevice
from app.models.odometer import OdometerRecord
from app.models.vehicle import Vehicle
from app.services.telemetry_service import TelemetryService
from app.utils.odometer_sync import auto_sync_marker

DAY = date(2026, 6, 21)
NOON = datetime(2026, 6, 21, 12, 0)
LATER = datetime(2026, 6, 21, 17, 30)

Row = tuple[date, Decimal, str | None, str | None]


@pytest_asyncio.fixture
async def linked(db_session, test_user):
    """A vehicle with a LiveLink device linked to it: `(vin, device_id)`."""
    suffix = uuid.uuid4().hex[:10].upper()
    vin = f"LLROWS{suffix}X"[:17]
    device_id = f"llrows{suffix.lower()}"
    db_session.add(
        Vehicle(
            vin=vin,
            user_id=test_user["id"],
            nickname="LiveLink rows",
            vehicle_type="Car",
            year=2019,
            make="Kia",
            model="Niro",
        )
    )
    await db_session.flush()
    db_session.add(LiveLinkDevice(device_id=device_id, vin=vin, enabled=True))
    await db_session.commit()
    yield vin, device_id
    await db_session.execute(delete(LiveLinkDevice).where(LiveLinkDevice.device_id == device_id))
    await db_session.execute(delete(Vehicle).where(Vehicle.vin == vin))
    await db_session.commit()


async def _ingest(db_session, vin: str, device_id: str, km: float, when: datetime) -> None:
    await TelemetryService(db_session).store_telemetry(
        vin=vin,
        device_id=device_id,
        autopid_data={"A6-ODOMETER": km},
        config={},
        timestamp=when,
    )
    await db_session.commit()


async def _rows(db_session, vin: str) -> list[Row]:
    db_session.expire_all()
    records = (
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
    return [(r.date, r.odometer_km, r.notes, r.source) for r in records]


def _livelink(km: str, verb: str) -> Row:
    return (DAY, Decimal(km), f"Auto-{verb} from LiveLink (A6-ODOMETER)", "livelink")


@pytest.mark.asyncio
class TestLiveLinkOwnsOnlyItsOwnRows:
    async def test_a_day_with_a_service_row_and_a_tire_row_takes_the_reading(
        self, client: AsyncClient, auth_headers, linked, db_session
    ):
        vin, device_id = linked
        visit = await client.post(
            f"/api/vehicles/{vin}/service-visits",
            headers=auth_headers,
            json={
                "date": DAY.isoformat(),
                "odometer_km": "50000",
                "line_items": [{"description": "Replace tires", "cost": 640.0}],
            },
        )
        assert visit.status_code == 201, visit.text
        mounted = await client.post(
            f"/api/vehicles/{vin}/tires/create-and-mount",
            headers=auth_headers,
            json={
                "vin": vin,
                "position": "FL",
                "mounted_on": DAY.isoformat(),
                "mounted_odometer_km": "50012",
            },
        )
        assert mounted.status_code == 201, mounted.text
        before = await _rows(db_session, vin)
        assert [row[3] for row in before] == ["service_visit", "tire_mount"]

        await _ingest(db_session, vin, device_id, 50100.0, NOON)

        assert await _rows(db_session, vin) == [*before, _livelink("50100", "recorded")]

    async def test_a_day_with_only_a_manual_row_gains_a_livelink_row_beside_it(
        self, client: AsyncClient, auth_headers, linked, db_session
    ):
        vin, device_id = linked
        manual = await client.post(
            f"/api/vehicles/{vin}/odometer",
            headers=auth_headers,
            json={"vin": vin, "date": DAY.isoformat(), "odometer_km": "50000", "notes": "hand"},
        )
        assert manual.status_code == 201, manual.text
        hand: Row = (DAY, Decimal("50000"), "hand", "manual")

        await _ingest(db_session, vin, device_id, 50100.0, NOON)
        assert await _rows(db_session, vin) == [hand, _livelink("50100", "recorded")]

        await _ingest(db_session, vin, device_id, 50180.0, LATER)
        assert await _rows(db_session, vin) == [hand, _livelink("50180", "updated")]

    async def test_a_second_ingest_updates_the_days_livelink_row_beside_a_tire_reading(
        self, client: AsyncClient, auth_headers, linked, db_session
    ):
        """The shape that crashed on real data: LiveLink's own row, then a tread
        reading above it the same day, then LiveLink again."""
        vin, device_id = linked
        await _ingest(db_session, vin, device_id, 61000.0, NOON)
        stored = await client.post(
            f"/api/vehicles/{vin}/tires", headers=auth_headers, json={"vin": vin}
        )
        assert stored.status_code == 201, stored.text
        tire_id = stored.json()["id"]
        read = await client.post(
            f"/api/vehicles/{vin}/tires/{tire_id}/readings",
            headers=auth_headers,
            json={"recorded_at": DAY.isoformat(), "odometer_km": "61005", "tread_depth_mm": "6.5"},
        )
        assert read.status_code == 201, read.text
        tire_row: Row = (
            DAY,
            Decimal("61005"),
            auto_sync_marker("tire", tire_id),
            "tire",
        )
        assert await _rows(db_session, vin) == [_livelink("61000", "recorded"), tire_row]

        await _ingest(db_session, vin, device_id, 61020.0, LATER)

        assert await _rows(db_session, vin) == [_livelink("61020", "updated"), tire_row]
