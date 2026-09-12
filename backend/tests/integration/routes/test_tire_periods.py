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
from datetime import date as date_type
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.models.odometer import OdometerRecord
from app.models.tire import Tire, TireMountPeriod
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


async def _tire_positions(db_session, vin: str) -> dict[int, str | None]:
    db_session.expire_all()
    rows = (await db_session.execute(select(Tire.id, Tire.position).where(Tire.vin == vin))).all()
    return {tire_id: position for tire_id, position in rows}


@pytest.mark.asyncio
class TestWritersRefuseContradictions:
    async def test_a_mount_backdated_before_the_last_dismount_is_refused(
        self, client: AsyncClient, auth_headers, vehicle
    ):
        base = f"/api/vehicles/{vehicle}/tires"
        made = await client.post(
            f"{base}/create-and-mount",
            headers=auth_headers,
            json={
                "vin": vehicle,
                "position": "FL",
                "mounted_on": "2026-01-01",
                "mounted_odometer_km": "1000",
            },
        )
        tire_id = made.json()["id"]
        await client.post(
            f"{base}/{tire_id}/dismount",
            headers=auth_headers,
            json={"dismounted_on": "2026-03-01", "dismounted_odometer_km": "2000"},
        )
        again = await client.post(
            f"{base}/{tire_id}/mount",
            headers=auth_headers,
            json={"position": "FR", "mounted_on": "2026-02-15", "mounted_odometer_km": "2000"},
        )
        assert again.status_code == 409, again.text
        assert "dismounted" in again.json()["detail"]

    async def test_a_dismount_dated_before_its_mount_is_refused(
        self, client: AsyncClient, auth_headers, vehicle
    ):
        base = f"/api/vehicles/{vehicle}/tires"
        made = await client.post(
            f"{base}/create-and-mount",
            headers=auth_headers,
            json={
                "vin": vehicle,
                "position": "FL",
                "mounted_on": "2026-04-10",
                "mounted_odometer_km": "5000",
            },
        )
        tire_id = made.json()["id"]
        off = await client.post(
            f"{base}/{tire_id}/dismount", headers=auth_headers, json={"dismounted_on": "2026-03-01"}
        )
        assert off.status_code == 409, off.text
        still = await client.get(base, headers=auth_headers)
        assert [t["position"] for t in still.json()["tires"] if t["id"] == tire_id] == ["FL"]
        # The 409 rolled the request back: a later, valid write on the SAME
        # session succeeds. Without production's rollback in the test
        # dependency, the flushed dismount would still be pending here and
        # the SQLite lock guard would raise on the open transaction.
        ok = await client.post(
            f"{base}/{tire_id}/dismount", headers=auth_headers, json={"dismounted_on": "2026-05-01"}
        )
        assert ok.status_code == 200, ok.text

    async def test_a_tire_with_an_old_fault_elsewhere_can_still_be_dismounted(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        """Incremental policy (plan review R1-M2): a legacy fault on another
        period neither blocks this write nor is silently healed by it."""
        base = f"/api/vehicles/{vehicle}/tires"
        made = await client.post(
            f"{base}/create-and-mount",
            headers=auth_headers,
            json={
                "vin": vehicle,
                "position": "FL",
                "mounted_on": "2026-04-01",
                "mounted_odometer_km": "5000",
            },
        )
        tire_id = made.json()["id"]
        # Seeded the way a pre-3.4.0 writer could leave one: reversed odometers.
        db_session.add(
            TireMountPeriod(
                tire_id=tire_id,
                position="FR",
                mounted_on=date_type(2025, 1, 1),
                dismounted_on=date_type(2025, 3, 1),
                mounted_odometer_km=Decimal("4000"),
                dismounted_odometer_km=Decimal("3000"),
                is_assumed=False,
            )
        )
        await db_session.commit()
        off = await client.post(
            f"{base}/{tire_id}/dismount",
            headers=auth_headers,
            json={"dismounted_on": "2026-06-01", "dismounted_odometer_km": "6000"},
        )
        assert off.status_code == 200, off.text
        legacy = next(p for p in await _periods(db_session, tire_id) if p.position == "FR")
        assert legacy.id in off.json()["blocking_period_ids"], "the old fault stays flagged"

    async def test_a_rotation_dated_before_a_mount_moves_nothing(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        base = f"/api/vehicles/{vehicle}/tires"
        ids = {}
        for position, day in (("FL", "2026-01-01"), ("FR", "2026-04-10")):
            made = await client.post(
                f"{base}/create-and-mount",
                headers=auth_headers,
                json={
                    "vin": vehicle,
                    "position": position,
                    "mounted_on": day,
                    "mounted_odometer_km": "1000",
                },
            )
            ids[position] = made.json()["id"]
        rotated = await client.post(
            f"{base}/rotate",
            headers=auth_headers,
            json={
                "rotated_on": "2026-03-01",
                "odometer_km": "1500",
                "moves": [
                    {"tire_id": ids["FL"], "position": "FR"},
                    {"tire_id": ids["FR"], "position": "FL"},
                ],
            },
        )
        assert rotated.status_code == 409, rotated.text
        assert await _tire_positions(db_session, vehicle) == {ids["FL"]: "FL", ids["FR"]: "FR"}

    async def test_a_set_fit_dated_before_a_displaced_tires_mount_changes_nothing(
        self, client: AsyncClient, auth_headers, vehicle, db_session
    ):
        """R1-H2: the tires coming OFF are validated too."""
        base = f"/api/vehicles/{vehicle}/tires"
        y = (
            await client.post(
                f"{base}/create-and-mount",
                headers=auth_headers,
                json={
                    "vin": vehicle,
                    "position": "FL",
                    "brand": "Y",
                    "mounted_on": "2026-01-01",
                    "mounted_odometer_km": "1000",
                },
            )
        ).json()["id"]
        await client.post(
            f"{base}/{y}/dismount",
            headers=auth_headers,
            json={"dismounted_on": "2026-02-01", "dismounted_odometer_km": "2000"},
        )
        x = (
            await client.post(
                f"{base}/create-and-mount",
                headers=auth_headers,
                json={
                    "vin": vehicle,
                    "position": "FL",
                    "brand": "X",
                    "mounted_on": "2026-03-01",
                    "mounted_odometer_km": "3000",
                },
            )
        ).json()["id"]
        set_id = (
            await client.post(
                f"/api/vehicles/{vehicle}/tire-sets", headers=auth_headers, json={"name": "Winter"}
            )
        ).json()["id"]
        assert (
            await client.put(f"{base}/{y}", headers=auth_headers, json={"set_id": set_id})
        ).status_code == 200
        before_positions = await _tire_positions(db_session, vehicle)
        before_records = len(await _records(db_session, vehicle))
        before_periods = len(await _periods(db_session, x)) + len(await _periods(db_session, y))

        fit = await client.post(
            f"/api/vehicles/{vehicle}/tire-sets/{set_id}/mount",
            headers=auth_headers,
            json={"mounted_on": "2026-02-15", "odometer_km": "2500"},
        )
        assert fit.status_code == 409, fit.text
        assert await _tire_positions(db_session, vehicle) == before_positions
        assert len(await _records(db_session, vehicle)) == before_records
        assert (
            len(await _periods(db_session, x)) + len(await _periods(db_session, y))
            == before_periods
        )

    async def test_a_retired_tire_cannot_be_mounted_or_rotated(
        self, client: AsyncClient, auth_headers, vehicle
    ):
        base = f"/api/vehicles/{vehicle}/tires"
        made = await client.post(
            f"{base}/create-and-mount",
            headers=auth_headers,
            json={"vin": vehicle, "position": "FL"},
        )
        tire_id = made.json()["id"]
        assert (
            await client.post(f"{base}/{tire_id}/retire", headers=auth_headers, json={})
        ).status_code == 200
        mount = await client.post(
            f"{base}/{tire_id}/mount", headers=auth_headers, json={"position": "FL"}
        )
        assert mount.status_code == 409 and "retired" in mount.json()["detail"]
        other = (
            await client.post(
                f"{base}/create-and-mount",
                headers=auth_headers,
                json={"vin": vehicle, "position": "FR"},
            )
        ).json()["id"]
        rotate = await client.post(
            f"{base}/rotate",
            headers=auth_headers,
            json={
                "moves": [
                    {"tire_id": tire_id, "position": "FR"},
                    {"tire_id": other, "position": "FL"},
                ]
            },
        )
        assert rotate.status_code == 409 and "retired" in rotate.json()["detail"]
