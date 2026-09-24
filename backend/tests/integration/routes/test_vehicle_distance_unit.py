"""Per-vehicle distance unit (#172), end to end through the API.

The suite shares one database: every row here is created with a unique VIN and
deleted in `finally`.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vehicle import Vehicle

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _vin(prefix: str = "DU") -> str:
    return (prefix + uuid.uuid4().hex.upper())[:17]


async def _create(client: AsyncClient, headers: dict[str, str], vin: str, **extra: object) -> dict:
    body = {"vin": vin, "nickname": f"DU {vin[-4:]}", "vehicle_type": "Car"} | extra
    response = await client.post("/api/vehicles", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _drop(db: AsyncSession, vin: str) -> None:
    await db.rollback()
    await db.execute(delete(Vehicle).where(Vehicle.vin == vin))
    await db.commit()


class TestVehicleField:
    async def test_new_vehicles_start_on_account_default(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        vin = _vin()
        try:
            assert (await _create(client, auth_headers, vin))["distance_unit"] is None
        finally:
            await _drop(db_session, vin)

    async def test_set_then_clear_with_null(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        vin = _vin()
        try:
            await _create(client, auth_headers, vin)
            put = await client.put(
                f"/api/vehicles/{vin}", headers=auth_headers, json={"distance_unit": "mi"}
            )
            assert put.status_code == 200, put.text
            assert put.json()["distance_unit"] == "mi"
            # A partial update that omits the field leaves it alone.
            other = await client.put(
                f"/api/vehicles/{vin}", headers=auth_headers, json={"nickname": "Renamed"}
            )
            assert other.json()["distance_unit"] == "mi"
            cleared = await client.put(
                f"/api/vehicles/{vin}", headers=auth_headers, json={"distance_unit": None}
            )
            assert cleared.json()["distance_unit"] is None
        finally:
            await _drop(db_session, vin)

    @pytest.mark.parametrize("bad", ["MI", "miles", ""])
    async def test_a_bad_write_token_is_a_422(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        bad: str,
    ) -> None:
        vin = _vin()
        try:
            await _create(client, auth_headers, vin)
            put = await client.put(
                f"/api/vehicles/{vin}", headers=auth_headers, json={"distance_unit": bad}
            )
            assert put.status_code == 422, put.text
        finally:
            await _drop(db_session, vin)

    async def test_a_hand_stored_bad_value_is_served_as_null(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
    ) -> None:
        vin = _vin()
        try:
            await _create(client, auth_headers, vin)
            # Fits VARCHAR(2): PostgreSQL refuses a longer bad token before the
            # response path is ever exercised.
            await db_session.execute(
                update(Vehicle).where(Vehicle.vin == vin).values(distance_unit="MI")
            )
            await db_session.commit()
            db_session.expunge_all()
            got = await client.get(f"/api/vehicles/{vin}", headers=auth_headers)
            assert got.status_code == 200, got.text
            assert got.json()["distance_unit"] is None
        finally:
            await _drop(db_session, vin)
