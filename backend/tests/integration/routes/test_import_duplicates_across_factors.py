"""Skip duplicates still recognises a row stored with the old conversion factors.

Before v3.4.0 a mile was converted with 1.60934 km and a US gallon with
3.78541 L; both are now the exact definitions (1.609344 km, 3.785411784 L).
45,000 mi typed before the upgrade is stored as 72420.30 km, and the same
45,000 mi converts to 72420.48 km today. A duplicate check that compares the
odometer for equality treats those as two different fill-ups, so re-importing
an old backup, or a new export of the old row, imports every imperial record a
second time.

Every expected figure below is computed here from both factors with
`Decimal`, never read back from the code under test. The old factors appear
only as history: they are what pre-upgrade rows were written with.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.def_record import DEFRecord
from app.models.fuel import FuelRecord
from app.models.odometer import OdometerRecord
from app.models.service_line_item import ServiceLineItem
from app.models.service_visit import ServiceVisit
from app.models.vehicle import Vehicle

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

#: The mile pre-upgrade rows were converted with (history, not a factor in use).
OLD_MILE_KM = Decimal("1.60934")
#: The international mile, exact by definition.
MILE_KM = Decimal("1.609344")
#: The US gallon pre-upgrade rows were converted with (history).
OLD_US_GALLON_L = Decimal("3.78541")
#: The US gallon, exact by definition.
US_GALLON_L = Decimal("3.785411784")

#: Odometer columns are NUMERIC(10, 2); volume columns NUMERIC(9, 3).
KM_STEP = Decimal("0.01")
LITRE_STEP = Decimal("0.001")
#: Export writes distance in miles to three decimals.
EXPORT_MILE_STEP = Decimal("0.001")

DAY = date(2026, 3, 1)


def stored_before_upgrade(miles: str) -> Decimal:
    """The odometer column's value for `miles` typed before the upgrade."""
    return (Decimal(miles) * OLD_MILE_KM).quantize(KM_STEP)


def converted_today(miles: str) -> Decimal:
    """The canonical km the importer computes for `miles` today."""
    return Decimal(miles) * MILE_KM


@pytest.fixture(autouse=True)
def _reset_import_rate_limit():
    """Clear the shared import and export limiter storage between tests.

    Every import endpoint shares one module-level limiter, and the export
    round trip below also spends the export limiter. Mirrors
    `test_import_data.py`.
    """
    from app.routes.export import limiter as export_limiter
    from app.routes.import_data import limiter as import_limiter

    for lim in (import_limiter, export_limiter):
        storage = lim._storage
        storage.storage.clear()
        storage.expirations.clear()
        if hasattr(storage, "events"):
            storage.events.clear()


@asynccontextmanager
async def _vehicle(db_session: AsyncSession, user_id: object, vin: str) -> AsyncIterator[str]:
    """A committed diesel vehicle, with every row this file writes removed after."""
    db_session.add(
        Vehicle(
            vin=vin,
            user_id=user_id,
            nickname=vin,
            vehicle_type="Car",
            # Diesel so the DEF importer's fuel-type gate accepts the vehicle.
            fuel_type="diesel",
        )
    )
    await db_session.commit()
    try:
        yield vin
    finally:
        await db_session.rollback()
        visit_ids = (
            (await db_session.execute(select(ServiceVisit.id).where(ServiceVisit.vin == vin)))
            .scalars()
            .all()
        )
        if visit_ids:
            await db_session.execute(
                delete(ServiceLineItem).where(ServiceLineItem.visit_id.in_(visit_ids))
            )
        for model in (OdometerRecord, ServiceVisit, FuelRecord, DEFRecord):
            await db_session.execute(delete(model).where(model.vin == vin))
        await db_session.execute(delete(Vehicle).where(Vehicle.vin == vin))
        await db_session.commit()


async def _count(db_session: AsyncSession, model, vin: str) -> int:
    """How many `model` rows `vin` holds on DAY."""
    result = await db_session.execute(
        select(func.count()).select_from(model).where(model.vin == vin, model.date == DAY)
    )
    return int(result.scalar_one())


async def _post_csv(client: AsyncClient, headers, vin: str, pair: str, body: str):
    """Upload one CSV with skip duplicates on."""
    return await client.post(
        f"/api/import/vehicles/{vin}/{pair}/csv",
        headers=headers,
        files={"file": (f"{pair}.csv", BytesIO(body.encode()), "text/csv")},
        data={"skip_duplicates": "true"},
    )


class TestTheScenarioIsReal:
    async def test_the_two_factors_store_different_figures(self):
        """Precondition for every test below: without it they prove nothing."""
        assert stored_before_upgrade("45000") == Decimal("72420.30")
        assert converted_today("45000") == Decimal("72420.48")
        re_exported = (stored_before_upgrade("45000") / MILE_KM).quantize(EXPORT_MILE_STEP)
        assert re_exported == Decimal("44999.888")
        assert converted_today("44999.888") == Decimal("72420.299753472")
        assert converted_today("44999.888") != stored_before_upgrade("45000")


class TestCsvImportersSkipAPreUpgradeRow:
    async def test_service(self, client, auth_headers, test_user, db_session):
        async with _vehicle(db_session, test_user["id"], "DRIFTSVC000000001") as vin:
            db_session.add(
                ServiceVisit(
                    vin=vin,
                    date=DAY,
                    odometer_km=stored_before_upgrade("45000"),
                    service_category="Maintenance",
                    total_cost=Decimal("10"),
                )
            )
            await db_session.commit()
            body = (
                "units_version,unit_system,Date,Category,Odometer (mi),Cost\n"
                "6,imperial,2026-03-01,Maintenance,45000,10\n"
            )
            resp = await _post_csv(client, auth_headers, vin, "service", body)
            assert resp.status_code == 200, resp.text
            assert resp.json()["skipped_count"] == 1, resp.json()
            assert await _count(db_session, ServiceVisit, vin) == 1

    @pytest.mark.parametrize("miles", ["45000", "44999.888"])
    async def test_fuel(self, client, auth_headers, test_user, db_session, miles):
        """45000 is the figure the user typed; 44999.888 is today's export of the stored row."""
        async with _vehicle(db_session, test_user["id"], "DRIFTFUEL00000001") as vin:
            db_session.add(
                FuelRecord(
                    vin=vin,
                    date=DAY,
                    odometer_km=stored_before_upgrade("45000"),
                    liters=Decimal("47.318"),
                    is_full_tank=True,
                )
            )
            await db_session.commit()
            body = (
                "units_version,unit_system,Date,Odometer (mi),Volume (gal_us)\n"
                f"6,imperial,2026-03-01,{miles},12.5\n"
            )
            resp = await _post_csv(client, auth_headers, vin, "fuel", body)
            assert resp.status_code == 200, resp.text
            assert resp.json()["skipped_count"] == 1, resp.json()
            assert await _count(db_session, FuelRecord, vin) == 1

    async def test_def(self, client, auth_headers, test_user, db_session):
        async with _vehicle(db_session, test_user["id"], "DRIFTDEF000000001") as vin:
            db_session.add(
                DEFRecord(
                    vin=vin,
                    date=DAY,
                    odometer_km=stored_before_upgrade("45000"),
                    liters=Decimal("9.464"),
                )
            )
            await db_session.commit()
            body = "units_version,unit_system,Date,Odometer (mi)\n6,imperial,2026-03-01,45000\n"
            resp = await _post_csv(client, auth_headers, vin, "def", body)
            assert resp.status_code == 200, resp.text
            assert resp.json()["skipped_count"] == 1, resp.json()
            assert await _count(db_session, DEFRecord, vin) == 1

    async def test_odometer(self, client, auth_headers, test_user, db_session):
        async with _vehicle(db_session, test_user["id"], "DRIFTODO000000001") as vin:
            db_session.add(
                OdometerRecord(vin=vin, date=DAY, odometer_km=stored_before_upgrade("45000"))
            )
            await db_session.commit()
            body = "units_version,unit_system,Date,Reading (mi)\n6,imperial,2026-03-01,45000\n"
            resp = await _post_csv(client, auth_headers, vin, "odometer", body)
            assert resp.status_code == 200, resp.text
            assert resp.json()["skipped_count"] == 1, resp.json()
            assert await _count(db_session, OdometerRecord, vin) == 1

    async def test_fuel_export_then_re_import(self, client, auth_headers, test_user, db_session):
        """The user-facing round trip: export the pre-upgrade row today, import it back."""
        async with _vehicle(db_session, test_user["id"], "DRIFTROUND0000001") as vin:
            db_session.add(
                FuelRecord(
                    vin=vin,
                    date=DAY,
                    odometer_km=stored_before_upgrade("45000"),
                    liters=Decimal("47.318"),
                    is_full_tank=True,
                )
            )
            await db_session.commit()
            exported = await client.get(
                f"/api/export/vehicles/{vin}/fuel/csv?units=imperial", headers=auth_headers
            )
            assert exported.status_code == 200, exported.text
            row = next(csv.DictReader(io.StringIO(exported.text)))
            expected_cell = (stored_before_upgrade("45000") / MILE_KM).quantize(EXPORT_MILE_STEP)
            assert Decimal(row["Odometer (mi)"]) == expected_cell

            resp = await _post_csv(client, auth_headers, vin, "fuel", exported.text)
            assert resp.status_code == 200, resp.text
            assert resp.json()["skipped_count"] == 1, resp.json()
            assert await _count(db_session, FuelRecord, vin) == 1

    async def test_a_row_already_stored_twice_is_skipped_not_an_error(
        self, client, auth_headers, test_user, db_session
    ):
        """A band can match more than one stored row; any match means skip.

        Asking for exactly one match turned a vehicle that already held the
        fill-up twice into a reported row error on every later re-import.
        """
        async with _vehicle(db_session, test_user["id"], "DRIFTTWICE0000001") as vin:
            for _ in range(2):
                db_session.add(
                    FuelRecord(
                        vin=vin,
                        date=DAY,
                        odometer_km=stored_before_upgrade("45000"),
                        liters=Decimal("47.318"),
                    )
                )
            await db_session.commit()
            body = "units_version,unit_system,Date,Odometer (mi)\n6,imperial,2026-03-01,45000\n"
            resp = await _post_csv(client, auth_headers, vin, "fuel", body)
            assert resp.status_code == 200, resp.text
            assert resp.json()["error_count"] == 0, resp.json()
            assert resp.json()["skipped_count"] == 1, resp.json()
            assert await _count(db_session, FuelRecord, vin) == 2

    async def test_a_low_odometer_rounded_down_on_storage(
        self, client, auth_headers, test_user, db_session
    ):
        """Both allowances at once: the factor drift and the column's rounding.

        2008 mi was 3231.55472 km with the old mile, stored rounded down to
        3231.55. Today it converts to 3231.562752 km: 0.012752 km away, more
        than either allowance alone covers at this odometer.
        """
        stored = stored_before_upgrade("2008")
        assert stored == Decimal("3231.55")
        today = converted_today("2008")
        assert today == Decimal("3231.562752")
        assert today - stored > max(KM_STEP, today * Decimal("3e-6"))
        async with _vehicle(db_session, test_user["id"], "DRIFTLOW000000001") as vin:
            db_session.add(FuelRecord(vin=vin, date=DAY, odometer_km=stored, liters=Decimal("30")))
            await db_session.commit()
            body = "units_version,unit_system,Date,Odometer (mi)\n6,imperial,2026-03-01,2008\n"
            resp = await _post_csv(client, auth_headers, vin, "fuel", body)
            assert resp.status_code == 200, resp.text
            assert resp.json()["skipped_count"] == 1, resp.json()
            assert await _count(db_session, FuelRecord, vin) == 1


class TestADifferentOdometerOnTheSameDayStillImports:
    @pytest.mark.parametrize("miles", ["45010", "45000.5"])
    async def test_fuel(self, client, auth_headers, test_user, db_session, miles):
        """45,010 mi is 16 km on; 45,000.5 mi is under a kilometre on, still a new fill-up."""
        stored = stored_before_upgrade("45000")
        assert converted_today(miles) - stored > Decimal("0.5")
        async with _vehicle(db_session, test_user["id"], "DRIFTGUARD0000001") as vin:
            db_session.add(
                FuelRecord(vin=vin, date=DAY, odometer_km=stored, liters=Decimal("47.318"))
            )
            await db_session.commit()
            body = (
                "units_version,unit_system,Date,Odometer (mi),Volume (gal_us)\n"
                f"6,imperial,2026-03-01,{miles},12.5\n"
            )
            resp = await _post_csv(client, auth_headers, vin, "fuel", body)
            assert resp.status_code == 200, resp.text
            assert resp.json()["success_count"] == 1, resp.json()
            assert resp.json()["skipped_count"] == 0, resp.json()
            assert await _count(db_session, FuelRecord, vin) == 2


class TestLegacyJsonBackupSkipsPreUpgradeRows:
    async def test_every_odometer_keyed_section(self, client, auth_headers, test_user, db_session):
        """A v2 backup carries miles, converted on ingest in every section."""
        stored = stored_before_upgrade("45000")
        async with _vehicle(db_session, test_user["id"], "DRIFTJSON00000001") as vin:
            db_session.add_all(
                [
                    ServiceVisit(
                        vin=vin,
                        date=DAY,
                        odometer_km=stored,
                        service_category="Maintenance",
                        total_cost=Decimal("10"),
                    ),
                    FuelRecord(vin=vin, date=DAY, odometer_km=stored, liters=Decimal("47.318")),
                    DEFRecord(vin=vin, date=DAY, odometer_km=stored, liters=Decimal("9.464")),
                    OdometerRecord(vin=vin, date=DAY, odometer_km=stored),
                ]
            )
            await db_session.commit()
            backup = {
                "service_records": [
                    {"date": "2026-03-01", "mileage": 45000, "service_type": "Oil", "cost": 10}
                ],
                "fuel_records": [{"date": "2026-03-01", "mileage": 45000, "gallons": 12.5}],
                "def_records": [{"date": "2026-03-01", "mileage": 45000, "gallons": 2.5}],
                "odometer_records": [{"date": "2026-03-01", "reading": 45000}],
            }
            resp = await client.post(
                f"/api/import/vehicles/{vin}/json",
                headers=auth_headers,
                files={
                    "file": ("v2.json", BytesIO(json.dumps(backup).encode()), "application/json")
                },
                data={"skip_duplicates": "true"},
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            for section in ("service_records", "fuel_records", "def_records", "odometer_records"):
                assert data[section]["skipped_count"] == 1, (section, data)
            assert await _count(db_session, ServiceVisit, vin) == 1
            assert await _count(db_session, FuelRecord, vin) == 1
            assert await _count(db_session, DEFRecord, vin) == 1
            assert await _count(db_session, OdometerRecord, vin) == 1


class TestThirdPartyImportSkipsAPreUpgradeRow:
    async def test_fuelio_in_miles_and_gallons(self, client, auth_headers, test_user, db_session):
        """Its duplicate key also compares the volume, converted from gallons the same way."""
        stored_litres = (Decimal("12.5") * OLD_US_GALLON_L).quantize(LITRE_STEP)
        assert stored_litres == Decimal("47.318")
        assert Decimal("12.5") * US_GALLON_L == Decimal("47.3176473000")
        async with _vehicle(db_session, test_user["id"], "DRIFTFUELIO000001") as vin:
            db_session.add(
                FuelRecord(
                    vin=vin,
                    date=DAY,
                    odometer_km=stored_before_upgrade("45000"),
                    liters=stored_litres,
                    is_full_tank=True,
                )
            )
            await db_session.commit()
            resp = await client.post(
                f"/api/import/vehicles/{vin}/fuel/fuelio",
                headers=auth_headers,
                files={
                    "file": (
                        "fuelio.csv",
                        "Date,Odometer,Gallons,Price,Total cost\n2026-03-01,45000,12.5,3.50,43.75\n",
                        "text/csv",
                    )
                },
                data={"skip_duplicates": "true", "odometer_unit": "mi"},
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["skipped_count"] == 1, resp.json()
            assert await _count(db_session, FuelRecord, vin) == 1
