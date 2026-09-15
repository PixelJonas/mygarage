"""`GET /odometer/nearest?date=`: the reading closest to a day.

Feeds the odometer suggestion on every tire dialog. One indexed query pair,
not a client-side scan of the paginated list a LiveLink vehicle fills with
thousands of rows. Declared above `/{record_id}` in the router, or FastAPI
reads "nearest" as a record id and answers 422; the first test here is what
notices if someone reorders the file.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.models.odometer import OdometerRecord
from app.models.vehicle import Vehicle


@pytest.fixture
async def vehicle(db_session, test_user):
    vin = f"NEAREST{uuid.uuid4().hex[:10].upper()}"[:17]
    db_session.add(
        Vehicle(
            vin=vin,
            user_id=test_user["id"],
            nickname="Nearest",
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


async def _seed(client, headers, vin, *rows):
    for day, km in rows:
        r = await client.post(
            f"/api/vehicles/{vin}/odometer",
            headers=headers,
            json={"vin": vin, "date": day, "odometer_km": km},
        )
        assert r.status_code == 201, r.text


async def _nearest(client, headers, vin, day):
    return await client.get(
        f"/api/vehicles/{vin}/odometer/nearest", headers=headers, params={"date": day}
    )


@pytest.mark.asyncio
class TestNearest:
    async def test_no_readings_is_404_not_422(self, client: AsyncClient, auth_headers, vehicle):
        r = await _nearest(client, auth_headers, vehicle, "2026-04-10")
        assert r.status_code == 404, r.text

    async def test_nearest_before_and_after(self, client: AsyncClient, auth_headers, vehicle):
        await _seed(
            client, auth_headers, vehicle, ("2026-04-01", "100000"), ("2026-04-20", "100600")
        )
        r = await _nearest(client, auth_headers, vehicle, "2026-04-05")
        assert r.status_code == 200, r.text
        assert r.json() == {
            "date": "2026-04-01",
            "odometer_km": "100000.00",
            "source": "manual",
            "days_away": -4,
        }
        r = await _nearest(client, auth_headers, vehicle, "2026-04-18")
        assert r.json()["date"] == "2026-04-20" and r.json()["days_away"] == 2

    async def test_a_tie_goes_to_the_reading_on_or_before(
        self, client: AsyncClient, auth_headers, vehicle
    ):
        await _seed(
            client, auth_headers, vehicle, ("2026-04-01", "100000"), ("2026-04-11", "100300")
        )
        r = await _nearest(client, auth_headers, vehicle, "2026-04-06")
        assert r.json()["date"] == "2026-04-01"

    async def test_same_day_duplicates_resolve_to_the_highest_reading(
        self, client: AsyncClient, auth_headers, vehicle
    ):
        """The higher reading is entered first, so the newest row is the lower
        one: an odometer does not run backwards within a day, and the day's
        highest reading is the one a suggestion offers."""
        await _seed(
            client, auth_headers, vehicle, ("2026-04-10", "100010"), ("2026-04-10", "100000")
        )
        r = await _nearest(client, auth_headers, vehicle, "2026-04-10")
        assert r.json()["odometer_km"] == "100010.00" and r.json()["days_away"] == 0

    async def test_same_day_duplicates_after_the_date_resolve_to_the_highest_reading(
        self, client: AsyncClient, auth_headers, vehicle
    ):
        await _seed(
            client, auth_headers, vehicle, ("2026-04-20", "100610"), ("2026-04-20", "100600")
        )
        r = await _nearest(client, auth_headers, vehicle, "2026-04-18")
        assert r.json()["odometer_km"] == "100610.00" and r.json()["days_away"] == 2

    async def test_a_date_after_every_reading_returns_the_latest(
        self, client: AsyncClient, auth_headers, vehicle
    ):
        await _seed(
            client, auth_headers, vehicle, ("2026-01-01", "90000"), ("2026-04-01", "100000")
        )
        r = await _nearest(client, auth_headers, vehicle, "2026-09-01")
        assert r.json()["date"] == "2026-04-01" and r.json()["days_away"] == -153

    async def test_a_bad_date_is_422(self, client: AsyncClient, auth_headers, vehicle):
        r = await _nearest(client, auth_headers, vehicle, "yesterday")
        assert r.status_code == 422
