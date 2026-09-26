"""Integration tests for financing record routes."""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Vehicle


async def _make_vehicle(db_session: AsyncSession, user_id: object, label: str) -> dict:
    """Create a vehicle with a unique VIN that no other test reads or writes."""
    vin = "FIN" + uuid.uuid4().hex[:14].upper()
    db_session.add(
        Vehicle(
            vin=vin,
            user_id=user_id,
            nickname=label,
            vehicle_type="Car",
            year=2020,
            make="Ford",
            model="Focus",
            fuel_type="gas",
        )
    )
    await db_session.commit()
    return {"vin": vin}


@pytest_asyncio.fixture
async def financing_vehicle(db_session: AsyncSession, test_user: dict[str, object]) -> dict:
    """A fresh vehicle owned by the test user, so record lists start empty."""
    return await _make_vehicle(db_session, test_user["id"], "Financing Route Vehicle")


@pytest_asyncio.fixture
async def other_financing_vehicle(db_session: AsyncSession, test_user: dict[str, object]) -> dict:
    """A second fresh vehicle owned by the same user, for cross-vehicle checks."""
    return await _make_vehicle(db_session, test_user["id"], "Other Financing Vehicle")


async def _create_record(client: AsyncClient, headers, vin: str) -> dict:
    response = await client.post(
        f"/api/vehicles/{vin}/financing-records",
        json={"vin": vin, "date": "2026-01-01", "amount": 100.00, "category": "loan_payment"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.integration
@pytest.mark.asyncio
class TestFinancingRoutes:
    """Test financing record API endpoints."""

    async def test_list_financing_records_empty(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        response = await client.get(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["financing_records"] == []
        assert data["total"] == 0

    async def test_create_financing_record(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        payload = {
            "vin": financing_vehicle["vin"],
            "date": "2026-01-01",
            "amount": 450.00,
            "category": "lease_payment",
            "notes": "Monthly lease payment",
        }
        response = await client.post(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["category"] == "lease_payment"
        assert data["amount"] == "450.00" or float(data["amount"]) == 450.00
        assert data["notes"] == "Monthly lease payment"
        assert "id" in data
        assert "created_at" in data
        assert data["lender"] is None

    async def test_create_financing_record_rejects_invalid_category(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        payload = {
            "vin": financing_vehicle["vin"],
            "date": "2026-01-01",
            "amount": 450.00,
            "category": "not_a_real_category",
        }
        response = await client.post(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 422

    async def test_get_financing_record_by_id(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        create_response = await client.post(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records",
            json={
                "vin": financing_vehicle["vin"],
                "date": "2026-02-01",
                "amount": 300.00,
                "category": "loan_payment",
            },
            headers=auth_headers,
        )
        record = create_response.json()

        response = await client.get(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records/{record['id']}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == record["id"]
        assert data["category"] == "loan_payment"

    async def test_get_financing_record_not_found(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        response = await client.get(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records/999999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_update_financing_record(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        create_response = await client.post(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records",
            json={
                "vin": financing_vehicle["vin"],
                "date": "2026-03-01",
                "amount": 1200.00,
                "category": "upfront_fee",
            },
            headers=auth_headers,
        )
        record = create_response.json()

        response = await client.put(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records/{record['id']}",
            json={"amount": 1300.00, "notes": "Corrected amount"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert float(data["amount"]) == 1300.00
        assert data["notes"] == "Corrected amount"
        assert data["category"] == "upfront_fee"

    async def test_delete_financing_record(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        create_response = await client.post(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records",
            json={
                "vin": financing_vehicle["vin"],
                "date": "2026-04-01",
                "amount": 200.00,
                "category": "lease_payment",
            },
            headers=auth_headers,
        )
        record = create_response.json()

        response = await client.delete(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records/{record['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        get_response = await client.get(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records/{record['id']}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    async def test_list_financing_records_unauthenticated(
        self, client: AsyncClient, financing_vehicle
    ):
        response = await client.get(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records",
        )
        assert response.status_code == 401

    async def test_create_financing_record_non_owner_forbidden(
        self, client: AsyncClient, non_admin_headers, financing_vehicle
    ):
        response = await client.post(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records",
            json={
                "vin": financing_vehicle["vin"],
                "date": "2026-01-01",
                "amount": 100.00,
                "category": "lease_payment",
            },
            headers=non_admin_headers,
        )
        assert response.status_code == 403

    async def test_list_financing_records_non_owner_forbidden(
        self, client: AsyncClient, auth_headers, non_admin_headers, financing_vehicle
    ):
        await _create_record(client, auth_headers, financing_vehicle["vin"])

        response = await client.get(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records",
            headers=non_admin_headers,
        )

        assert response.status_code == 403

    async def test_get_financing_record_non_owner_forbidden(
        self, client: AsyncClient, auth_headers, non_admin_headers, financing_vehicle
    ):
        record = await _create_record(client, auth_headers, financing_vehicle["vin"])

        response = await client.get(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records/{record['id']}",
            headers=non_admin_headers,
        )

        assert response.status_code == 403

    async def test_update_financing_record_non_owner_forbidden(
        self, client: AsyncClient, auth_headers, non_admin_headers, financing_vehicle
    ):
        vin = financing_vehicle["vin"]
        record = await _create_record(client, auth_headers, vin)

        response = await client.put(
            f"/api/vehicles/{vin}/financing-records/{record['id']}",
            json={"amount": 1.00},
            headers=non_admin_headers,
        )

        assert response.status_code == 403
        unchanged = await client.get(
            f"/api/vehicles/{vin}/financing-records/{record['id']}", headers=auth_headers
        )
        assert float(unchanged.json()["amount"]) == 100.00

    async def test_delete_financing_record_non_owner_forbidden(
        self, client: AsyncClient, auth_headers, non_admin_headers, financing_vehicle
    ):
        vin = financing_vehicle["vin"]
        record = await _create_record(client, auth_headers, vin)

        response = await client.delete(
            f"/api/vehicles/{vin}/financing-records/{record['id']}",
            headers=non_admin_headers,
        )

        assert response.status_code == 403
        still_there = await client.get(
            f"/api/vehicles/{vin}/financing-records/{record['id']}", headers=auth_headers
        )
        assert still_there.status_code == 200

    async def test_record_id_under_wrong_vehicle_returns_404(
        self, client: AsyncClient, auth_headers, financing_vehicle, other_financing_vehicle
    ):
        record = await _create_record(client, auth_headers, financing_vehicle["vin"])
        other_vin = other_financing_vehicle["vin"]
        url = f"/api/vehicles/{other_vin}/financing-records/{record['id']}"

        assert (await client.get(url, headers=auth_headers)).status_code == 404
        assert (
            await client.put(url, json={"amount": 1.00}, headers=auth_headers)
        ).status_code == 404
        assert (await client.delete(url, headers=auth_headers)).status_code == 404

        own = await client.get(
            f"/api/vehicles/{financing_vehicle['vin']}/financing-records/{record['id']}",
            headers=auth_headers,
        )
        assert own.status_code == 200
        assert float(own.json()["amount"]) == 100.00


@pytest.mark.integration
@pytest.mark.asyncio
class TestFinancingRecordLender:
    """The lender (vendor) is embedded in the response, not fetched separately."""

    async def test_create_and_get_include_lender(
        self, client: AsyncClient, auth_headers, financing_vehicle, db_session: AsyncSession
    ):
        from app.models.vendor import Vendor

        vendor = Vendor(name="Acme Auto Finance")
        db_session.add(vendor)
        await db_session.commit()

        vin = financing_vehicle["vin"]
        create_resp = await client.post(
            f"/api/vehicles/{vin}/financing-records",
            json={
                "vin": vin,
                "date": "2026-01-01",
                "amount": 450.00,
                "category": "lease_payment",
                "vendor_id": vendor.id,
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        created = create_resp.json()
        assert created["lender"] is not None
        assert created["lender"]["name"] == "Acme Auto Finance"

        get_resp = await client.get(
            f"/api/vehicles/{vin}/financing-records/{created['id']}", headers=auth_headers
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["lender"]["name"] == "Acme Auto Finance"

    async def test_list_includes_lender_only_where_set(
        self, client: AsyncClient, auth_headers, financing_vehicle, db_session: AsyncSession
    ):
        from app.models.vendor import Vendor

        vendor = Vendor(name="Community Credit Union")
        db_session.add(vendor)
        await db_session.commit()

        vin = financing_vehicle["vin"]
        await client.post(
            f"/api/vehicles/{vin}/financing-records",
            json={
                "vin": vin,
                "date": "2026-01-05",
                "amount": 200.00,
                "category": "loan_payment",
                "vendor_id": vendor.id,
            },
            headers=auth_headers,
        )
        await _create_record(client, auth_headers, vin)

        resp = await client.get(f"/api/vehicles/{vin}/financing-records", headers=auth_headers)
        assert resp.status_code == 200
        records = resp.json()["financing_records"]
        with_lender = [r for r in records if r["vendor_id"] == vendor.id]
        without_lender = [r for r in records if r["vendor_id"] is None]
        assert with_lender and with_lender[0]["lender"]["name"] == "Community Credit Union"
        assert without_lender and without_lender[0]["lender"] is None

    async def test_update_setting_vendor_id_populates_lender(
        self, client: AsyncClient, auth_headers, financing_vehicle, db_session: AsyncSession
    ):
        from app.models.vendor import Vendor

        vendor = Vendor(name="Lakeside Motors Finance")
        db_session.add(vendor)
        await db_session.commit()

        vin = financing_vehicle["vin"]
        record = await _create_record(client, auth_headers, vin)
        assert record["lender"] is None

        update_resp = await client.put(
            f"/api/vehicles/{vin}/financing-records/{record['id']}",
            json={"vendor_id": vendor.id},
            headers=auth_headers,
        )
        assert update_resp.status_code == 200, update_resp.text
        updated = update_resp.json()
        assert updated["lender"] is not None
        assert updated["lender"]["name"] == "Lakeside Motors Finance"
