"""
Integration tests for financing record routes.

Tests financing record CRUD operations and authorization (ADR 0001).
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.asyncio
class TestFinancingRoutes:
    """Test financing record API endpoints."""

    async def test_list_financing_records_empty(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        response = await client.get(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["financing_records"] == []
        assert data["total"] == 0

    async def test_create_financing_record(self, client: AsyncClient, auth_headers, test_vehicle):
        payload = {
            "vin": test_vehicle["vin"],
            "date": "2026-01-01",
            "amount": 450.00,
            "category": "lease_payment",
            "notes": "Monthly lease payment",
        }
        response = await client.post(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records",
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

    async def test_create_financing_record_rejects_invalid_category(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        payload = {
            "vin": test_vehicle["vin"],
            "date": "2026-01-01",
            "amount": 450.00,
            "category": "not_a_real_category",
        }
        response = await client.post(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 422

    async def test_get_financing_record_by_id(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        create_response = await client.post(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records",
            json={
                "vin": test_vehicle["vin"],
                "date": "2026-02-01",
                "amount": 300.00,
                "category": "loan_payment",
            },
            headers=auth_headers,
        )
        record = create_response.json()

        response = await client.get(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records/{record['id']}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == record["id"]
        assert data["category"] == "loan_payment"

    async def test_get_financing_record_not_found(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        response = await client.get(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records/999999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_update_financing_record(self, client: AsyncClient, auth_headers, test_vehicle):
        create_response = await client.post(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records",
            json={
                "vin": test_vehicle["vin"],
                "date": "2026-03-01",
                "amount": 1200.00,
                "category": "upfront_fee",
            },
            headers=auth_headers,
        )
        record = create_response.json()

        response = await client.put(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records/{record['id']}",
            json={"amount": 1300.00, "notes": "Corrected amount"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert float(data["amount"]) == 1300.00
        assert data["notes"] == "Corrected amount"
        assert data["category"] == "upfront_fee"

    async def test_delete_financing_record(self, client: AsyncClient, auth_headers, test_vehicle):
        create_response = await client.post(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records",
            json={
                "vin": test_vehicle["vin"],
                "date": "2026-04-01",
                "amount": 200.00,
                "category": "lease_payment",
            },
            headers=auth_headers,
        )
        record = create_response.json()

        response = await client.delete(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records/{record['id']}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        get_response = await client.get(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records/{record['id']}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    async def test_list_financing_records_unauthenticated(
        self, client: AsyncClient, test_vehicle
    ):
        response = await client.get(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records",
        )
        assert response.status_code == 401

    async def test_create_financing_record_non_owner_forbidden(
        self, client: AsyncClient, non_admin_headers, test_vehicle
    ):
        response = await client.post(
            f"/api/vehicles/{test_vehicle['vin']}/financing-records",
            json={
                "vin": test_vehicle["vin"],
                "date": "2026-01-01",
                "amount": 100.00,
                "category": "lease_payment",
            },
            headers=non_admin_headers,
        )
        assert response.status_code == 403
