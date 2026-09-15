"""A tire event owns only the odometer records it created.

A service visit, a fuel-up or a LiveLink device may already have recorded the
vehicle's odometer on the day a tire is mounted, read or fitted. The tire paths
used to treat any automatic record on that day as theirs: they overwrote its
value, re-marked it with the tire event's own marker, and from then on the
period editor moved it and a tire delete removed it. A service visit's reading
could end up two days later than the visit, and the vehicle's odometer history
then ran backwards.

The rule these tests pin: a tire event updates a record carrying its own
marker, publishes nothing onto a day that already has any other record, and
creates its own record only on a day with none. Fuel, DEF and service visits
keep the one-reading-per-day policy they have always had.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.models.odometer import OdometerRecord
from app.models.tire import Tire, TireMountPeriod
from app.models.vehicle import Vehicle
from app.services.tire_service import (
    ODOMETER_SOURCE_ROTATION,
    ODOMETER_SOURCE_SET,
    ODOMETER_SOURCE_TIRE,
    ODOMETER_SOURCE_TIRE_DISMOUNT,
    ODOMETER_SOURCE_TIRE_MOUNT,
)
from app.utils.odometer_sync import auto_sync_marker

DAY = date(2026, 6, 21)
EARLIER = DAY - timedelta(days=30)
TIRE_SOURCES = {
    ODOMETER_SOURCE_TIRE,
    ODOMETER_SOURCE_TIRE_MOUNT,
    ODOMETER_SOURCE_TIRE_DISMOUNT,
    ODOMETER_SOURCE_ROTATION,
    ODOMETER_SOURCE_SET,
}

Row = tuple[date, Decimal, str | None, str | None]


@pytest_asyncio.fixture
async def vehicle(db_session, test_user):
    """A vehicle for one test: these assertions list every odometer record it has."""
    vin = f"TYRESYN{uuid.uuid4().hex[:10].upper()}"
    db_session.add(
        Vehicle(
            vin=vin,
            user_id=test_user["id"],
            nickname="Odometer ownership",
            vehicle_type="Car",
            year=2018,
            make="Mazda",
            model="CX-5",
        )
    )
    await db_session.commit()
    yield vin
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


async def _rows(db_session, vin: str) -> list[Row]:
    return [(r.date, r.odometer_km, r.notes, r.source) for r in await _records(db_session, vin)]


async def _service_visit(client: AsyncClient, headers, vin: str, day: date, km: str) -> int:
    made = await client.post(
        f"/api/vehicles/{vin}/service-visits",
        headers=headers,
        json={
            "date": day.isoformat(),
            "odometer_km": km,
            "line_items": [{"description": "Replace tires", "cost": 640.0}],
        },
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def _fuel(client: AsyncClient, headers, vin: str, day: date, km: str) -> int:
    made = await client.post(
        f"/api/vehicles/{vin}/fuel",
        headers=headers,
        json={
            "vin": vin,
            "date": day.isoformat(),
            "odometer_km": km,
            "liters": 45.0,
            "cost": 70.0,
            "price_per_unit": 1.55,
            "is_full_tank": True,
        },
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


async def _create_and_mount(client: AsyncClient, headers, vin: str, position: str, **body) -> int:
    made = await client.post(
        f"/api/vehicles/{vin}/tires/create-and-mount",
        headers=headers,
        json={"vin": vin, "position": position, **body},
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


def _service_row(visit_id: int, km: str) -> Row:
    marker = auto_sync_marker("service_visit", visit_id)
    return (DAY, Decimal(km), marker, "service_visit")


async def _mount_on_day(client: AsyncClient, headers, vin: str) -> None:
    await _create_and_mount(
        client, headers, vin, "FL", mounted_on=DAY.isoformat(), mounted_odometer_km="50012"
    )


async def _mount_existing_on_day(client: AsyncClient, headers, vin: str) -> None:
    made = await client.post(f"/api/vehicles/{vin}/tires", headers=headers, json={"vin": vin})
    assert made.status_code == 201, made.text
    mounted = await client.post(
        f"/api/vehicles/{vin}/tires/{made.json()['id']}/mount",
        headers=headers,
        json={"position": "FR", "mounted_on": DAY.isoformat(), "mounted_odometer_km": "50012"},
    )
    assert mounted.status_code == 200, mounted.text


async def _dismount_on_day(client: AsyncClient, headers, vin: str) -> None:
    tire_id = await _create_and_mount(client, headers, vin, "RL", mounted_on=EARLIER.isoformat())
    off = await client.post(
        f"/api/vehicles/{vin}/tires/{tire_id}/dismount",
        headers=headers,
        json={"dismounted_on": DAY.isoformat(), "dismounted_odometer_km": "50012"},
    )
    assert off.status_code == 200, off.text


async def _retire_on_day(client: AsyncClient, headers, vin: str) -> None:
    tire_id = await _create_and_mount(client, headers, vin, "RR", mounted_on=EARLIER.isoformat())
    retired = await client.post(
        f"/api/vehicles/{vin}/tires/{tire_id}/retire",
        headers=headers,
        json={"dismounted_on": DAY.isoformat(), "dismounted_odometer_km": "50012"},
    )
    assert retired.status_code == 200, retired.text


async def _rotate_on_day(client: AsyncClient, headers, vin: str) -> None:
    left = await _create_and_mount(client, headers, vin, "FL", mounted_on=EARLIER.isoformat())
    right = await _create_and_mount(client, headers, vin, "FR", mounted_on=EARLIER.isoformat())
    rotated = await client.post(
        f"/api/vehicles/{vin}/tires/rotate",
        headers=headers,
        json={
            "rotated_on": DAY.isoformat(),
            "odometer_km": "50012",
            "moves": [
                {"tire_id": left, "position": "FR"},
                {"tire_id": right, "position": "FL"},
            ],
        },
    )
    assert rotated.status_code == 200, rotated.text


@pytest.mark.asyncio
class TestAnotherSourcesReadingIsNeverTakenOver:
    @pytest.mark.parametrize(
        "writer",
        [
            _mount_on_day,
            _mount_existing_on_day,
            _dismount_on_day,
            _retire_on_day,
            _rotate_on_day,
        ],
        ids=["create_and_mount", "mount", "dismount", "retire", "rotate"],
    )
    async def test_a_tire_write_leaves_a_service_visits_reading_alone(
        self, client: AsyncClient, auth_headers, vehicle, db_session, writer
    ):
        """The service visit that replaced the tires recorded the odometer that
        day. Mounting them at a slightly different figure used to overwrite the
        visit's value and re-mark the record as the mount's own."""
        visit_id = await _service_visit(client, auth_headers, vehicle, DAY, "50000")
        assert await _rows(db_session, vehicle) == [_service_row(visit_id, "50000")]

        await writer(client, auth_headers, vehicle)

        assert await _rows(db_session, vehicle) == [_service_row(visit_id, "50000")]

    async def test_the_period_editor_neither_takes_over_nor_moves_a_service_visits_reading(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        """A legacy period given the service visit's own date and odometer (what
        the editor's Use button fills in), then moved two days later. The
        visit's record used to become the period's, and the move carried it to
        the new date."""
        visit_id = await _service_visit(client, auth_headers, vehicle, DAY, "143302.07")
        tire = Tire(vin=vehicle, position="FL", brand="Legacy")
        db_session.add(tire)
        await db_session.flush()
        tire_id = tire.id
        period = TireMountPeriod(
            tire_id=tire_id,
            position="FL",
            mounted_on=None,
            mounted_odometer_km=None,
            is_assumed=True,
            observed_active_on=date(2026, 9, 4),
        )
        db_session.add(period)
        await db_session.commit()
        period_id = period.id
        url = f"/api/vehicles/{vehicle}/tires/{tire_id}/mount-periods/{period_id}"

        used = await client.put(
            url,
            headers=auth_headers,
            json={"mounted_on": DAY.isoformat(), "mounted_odometer_km": "143302.07"},
        )
        assert used.status_code == 200, used.text
        assert await _rows(db_session, vehicle) == [_service_row(visit_id, "143302.07")]

        later = DAY + timedelta(days=2)
        moved = await client.put(
            url,
            headers=auth_headers,
            json={"mounted_on": later.isoformat(), "mounted_odometer_km": "143302.07"},
        )
        assert moved.status_code == 200, moved.text
        assert await _rows(db_session, vehicle) == [
            _service_row(visit_id, "143302.07"),
            (
                later,
                Decimal("143302.07"),
                auto_sync_marker(ODOMETER_SOURCE_TIRE_MOUNT, period_id),
                ODOMETER_SOURCE_TIRE_MOUNT,
            ),
        ]

    async def test_a_past_period_leaves_a_fuel_ups_reading_alone(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        """Add past period with a mount date that matches an older fill-up."""
        tire_id = await _create_and_mount(
            client, auth_headers, vehicle, "FL", mounted_on=DAY.isoformat()
        )
        fuel_day = date(2026, 1, 10)
        fuel_id = await _fuel(client, auth_headers, vehicle, fuel_day, "31000")
        (fuel_record,) = await _records(db_session, vehicle)
        fuel_row = (
            fuel_record.date,
            fuel_record.odometer_km,
            fuel_record.notes,
            fuel_record.source,
            fuel_record.fuel_record_id,
        )
        assert fuel_row == (
            fuel_day,
            Decimal("31000"),
            auto_sync_marker("fuel", fuel_id),
            "fuel",
            fuel_id,
        )

        added = await client.post(
            f"/api/vehicles/{vehicle}/tires/{tire_id}/mount-periods",
            headers=auth_headers,
            json={
                "position": "FR",
                "mounted_on": fuel_day.isoformat(),
                "mounted_odometer_km": "31020",
                "dismounted_on": "2026-03-01",
                "dismounted_odometer_km": "36000",
            },
        )
        assert added.status_code == 201, added.text
        new_period_id = next(
            p["id"] for p in added.json()["mount_periods"] if p["position"] == "FR"
        )

        records = await _records(db_session, vehicle)
        assert [(r.date, r.odometer_km, r.notes, r.source, r.fuel_record_id) for r in records] == [
            fuel_row,
            (
                date(2026, 3, 1),
                Decimal("36000"),
                auto_sync_marker(ODOMETER_SOURCE_TIRE_DISMOUNT, new_period_id),
                ODOMETER_SOURCE_TIRE_DISMOUNT,
                None,
            ),
        ]

    async def test_a_reading_leaves_a_livelink_reading_alone(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        db_session.add(
            OdometerRecord(
                vin=vehicle,
                date=DAY,
                odometer_km=Decimal("61000.40"),
                source="livelink",
                notes="Auto-recorded from LiveLink (A6-Odometer)",
            )
        )
        await db_session.commit()
        stored = await client.post(
            f"/api/vehicles/{vehicle}/tires", headers=auth_headers, json={"vin": vehicle}
        )
        assert stored.status_code == 201, stored.text

        read = await client.post(
            f"/api/vehicles/{vehicle}/tires/{stored.json()['id']}/readings",
            headers=auth_headers,
            json={"recorded_at": DAY.isoformat(), "odometer_km": "61050", "tread_depth_mm": "6.5"},
        )
        assert read.status_code == 201, read.text

        assert await _rows(db_session, vehicle) == [
            (DAY, Decimal("61000.40"), "Auto-recorded from LiveLink (A6-Odometer)", "livelink")
        ]

    async def test_a_set_fit_leaves_a_service_visits_reading_alone(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        tire_id = await _create_and_mount(
            client, auth_headers, vehicle, "FL", mounted_on="2025-11-01"
        )
        off = await client.post(
            f"/api/vehicles/{vehicle}/tires/{tire_id}/dismount",
            headers=auth_headers,
            json={"dismounted_on": "2026-04-01"},
        )
        assert off.status_code == 200, off.text
        winter = await client.post(
            f"/api/vehicles/{vehicle}/tire-sets", headers=auth_headers, json={"name": "Winter"}
        )
        assert winter.status_code == 201, winter.text
        set_id = winter.json()["id"]
        assigned = await client.put(
            f"/api/vehicles/{vehicle}/tires/{tire_id}",
            headers=auth_headers,
            json={"set_id": set_id},
        )
        assert assigned.status_code == 200, assigned.text
        visit_id = await _service_visit(client, auth_headers, vehicle, DAY, "50000")

        fitted = await client.post(
            f"/api/vehicles/{vehicle}/tire-sets/{set_id}/mount",
            headers=auth_headers,
            json={"mounted_on": DAY.isoformat(), "odometer_km": "50012"},
        )
        assert fitted.status_code == 200, fitted.text

        assert await _rows(db_session, vehicle) == [_service_row(visit_id, "50000")]

    async def test_a_tire_delete_leaves_the_reading_it_did_not_create(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        """The last step of the chain: a record a tire had taken over went with
        the tire when it was deleted."""
        visit_id = await _service_visit(client, auth_headers, vehicle, DAY, "50000")
        tire_id = await _create_and_mount(
            client,
            auth_headers,
            vehicle,
            "FL",
            mounted_on=DAY.isoformat(),
            mounted_odometer_km="50012",
        )

        gone = await client.delete(f"/api/vehicles/{vehicle}/tires/{tire_id}", headers=auth_headers)
        assert gone.status_code == 204, gone.text

        assert await _rows(db_session, vehicle) == [_service_row(visit_id, "50000")]


@pytest.mark.asyncio
class TestATireEventStillKeepsItsOwnRecord:
    async def test_a_mount_on_a_free_day_creates_its_record_and_an_edit_updates_it_in_place(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        tire_id = await _create_and_mount(
            client,
            auth_headers,
            vehicle,
            "FL",
            mounted_on=DAY.isoformat(),
            mounted_odometer_km="50000",
        )
        (period_id,) = [
            p.id
            for p in (
                await db_session.execute(
                    select(TireMountPeriod).where(TireMountPeriod.tire_id == tire_id)
                )
            )
            .scalars()
            .all()
        ]
        marker = auto_sync_marker(ODOMETER_SOURCE_TIRE_MOUNT, period_id)
        (created,) = await _records(db_session, vehicle)
        created_id = created.id
        assert (created.date, created.odometer_km, created.notes) == (DAY, Decimal("50000"), marker)
        # A later row on another day, so a delete and recreate of the mount's
        # record could not reuse its id (SQLite hands out the highest plus one).
        later = await client.post(
            f"/api/vehicles/{vehicle}/odometer",
            headers=auth_headers,
            json={"vin": vehicle, "date": "2026-07-01", "odometer_km": "50900", "notes": "hand"},
        )
        assert later.status_code == 201, later.text

        edited = await client.put(
            f"/api/vehicles/{vehicle}/tires/{tire_id}/mount-periods/{period_id}",
            headers=auth_headers,
            json={"mounted_on": DAY.isoformat(), "mounted_odometer_km": "50040"},
        )
        assert edited.status_code == 200, edited.text

        updated, _hand = await _records(db_session, vehicle)
        assert (updated.id, updated.date, updated.odometer_km, updated.notes) == (
            created_id,
            DAY,
            Decimal("50040"),
            marker,
        )

    async def test_a_second_reading_updates_its_own_record_beside_a_newer_one(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        """The tire's own record is found by its marker, not by being the day's
        newest: a manual entry added after the first reading does not stop the
        tire's own figure from being corrected."""
        stored = await client.post(
            f"/api/vehicles/{vehicle}/tires", headers=auth_headers, json={"vin": vehicle}
        )
        assert stored.status_code == 201, stored.text
        tire_id = stored.json()["id"]
        readings = f"/api/vehicles/{vehicle}/tires/{tire_id}/readings"
        first = await client.post(
            readings,
            headers=auth_headers,
            json={"recorded_at": DAY.isoformat(), "odometer_km": "50000", "tread_depth_mm": "7.0"},
        )
        assert first.status_code == 201, first.text
        manual = await client.post(
            f"/api/vehicles/{vehicle}/odometer",
            headers=auth_headers,
            json={"vin": vehicle, "date": DAY.isoformat(), "odometer_km": "50100", "notes": "hand"},
        )
        assert manual.status_code == 201, manual.text

        second = await client.post(
            readings,
            headers=auth_headers,
            json={"recorded_at": DAY.isoformat(), "odometer_km": "50060", "pressure_kpa": "230"},
        )
        assert second.status_code == 201, second.text

        assert await _rows(db_session, vehicle) == [
            (
                DAY,
                Decimal("50060"),
                auto_sync_marker(ODOMETER_SOURCE_TIRE, tire_id),
                ODOMETER_SOURCE_TIRE,
            ),
            (DAY, Decimal("50100"), "hand", "manual"),
        ]


@pytest.mark.asyncio
class TestNonTireSourcesKeepOneReadingPerDay:
    async def test_a_second_fill_up_on_a_day_takes_over_the_first_ones_reading(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        first = await _fuel(client, auth_headers, vehicle, DAY, "70000")
        assert [(r.notes, r.fuel_record_id) for r in await _records(db_session, vehicle)] == [
            (auto_sync_marker("fuel", first), first)
        ]

        second = await _fuel(client, auth_headers, vehicle, DAY, "70300")

        records = await _records(db_session, vehicle)
        assert [(r.date, r.odometer_km, r.notes, r.source, r.fuel_record_id) for r in records] == [
            (DAY, Decimal("70300"), auto_sync_marker("fuel", second), "fuel", second)
        ]
        assert not {r.source for r in records} & TIRE_SOURCES
