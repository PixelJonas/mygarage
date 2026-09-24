"""
Integration tests for vehicle routes.

Tests vehicle CRUD operations, access control, and archive workflows.
"""

from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HoursRecord


@pytest.mark.integration
@pytest.mark.vehicle
@pytest.mark.asyncio
class TestVehicleRoutes:
    """Test vehicle API endpoints."""

    async def test_list_vehicles(self, client: AsyncClient, auth_headers, test_vehicle):
        """Test listing user's vehicles.

        ★ `limit=500`, the route's maximum, is load-bearing. The default page is
        100, the list is ordered newest-first, and this session-scoped database
        accumulates vehicles from every test file that runs before this one. On
        the default page the assertion below stops being about scoping and starts
        being about how many vehicles happen to exist, which is what broke it: it
        passed on SQLite and failed under PostgreSQL purely on ordering.
        """
        response = await client.get("/api/vehicles?limit=500", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        # API returns {"vehicles": [...], "total": N}
        assert "vehicles" in data
        assert "total" in data
        assert isinstance(data["vehicles"], list)
        assert len(data["vehicles"]) >= 1
        # Should include our test vehicle (identified by VIN, not id)
        vehicle_vins = [v["vin"] for v in data["vehicles"]]
        assert test_vehicle["vin"] in vehicle_vins

    async def test_get_vehicle_by_vin(self, client: AsyncClient, auth_headers, test_vehicle):
        """Test retrieving a specific vehicle by VIN."""
        response = await client.get(
            f"/api/vehicles/{test_vehicle['vin']}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["vin"] == test_vehicle["vin"]
        assert data["year"] == test_vehicle["year"]
        assert data["make"] == test_vehicle["make"]

    async def test_create_vehicle(self, client: AsyncClient, auth_headers, sample_vehicle_payload):
        """Test creating a new vehicle."""
        response = await client.post(
            "/api/vehicles",
            json=sample_vehicle_payload,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["vin"] == sample_vehicle_payload["vin"]
        assert data["year"] == sample_vehicle_payload["year"]
        assert data["nickname"] == sample_vehicle_payload["nickname"]

    async def test_update_vehicle(self, client: AsyncClient, auth_headers, test_vehicle):
        """Test updating a vehicle."""
        update_data = {
            "license_plate": "UPDATED-123",
        }

        response = await client.put(
            f"/api/vehicles/{test_vehicle['vin']}",
            json=update_data,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["license_plate"] == "UPDATED-123"

    async def test_update_vehicle_persists_equipment(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        """Standard/optional equipment must be editable via a partial PUT.

        The fields live on VehicleResponse; unless VehicleUpdate also declares
        them, Pydantic's default extra='ignore' silently drops the keys and the
        save is a no-op (the vehicle-detail equipment sidecar regression).
        """
        response = await client.put(
            f"/api/vehicles/{test_vehicle['vin']}",
            json={
                "standard_equipment": {"items": ["ABS", "Airbags"]},
                "optional_equipment": {"Comfort": ["Sunroof"]},
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["standard_equipment"] == {"items": ["ABS", "Airbags"]}
        assert data["optional_equipment"] == {"Comfort": ["Sunroof"]}

    async def test_update_vehicle_persists_pricing(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        """Purchase/sale fields (VehicleBase) and MSRP fields (added to
        VehicleUpdate for the pricing sidecar) all persist via a partial PUT.
        The MSRP fields otherwise live only on VehicleResponse and would be
        silently dropped by extra='ignore'.
        """
        response = await client.put(
            f"/api/vehicles/{test_vehicle['vin']}",
            json={
                "purchase_date": "2019-03-15",
                "purchase_price": "15000.00",
                "sold_date": "2024-06-01",
                "sold_price": "9500.00",
                "msrp_base": "40000.00",
                "msrp_options": "2500.00",
                "destination_charge": "1595.00",
                "msrp_total": "44095.00",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["purchase_date"] == "2019-03-15"
        assert float(data["purchase_price"]) == 15000.00
        assert float(data["sold_price"]) == 9500.00
        assert float(data["msrp_base"]) == 40000.00
        assert float(data["destination_charge"]) == 1595.00
        assert float(data["msrp_total"]) == 44095.00

    async def test_update_vehicle_persists_descriptive_specs(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        """Colors, wheel/tire specs, warranty, and window-sticker engine/
        transmission descriptions are editable from the vehicle-detail card
        sidecars. Like equipment/MSRP they live only on VehicleResponse, so
        VehicleUpdate must declare them or extra='ignore' drops the save.
        """
        response = await client.put(
            f"/api/vehicles/{test_vehicle['vin']}",
            json={
                "exterior_color": "Cherry Red",
                "interior_color": "Black",
                "wheel_specs": '18" Alloy',
                "tire_specs": "245/45R18",
                "warranty_basic": "3 yr / 36,000 mi",
                "warranty_powertrain": "5 yr / 60,000 mi",
                "sticker_engine_description": "2.0L Turbo I4",
                "sticker_transmission_description": "8-Speed Automatic",
                "sticker_drivetrain": "AWD",
                "assembly_location": "Toyota City, Japan",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["assembly_location"] == "Toyota City, Japan"
        assert data["exterior_color"] == "Cherry Red"
        assert data["interior_color"] == "Black"
        assert data["wheel_specs"] == '18" Alloy'
        assert data["tire_specs"] == "245/45R18"
        assert data["warranty_basic"] == "3 yr / 36,000 mi"
        assert data["warranty_powertrain"] == "5 yr / 60,000 mi"
        assert data["sticker_engine_description"] == "2.0L Turbo I4"
        assert data["sticker_transmission_description"] == "8-Speed Automatic"
        assert data["sticker_drivetrain"] == "AWD"

    async def test_create_vehicle_defaults_usage_unit_to_distance(
        self, client: AsyncClient, auth_headers, sample_vehicle_payload
    ):
        """A vehicle created without usage_unit defaults to distance tracking."""
        payload = {**sample_vehicle_payload, "vin": "1HGCM82633A100001"}
        response = await client.post("/api/vehicles", json=payload, headers=auth_headers)
        assert response.status_code == 201
        assert response.json()["usage_unit"] == "distance"

    async def test_create_and_update_hours_tracking_writes_manual_hours_row(
        self,
        client: AsyncClient,
        auth_headers,
        sample_vehicle_payload,
        db_session: AsyncSession,
    ):
        """R2-H1: current_hours is retired as a source-of-truth column write.
        A submitted current_hours on create/update upserts TODAY's manual
        hours_records row instead — and latest_hours (never
        vehicle.current_hours) is what detail-stats displays. A repeated
        same-day PUT updates the SAME row, never a second one."""
        vin = "1HGCM82633A100002"
        payload = {
            **sample_vehicle_payload,
            "vin": vin,
            "usage_unit": "hours",
            "current_hours": 123.5,
        }
        resp = await client.post("/api/vehicles", json=payload, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["usage_unit"] == "hours"

        today = date.today()

        async def _manual_rows() -> list[HoursRecord]:
            result = await db_session.execute(
                select(HoursRecord).where(
                    HoursRecord.vin == vin,
                    HoursRecord.source == "manual",
                    HoursRecord.date == today,
                )
            )
            return list(result.scalars().all())

        rows = await _manual_rows()
        assert len(rows) == 1
        assert rows[0].engine_hours == Decimal("123.5")
        first_row_id = rows[0].id

        detail = (
            await client.get(f"/api/vehicles/{vin}/detail-stats", headers=auth_headers)
        ).json()
        assert detail["latest_hours"] == "123.5"

        # Same-day PUT: must update the SAME manual row, never create a second.
        upd = await client.put(
            f"/api/vehicles/{vin}",
            json={"current_hours": 200.0},
            headers=auth_headers,
        )
        assert upd.status_code == 200

        rows_after = await _manual_rows()
        assert len(rows_after) == 1, "same-day update must not proliferate manual rows"
        assert rows_after[0].id == first_row_id
        assert rows_after[0].engine_hours == Decimal("200.0")

        detail_after = (
            await client.get(f"/api/vehicles/{vin}/detail-stats", headers=auth_headers)
        ).json()
        assert detail_after["latest_hours"] == "200.0"

        # A third same-day PUT still updates the ONE row.
        upd2 = await client.put(
            f"/api/vehicles/{vin}",
            json={"current_hours": 210.3},
            headers=auth_headers,
        )
        assert upd2.status_code == 200
        rows_final = await _manual_rows()
        assert len(rows_final) == 1
        assert rows_final[0].id == first_row_id
        assert rows_final[0].engine_hours == Decimal("210.3")

    async def test_omitted_current_hours_on_update_does_not_write_a_row(
        self, client: AsyncClient, auth_headers, sample_vehicle_payload, db_session: AsyncSession
    ):
        """exclude_unset semantics: a PUT that never mentions current_hours
        must not touch hours_records at all."""
        vin = "1HGCM82633A100011"
        payload = {**sample_vehicle_payload, "vin": vin, "usage_unit": "hours"}
        resp = await client.post("/api/vehicles", json=payload, headers=auth_headers)
        assert resp.status_code == 201

        upd = await client.put(
            f"/api/vehicles/{vin}",
            json={"license_plate": "NOHOURS-1"},
            headers=auth_headers,
        )
        assert upd.status_code == 200

        rows = (
            (await db_session.execute(select(HoursRecord).where(HoursRecord.vin == vin)))
            .scalars()
            .all()
        )
        assert rows == []

    async def test_create_vehicle_rejects_bad_usage_unit(
        self, client: AsyncClient, auth_headers, sample_vehicle_payload
    ):
        """usage_unit outside {distance, hours} is rejected (422)."""
        payload = {**sample_vehicle_payload, "vin": "1HGCM82633A100003", "usage_unit": "lightyears"}
        resp = await client.post("/api/vehicles", json=payload, headers=auth_headers)
        assert resp.status_code == 422

    async def test_create_vehicle_persists_secondary_usage_enabled(
        self, client: AsyncClient, auth_headers, sample_vehicle_payload
    ):
        """secondary_usage_enabled=true on create must persist. `VehicleBase`
        was missing this field entirely, so Pydantic's `extra="ignore"` was
        silently dropping it on POST -> the "also track hours" toggle was a
        no-op. Regression guard for that gap."""
        vin = "1HGCM82633A100004"
        payload = {**sample_vehicle_payload, "vin": vin, "secondary_usage_enabled": True}
        resp = await client.post("/api/vehicles", json=payload, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["secondary_usage_enabled"] is True

        get_resp = await client.get(f"/api/vehicles/{vin}", headers=auth_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["secondary_usage_enabled"] is True

    async def test_update_vehicle_toggles_secondary_usage_enabled(
        self, client: AsyncClient, auth_headers, sample_vehicle_payload
    ):
        """A PUT toggling secondary_usage_enabled true -> false must persist
        the new value (same VehicleBase gap: VehicleUpdate silently dropped
        it too)."""
        vin = "1HGCM82633A100005"
        payload = {**sample_vehicle_payload, "vin": vin, "secondary_usage_enabled": True}
        resp = await client.post("/api/vehicles", json=payload, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["secondary_usage_enabled"] is True

        upd = await client.put(
            f"/api/vehicles/{vin}",
            json={"secondary_usage_enabled": False},
            headers=auth_headers,
        )
        assert upd.status_code == 200
        assert upd.json()["secondary_usage_enabled"] is False

        get_resp = await client.get(f"/api/vehicles/{vin}", headers=auth_headers)
        assert get_resp.json()["secondary_usage_enabled"] is False

    async def test_omitted_secondary_usage_enabled_on_update_leaves_it_unchanged(
        self, client: AsyncClient, auth_headers, sample_vehicle_payload
    ):
        """exclude_unset semantics: a PUT that never mentions
        secondary_usage_enabled must not reset it to the schema default."""
        vin = "1HGCM82633A100006"
        payload = {**sample_vehicle_payload, "vin": vin, "secondary_usage_enabled": True}
        resp = await client.post("/api/vehicles", json=payload, headers=auth_headers)
        assert resp.status_code == 201

        upd = await client.put(
            f"/api/vehicles/{vin}",
            json={"license_plate": "SECONDARY-1"},
            headers=auth_headers,
        )
        assert upd.status_code == 200
        assert upd.json()["secondary_usage_enabled"] is True

    async def test_delete_vehicle(self, client: AsyncClient, auth_headers, test_user, db_session):
        """Test deleting a vehicle."""
        from app.models.vehicle import Vehicle

        # Create a vehicle specifically for deletion. Pull user_id from
        # the test_user fixture instead of hardcoding 1 — PG enforces
        # FKs strictly and the auto-assigned id may not be 1.
        delete_vehicle = Vehicle(
            vin="1HGCM82633A999999",
            user_id=test_user["id"],
            nickname="Delete Test Vehicle",
            vehicle_type="Car",
            year=2020,
            make="Test",
            model="Delete",
        )
        db_session.add(delete_vehicle)
        await db_session.commit()

        response = await client.delete(
            f"/api/vehicles/{delete_vehicle.vin}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await client.get(
            f"/api/vehicles/{delete_vehicle.vin}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    async def test_get_vehicle_unauthorized(self, client: AsyncClient, test_vehicle):
        """Test that unauthenticated users cannot access vehicles."""
        response = await client.get(f"/api/vehicles/{test_vehicle['vin']}")

        assert response.status_code == 401

    async def test_create_vehicle_invalid_vin(self, client: AsyncClient, auth_headers):
        """Test that invalid VINs are rejected."""
        invalid_payload = {
            "vin": "INVALID",  # Too short (must be 17 chars)
            "nickname": "Test Vehicle",
            "vehicle_type": "Car",
            "year": 2023,
            "make": "Test",
            "model": "Car",
        }

        response = await client.post(
            "/api/vehicles",
            json=invalid_payload,
            headers=auth_headers,
        )

        assert response.status_code == 422  # Validation error


@pytest.mark.integration
@pytest.mark.vehicle
@pytest.mark.asyncio
class TestVehicleArchiveRoutes:
    """Test vehicle archive/unarchive/visibility endpoints."""

    async def _create_archivable_vehicle(self, db_session, user_id: int, vin: str) -> None:
        """Helper: create a fresh vehicle for archive tests."""

        from app.models.vehicle import Vehicle

        result = await db_session.execute(select(Vehicle).where(Vehicle.vin == vin))
        existing = result.scalar_one_or_none()
        if existing:
            await db_session.delete(existing)
            await db_session.commit()

        vehicle = Vehicle(
            vin=vin,
            user_id=user_id,
            nickname="Archive Test Vehicle",
            vehicle_type="Car",
            year=2021,
            make="Toyota",
            model="Camry",
        )
        db_session.add(vehicle)
        await db_session.commit()

    async def test_archive_vehicle(self, client: AsyncClient, auth_headers, db_session, test_user):
        """Archive a vehicle and verify archived_at is set."""
        vin = "1HGCM82633A888801"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        archive_payload = {"reason": "Sold"}
        response = await client.post(
            f"/api/vehicles/{vin}/archive",
            json=archive_payload,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["archived_at"] is not None
        assert data["archive_reason"] == "Sold"
        assert data["archived_visible"] is True  # default

    async def test_archive_vehicle_with_sale_data(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """Archive with reason, sale price, sale date, and notes."""
        vin = "1HGCM82633A888802"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        archive_payload = {
            "reason": "Sold",
            "sale_price": 25000.00,
            "sale_date": "2026-01-15",
            "notes": "Sold to private buyer",
            "visible": False,
        }
        response = await client.post(
            f"/api/vehicles/{vin}/archive",
            json=archive_payload,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["archived_at"] is not None
        assert data["archive_reason"] == "Sold"
        assert float(data["archive_sale_price"]) == 25000.00
        assert data["archive_sale_date"] == "2026-01-15"
        assert data["archive_notes"] == "Sold to private buyer"
        assert data["archived_visible"] is False

    async def test_archive_vehicle_nonexistent_vin(self, client: AsyncClient, auth_headers):
        """Archive a vehicle that does not exist returns 404."""
        response = await client.post(
            "/api/vehicles/00000000000000000/archive",
            json={"reason": "Sold"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_archive_already_archived_vehicle(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """Archiving an already-archived vehicle overwrites the archive metadata."""
        vin = "1HGCM82633A888803"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        # Archive first time
        response1 = await client.post(
            f"/api/vehicles/{vin}/archive",
            json={"reason": "Sold", "notes": "First archive"},
            headers=auth_headers,
        )
        assert response1.status_code == 200

        # Archive again with different data
        response2 = await client.post(
            f"/api/vehicles/{vin}/archive",
            json={"reason": "Trade-in", "notes": "Changed mind"},
            headers=auth_headers,
        )
        assert response2.status_code == 200
        data = response2.json()
        assert data["archive_reason"] == "Trade-in"
        assert data["archive_notes"] == "Changed mind"

    async def test_archive_vehicle_non_owner_forbidden(
        self, client: AsyncClient, non_admin_headers, db_session, test_user
    ):
        """Non-owner attempting to archive another user's vehicle gets 403."""
        vin = "1HGCM82633A888804"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        response = await client.post(
            f"/api/vehicles/{vin}/archive",
            json={"reason": "Sold"},
            headers=non_admin_headers,
        )

        assert response.status_code == 403

    async def test_list_archived_vehicles(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """Archived vehicles appear in the archived list."""
        vin = "1HGCM82633A888805"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        # Archive it
        await client.post(
            f"/api/vehicles/{vin}/archive",
            json={"reason": "Totaled"},
            headers=auth_headers,
        )

        # Fetch archived list
        response = await client.get(
            "/api/vehicles/archived/list",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "vehicles" in data
        assert "total" in data
        archived_vins = [v["vin"] for v in data["vehicles"]]
        assert vin in archived_vins

    async def test_unarchive_vehicle(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """Unarchiving clears all archive fields."""
        vin = "1HGCM82633A888806"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        # Archive first
        await client.post(
            f"/api/vehicles/{vin}/archive",
            json={"reason": "Gifted", "notes": "Gave to sibling"},
            headers=auth_headers,
        )

        # Unarchive
        response = await client.post(
            f"/api/vehicles/{vin}/unarchive",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["archived_at"] is None
        assert data["archive_reason"] is None
        assert data["archive_sale_price"] is None
        assert data["archive_sale_date"] is None
        assert data["archive_notes"] is None
        assert data["archived_visible"] is True

    async def test_unarchive_non_archived_vehicle(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """Unarchiving a vehicle that is not archived returns 400."""
        vin = "1HGCM82633A888807"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        response = await client.post(
            f"/api/vehicles/{vin}/unarchive",
            headers=auth_headers,
        )

        assert response.status_code == 400

    async def test_unarchive_nonexistent_vin(self, client: AsyncClient, auth_headers):
        """Unarchiving a nonexistent vehicle returns 404."""
        response = await client.post(
            "/api/vehicles/00000000000000000/unarchive",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_unarchive_vehicle_non_owner_forbidden(
        self, client: AsyncClient, non_admin_headers, auth_headers, db_session, test_user
    ):
        """Non-owner cannot unarchive another user's vehicle."""
        vin = "1HGCM82633A888808"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        # Archive as owner
        await client.post(
            f"/api/vehicles/{vin}/archive",
            json={"reason": "Sold"},
            headers=auth_headers,
        )

        # Attempt unarchive as non-owner
        response = await client.post(
            f"/api/vehicles/{vin}/unarchive",
            headers=non_admin_headers,
        )

        assert response.status_code == 403

    async def test_toggle_archive_visibility_hidden(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """Toggle archived vehicle visibility to hidden."""
        vin = "1HGCM82633A888809"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        # Archive first
        await client.post(
            f"/api/vehicles/{vin}/archive",
            json={"reason": "Sold"},
            headers=auth_headers,
        )

        # Set visibility to false
        response = await client.patch(
            f"/api/vehicles/{vin}/archive/visibility",
            params={"visible": False},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["archived_visible"] is False

    async def test_toggle_archive_visibility_visible(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """Toggle archived vehicle visibility back to visible."""
        vin = "1HGCM82633A888810"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        # Archive with visible=False
        await client.post(
            f"/api/vehicles/{vin}/archive",
            json={"reason": "Sold", "visible": False},
            headers=auth_headers,
        )

        # Set visibility to true
        response = await client.patch(
            f"/api/vehicles/{vin}/archive/visibility",
            params={"visible": True},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["archived_visible"] is True

    async def test_toggle_visibility_non_archived_vehicle(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """Toggling visibility on a non-archived vehicle returns 400."""
        vin = "1HGCM82633A888811"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        response = await client.patch(
            f"/api/vehicles/{vin}/archive/visibility",
            params={"visible": False},
            headers=auth_headers,
        )

        assert response.status_code == 400

    async def test_toggle_visibility_nonexistent_vin(self, client: AsyncClient, auth_headers):
        """Toggling visibility on a nonexistent vehicle returns 404."""
        response = await client.patch(
            "/api/vehicles/00000000000000000/archive/visibility",
            params={"visible": False},
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_toggle_visibility_non_owner_forbidden(
        self, client: AsyncClient, non_admin_headers, auth_headers, db_session, test_user
    ):
        """Non-owner cannot toggle archive visibility on another user's vehicle."""
        vin = "1HGCM82633A888812"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        # Archive as owner
        await client.post(
            f"/api/vehicles/{vin}/archive",
            json={"reason": "Sold"},
            headers=auth_headers,
        )

        # Attempt visibility toggle as non-owner
        response = await client.patch(
            f"/api/vehicles/{vin}/archive/visibility",
            params={"visible": False},
            headers=non_admin_headers,
        )

        assert response.status_code == 403

    async def test_archive_invalid_reason(
        self, client: AsyncClient, auth_headers, db_session, test_user
    ):
        """Archive with an invalid reason is rejected with 422."""
        vin = "1HGCM82633A888813"
        await self._create_archivable_vehicle(db_session, test_user["id"], vin)

        response = await client.post(
            f"/api/vehicles/{vin}/archive",
            json={"reason": "Stolen"},  # Not in valid reasons list
            headers=auth_headers,
        )

        assert response.status_code == 422
