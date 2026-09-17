"""Integration tests for reminder pack list/apply endpoints."""

from datetime import date

import pytest
from dateutil.relativedelta import relativedelta
from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.asyncio
class TestReminderPacks:
    async def test_list_reminder_packs(self, client: AsyncClient, auth_headers):
        response = await client.get("/api/reminder-packs", headers=auth_headers)
        assert response.status_code == 200
        packs = response.json()
        assert isinstance(packs, list)
        assert len(packs) >= 3
        ids = {p["id"] for p in packs}
        assert {
            "oil_and_filter",
            "tire_rotation",
            "boat_winterization",
        }.issubset(ids)
        for pack in packs:
            assert pack["name"]
            assert pack["description"]
            assert pack["reminder_count"] >= 1

    async def test_apply_pack_uses_interval_as_absolute_without_odometer(
        self, client: AsyncClient, auth_headers
    ):
        # Dedicated VIN, not the shared `test_vehicle`: that fixture accumulates
        # odometer rows from other tests, which silently moves this into the
        # current+interval branch and made the assertion order-dependent.
        created_vehicle = await client.post(
            "/api/vehicles",
            headers=auth_headers,
            json={
                "vin": "1HGCM82633A004301",
                "nickname": "Pack Baseline None",
                "vehicle_type": "Car",
            },
        )
        assert created_vehicle.status_code == 201, created_vehicle.text
        vin = created_vehicle.json()["vin"]

        response = await client.post(
            f"/api/vehicles/{vin}/reminders/apply-pack",
            json={"pack_id": "oil_and_filter"},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        created = response.json()
        assert len(created) == 2
        titles = {r["title"] for r in created}
        assert titles == {"Oil & Filter Change", "Inspect Drain Plug Washer"}

        oil = next(r for r in created if r["title"] == "Oil & Filter Change")
        assert oil["status"] == "pending"
        # v3.5.0: a pack item is a RULE with intervals; the reminder counts
        # from an anchor. With nothing on record the anchor is a baseline
        # dated today, and 6 calendar months (not 180 days) is the pack's
        # calendar interval. No odometer reading exists, so the mileage
        # threshold cannot be anchored yet and the reminder is date-only;
        # the rule still carries the 8,000 km interval and the threshold
        # appears at the next reconcile once a reading exists.
        assert oil["reminder_type"] == "date"
        assert oil["due_date"] == (date.today() + relativedelta(months=6)).isoformat()
        assert oil["due_mileage_km"] is None
        assert oil["rule"]["interval_km"] is not None
        assert float(oil["rule"]["interval_km"]) == 8000.0
        assert oil["rule"]["interval_months"] == 6
        assert oil["anchor_kind"] == "baseline"
        assert oil["maintenance_type"] == "engine_oil_filter"

    async def test_apply_pack_adds_interval_to_current_odometer(
        self, client: AsyncClient, auth_headers
    ):
        created_vehicle = await client.post(
            "/api/vehicles",
            headers=auth_headers,
            json={
                "vin": "1HGCM82633A004302",
                "nickname": "Pack Baseline Odo",
                "vehicle_type": "Car",
            },
        )
        assert created_vehicle.status_code == 201, created_vehicle.text
        vin = created_vehicle.json()["vin"]

        # Fixed date, never a relative one: relative seed dates are calendar bombs.
        seeded = await client.post(
            f"/api/vehicles/{vin}/odometer",
            headers=auth_headers,
            json={"vin": vin, "date": "2027-03-04", "odometer_km": 50000},
        )
        assert seeded.status_code == 201, seeded.text

        response = await client.post(
            f"/api/vehicles/{vin}/reminders/apply-pack",
            json={"pack_id": "oil_and_filter"},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        oil = next(r for r in response.json() if r["title"] == "Oil & Filter Change")
        # Documented behaviour: pack mileage is an interval on top of the
        # baseline anchor, which is the current reading when nothing else is
        # on record.
        assert float(oil["due_mileage_km"]) == 58000.0
        assert oil["reminder_type"] == "smart"
        assert oil["anchor_kind"] == "baseline"
        assert float(oil["anchor_odometer_km"]) == 50000.0

    async def test_apply_boat_winterization_pack(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        vin = test_vehicle["vin"]
        response = await client.post(
            f"/api/vehicles/{vin}/reminders/apply-pack",
            json={"pack_id": "boat_winterization"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        created = response.json()
        assert len(created) == 4
        assert all(r["status"] == "pending" for r in created)
        assert all(r["due_date"] is not None for r in created)

    async def test_apply_unknown_pack_404(self, client: AsyncClient, auth_headers, test_vehicle):
        response = await client.post(
            f"/api/vehicles/{test_vehicle['vin']}/reminders/apply-pack",
            json={"pack_id": "does_not_exist"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_apply_path_traversal_pack_404(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        response = await client.post(
            f"/api/vehicles/{test_vehicle['vin']}/reminders/apply-pack",
            json={"pack_id": "../oil_and_filter"},
            headers=auth_headers,
        )
        assert response.status_code == 404
