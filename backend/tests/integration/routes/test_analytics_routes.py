"""
Integration tests for analytics routes.

Tests vehicle analytics, garage analytics, vendor analytics,
seasonal analytics, and period comparison endpoints.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Vehicle


@pytest_asyncio.fixture
async def financing_vehicle(db_session: AsyncSession, test_user: dict[str, object]) -> dict:
    """A vehicle no other test writes to, so monthly/rolling assertions are exact."""
    vin = "1FTFW1ET5EKE00001"
    vehicle = await db_session.get(Vehicle, vin)
    if vehicle is None:
        vehicle = Vehicle(
            vin=vin,
            user_id=test_user["id"],
            nickname="Financing Rollup Vehicle",
            vehicle_type="Car",
            year=2020,
            make="Ford",
            model="F-150",
            fuel_type="gas",
        )
        db_session.add(vehicle)
        await db_session.commit()
    return {"vin": vin, "name": "2020 Ford F-150"}


async def _add_financing(client, headers, vin, on, amount, category="lease_payment"):
    resp = await client.post(
        f"/api/vehicles/{vin}/financing-records",
        json={"vin": vin, "date": on, "amount": amount, "category": category},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.integration
@pytest.mark.asyncio
class TestVehicleAnalyticsRoutes:
    """Test per-vehicle analytics endpoints."""

    async def test_get_vehicle_analytics(self, client: AsyncClient, auth_headers, test_vehicle):
        """Vehicle analytics endpoint returns 200 with expected structure."""
        response = await client.get(
            f"/api/analytics/vehicles/{test_vehicle['vin']}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["vin"] == test_vehicle["vin"]
        assert "vehicle_name" in data
        assert "cost_analysis" in data
        assert "fuel_economy" in data
        assert "service_history" in data
        assert "predictions" in data

    async def test_get_vehicle_analytics_nonexistent_vin(self, client: AsyncClient, auth_headers):
        """Analytics for a nonexistent VIN returns 404."""
        response = await client.get(
            "/api/analytics/vehicles/00000000000000000",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_vehicle_analytics_unauthenticated(self, client: AsyncClient, test_vehicle):
        """Unauthenticated analytics request returns 401."""
        response = await client.get(
            f"/api/analytics/vehicles/{test_vehicle['vin']}",
        )

        assert response.status_code == 401

    async def test_get_vehicle_analytics_non_owner(
        self, client: AsyncClient, non_admin_headers, test_vehicle
    ):
        """Non-owner cannot access another user's vehicle analytics."""
        response = await client.get(
            f"/api/analytics/vehicles/{test_vehicle['vin']}",
            headers=non_admin_headers,
        )

        assert response.status_code == 403

    async def test_vehicle_analytics_includes_financing_cost(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        """Financing records must appear in CostAnalysis and count toward total_cost."""
        vin = test_vehicle["vin"]

        baseline = await client.get(f"/api/analytics/vehicles/{vin}", headers=auth_headers)
        baseline_total = float(baseline.json()["cost_analysis"]["total_cost"])

        create_resp = await client.post(
            f"/api/vehicles/{vin}/financing-records",
            json={
                "vin": vin,
                "date": "2026-01-01",
                "amount": 450.00,
                "category": "lease_payment",
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 201

        response = await client.get(f"/api/analytics/vehicles/{vin}", headers=auth_headers)
        assert response.status_code == 200
        cost_analysis = response.json()["cost_analysis"]

        assert float(cost_analysis["total_financing_cost"]) == 450.00
        assert float(cost_analysis["total_cost"]) == pytest.approx(baseline_total + 450.00)


@pytest.mark.integration
@pytest.mark.asyncio
class TestVehicleFinancingRollup:
    """Ticket #9: financing counts in every per-vehicle cost surface."""

    async def test_monthly_breakdown_includes_financing(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        vin = financing_vehicle["vin"]
        await _add_financing(client, auth_headers, vin, "2031-03-02", 1000.00, "upfront_fee")
        await _add_financing(client, auth_headers, vin, "2031-03-15", 450.00, "lease_payment")

        resp = await client.get(f"/api/analytics/vehicles/{vin}", headers=auth_headers)
        assert resp.status_code == 200
        ca = resp.json()["cost_analysis"]

        march = [m for m in ca["monthly_breakdown"] if (m["year"], m["month"]) == (2031, 3)]
        assert len(march) == 1
        # All financing categories (incl. upfront_fee) count, bucketed by record date
        assert float(march[0]["total_financing_cost"]) == 1450.00
        assert march[0]["financing_count"] == 2
        assert float(march[0]["total_cost"]) == 1450.00
        # Per-month figures agree with the headline total
        assert float(ca["total_cost"]) == pytest.approx(
            sum(float(m["total_cost"]) for m in ca["monthly_breakdown"])
        )

    async def test_average_rolling_and_trend_reflect_financing(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        vin = financing_vehicle["vin"]
        for on, amount in (("2032-01-10", 100.00), ("2032-02-10", 200.00), ("2032-03-10", 300.00)):
            await _add_financing(client, auth_headers, vin, on, amount)

        resp = await client.get(f"/api/analytics/vehicles/{vin}", headers=auth_headers)
        ca = resp.json()["cost_analysis"]

        assert float(ca["average_monthly_cost"]) == pytest.approx(
            float(ca["total_cost"]) / ca["months_tracked"]
        )
        # Last three months are the 100/200/300 payments -> mean 200
        assert float(ca["rolling_avg_3m"]) == pytest.approx(200.00)
        assert ca["trend_direction"] in {"increasing", "decreasing", "stable"}
        assert ca["monthly_breakdown"][-1]["year"] == 2032

    async def test_cost_per_km_includes_financing(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        vin = financing_vehicle["vin"]
        for on, km in (("2033-01-01", 1000.0), ("2033-02-01", 2000.0)):
            r = await client.post(
                f"/api/vehicles/{vin}/odometer",
                json={"vin": vin, "date": on, "odometer_km": km},
                headers=auth_headers,
            )
            assert r.status_code == 201, r.text
        await _add_financing(client, auth_headers, vin, "2033-01-15", 500.00)

        resp = await client.get(f"/api/analytics/vehicles/{vin}", headers=auth_headers)
        ca = resp.json()["cost_analysis"]

        assert ca["cost_per_km"] is not None
        # cost_per_km is derived from total_cost, which includes all financing
        km_driven = float(ca["total_cost"]) / float(ca["cost_per_km"])
        assert km_driven >= 1000.0
        assert float(ca["total_financing_cost"]) >= 500.00
        assert float(ca["cost_per_km"]) * km_driven == pytest.approx(float(ca["total_cost"]))


@pytest.mark.integration
@pytest.mark.asyncio
class TestGarageAnalyticsRoutes:
    """Test garage-level analytics endpoints."""

    async def test_get_garage_analytics(self, client: AsyncClient, auth_headers, test_vehicle):
        """Garage analytics returns 200 with expected structure."""
        response = await client.get(
            "/api/analytics/garage",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_costs" in data
        assert "cost_breakdown_by_category" in data
        assert "cost_by_vehicle" in data
        assert "monthly_trends" in data
        assert "vehicle_count" in data
        assert data["vehicle_count"] >= 1

    async def test_get_garage_analytics_unauthenticated(self, client: AsyncClient):
        """Unauthenticated garage analytics request returns 401."""
        response = await client.get("/api/analytics/garage")

        assert response.status_code == 401

    async def test_garage_analytics_includes_financing_total(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        """Financing records must roll up into GarageCostTotals.total_financing
        and appear as a "Financing" entry in cost_breakdown_by_category,
        (per-vehicle and monthly-trend rollups are covered by ticket #9 tests)."""
        vin = test_vehicle["vin"]

        create_resp = await client.post(
            f"/api/vehicles/{vin}/financing-records",
            json={
                "vin": vin,
                "date": "2026-01-01",
                "amount": 600.00,
                "category": "loan_payment",
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 201

        response = await client.get("/api/analytics/garage", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert float(data["total_costs"]["total_financing"]) >= 600.00

        financing_entries = [
            c for c in data["cost_breakdown_by_category"] if c["category"] == "Financing"
        ]
        assert len(financing_entries) == 1
        assert float(financing_entries[0]["amount"]) >= 600.00


@pytest.mark.integration
@pytest.mark.asyncio
class TestGarageFinancingRollup:
    """Ticket #9: financing counts in garage per-vehicle rows and monthly trends."""

    @staticmethod
    def _vehicle_row(data, vin):
        return next(v for v in data["cost_by_vehicle"] if v["vin"] == vin)

    async def test_cost_by_vehicle_includes_financing(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        vin = financing_vehicle["vin"]
        before = self._vehicle_row(
            (await client.get("/api/analytics/garage", headers=auth_headers)).json(), vin
        )

        await _add_financing(client, auth_headers, vin, "2034-01-05", 455.00, "lease_payment")
        await _add_financing(client, auth_headers, vin, "2034-01-01", 90.00, "upfront_fee")

        after = self._vehicle_row(
            (await client.get("/api/analytics/garage", headers=auth_headers)).json(), vin
        )
        assert float(after["total_financing"]) == pytest.approx(
            float(before["total_financing"]) + 545.00
        )
        # Row total includes every financing category and matches the sum of its parts
        assert float(after["total_cost"]) == pytest.approx(float(before["total_cost"]) + 545.00)
        parts = sum(
            float(after[k])
            for k in (
                "total_maintenance",
                "total_upgrades",
                "total_inspection",
                "total_collision",
                "total_detailing",
                "total_fuel",
                "total_def",
                "total_financing",
            )
        )
        assert float(after["total_cost"]) == pytest.approx(parts)

    async def test_monthly_trends_include_financing(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        vin = financing_vehicle["vin"]
        await _add_financing(client, auth_headers, vin, "2040-06-01", 400.00, "loan_payment")
        await _add_financing(client, auth_headers, vin, "2040-06-20", 100.00, "upfront_fee")

        data = (await client.get("/api/analytics/garage", headers=auth_headers)).json()

        june = [t for t in data["monthly_trends"] if t["month"] == "Jun 2040"]
        assert len(june) == 1
        assert float(june[0]["financing"]) == 500.00
        assert float(june[0]["total"]) == 500.00

    async def test_garage_rows_and_trends_agree_with_totals(
        self, client: AsyncClient, auth_headers, financing_vehicle
    ):
        """The headline total_financing equals the sum of per-vehicle financing."""
        vin = financing_vehicle["vin"]
        await _add_financing(client, auth_headers, vin, "2035-02-01", 250.00)

        data = (await client.get("/api/analytics/garage", headers=auth_headers)).json()

        assert float(data["total_costs"]["total_financing"]) == pytest.approx(
            sum(float(v["total_financing"]) for v in data["cost_by_vehicle"])
        )


@pytest.mark.integration
@pytest.mark.asyncio
class TestVendorAnalyticsRoutes:
    """Test vendor analytics endpoint."""

    async def test_get_vendor_analytics(self, client: AsyncClient, auth_headers, test_vehicle):
        """Vendor analytics returns 200 with expected structure."""
        response = await client.get(
            f"/api/analytics/vehicles/{test_vehicle['vin']}/vendors",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "vendors" in data
        assert "total_vendors" in data
        assert isinstance(data["vendors"], list)

    async def test_get_vendor_analytics_nonexistent_vin(self, client: AsyncClient, auth_headers):
        """Vendor analytics for a nonexistent VIN returns 404."""
        response = await client.get(
            "/api/analytics/vehicles/00000000000000000/vendors",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_vendor_analytics_non_owner(
        self, client: AsyncClient, non_admin_headers, test_vehicle
    ):
        """Non-owner cannot access vendor analytics for another user's vehicle."""
        response = await client.get(
            f"/api/analytics/vehicles/{test_vehicle['vin']}/vendors",
            headers=non_admin_headers,
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestSeasonalAnalyticsRoutes:
    """Test seasonal analytics endpoint."""

    async def test_get_seasonal_analytics(self, client: AsyncClient, auth_headers, test_vehicle):
        """Seasonal analytics returns 200 with expected structure."""
        response = await client.get(
            f"/api/analytics/vehicles/{test_vehicle['vin']}/seasonal",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "seasons" in data
        assert isinstance(data["seasons"], list)

    async def test_get_seasonal_analytics_nonexistent_vin(self, client: AsyncClient, auth_headers):
        """Seasonal analytics for a nonexistent VIN returns 404."""
        response = await client.get(
            "/api/analytics/vehicles/00000000000000000/seasonal",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_get_seasonal_analytics_non_owner(
        self, client: AsyncClient, non_admin_headers, test_vehicle
    ):
        """Non-owner cannot access seasonal analytics for another user's vehicle."""
        response = await client.get(
            f"/api/analytics/vehicles/{test_vehicle['vin']}/seasonal",
            headers=non_admin_headers,
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestPeriodComparisonRoutes:
    """Test period comparison endpoint."""

    async def test_compare_periods(self, client: AsyncClient, auth_headers, test_vehicle):
        """Period comparison returns 200 with expected structure."""
        params = {
            "period1_start": "2025-01-01",
            "period1_end": "2025-06-30",
            "period2_start": "2025-07-01",
            "period2_end": "2025-12-31",
        }
        response = await client.get(
            f"/api/analytics/vehicles/{test_vehicle['vin']}/compare",
            params=params,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "period1_label" in data
        assert "period2_label" in data
        assert "period1_total_cost" in data
        assert "period2_total_cost" in data
        assert "cost_change_amount" in data
        assert "category_changes" in data

    async def test_compare_periods_with_labels(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        """Period comparison with custom labels uses supplied labels."""
        params = {
            "period1_start": "2025-01-01",
            "period1_end": "2025-06-30",
            "period2_start": "2025-07-01",
            "period2_end": "2025-12-31",
            "period1_label": "H1 2025",
            "period2_label": "H2 2025",
        }
        response = await client.get(
            f"/api/analytics/vehicles/{test_vehicle['vin']}/compare",
            params=params,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["period1_label"] == "H1 2025"
        assert data["period2_label"] == "H2 2025"

    async def test_compare_periods_nonexistent_vin(self, client: AsyncClient, auth_headers):
        """Period comparison for a nonexistent VIN returns 404."""
        params = {
            "period1_start": "2025-01-01",
            "period1_end": "2025-06-30",
            "period2_start": "2025-07-01",
            "period2_end": "2025-12-31",
        }
        response = await client.get(
            "/api/analytics/vehicles/00000000000000000/compare",
            params=params,
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_compare_periods_missing_params(
        self, client: AsyncClient, auth_headers, test_vehicle
    ):
        """Period comparison without required date params returns 422."""
        response = await client.get(
            f"/api/analytics/vehicles/{test_vehicle['vin']}/compare",
            headers=auth_headers,
        )

        assert response.status_code == 422

    async def test_compare_periods_non_owner(
        self, client: AsyncClient, non_admin_headers, test_vehicle
    ):
        """Non-owner cannot compare periods for another user's vehicle."""
        params = {
            "period1_start": "2025-01-01",
            "period1_end": "2025-06-30",
            "period2_start": "2025-07-01",
            "period2_end": "2025-12-31",
        }
        response = await client.get(
            f"/api/analytics/vehicles/{test_vehicle['vin']}/compare",
            params=params,
            headers=non_admin_headers,
        )

        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
class TestAnalyticsDefConsistency:
    """The Analytics page and the DEF tab must agree on DEF consumption.

    The analytics route previously carried its own DEF formula (all purchase
    liters over the odometer span of ALL records, min 2 points) and asserted
    a rate on data the DEF endpoint judged insufficient. Both now go through
    DEFRecordService.get_def_analytics.
    """

    async def test_def_rate_matches_def_endpoint_verdict(
        self, client: AsyncClient, auth_headers, test_vehicle, db_session
    ):
        from datetime import date
        from decimal import Decimal

        from sqlalchemy import delete

        from app.models.def_record import DEFRecord

        vin = test_vehicle["vin"]
        await db_session.execute(delete(DEFRecord).where(DEFRecord.vin == vin))
        # 2 purchases with odometer+liters + 3 odometer-only observations:
        # exactly the production shape that produced a phantom 2.7 gal/1,000 mi.
        db_session.add_all(
            [
                DEFRecord(
                    vin=vin,
                    date=date(2026, 2, 11),
                    odometer_km=Decimal("7898.64"),
                    liters=Decimal("9.464"),
                    cost=Decimal("22.60"),
                    entry_type="purchase",
                ),
                DEFRecord(
                    vin=vin,
                    date=date(2026, 2, 13),
                    odometer_km=Decimal("7958.19"),
                    liters=Decimal("9.464"),
                    cost=Decimal("22.60"),
                    entry_type="purchase",
                ),
                DEFRecord(
                    vin=vin,
                    date=date(2026, 3, 17),
                    odometer_km=Decimal("9144.27"),
                    fill_level=Decimal("0.85"),
                    entry_type="auto_fuel_sync",
                ),
                DEFRecord(
                    vin=vin,
                    date=date(2026, 5, 5),
                    odometer_km=Decimal("9968.25"),
                    fill_level=Decimal("0.75"),
                    entry_type="auto_fuel_sync",
                ),
                DEFRecord(
                    vin=vin,
                    date=date(2026, 6, 30),
                    odometer_km=Decimal("10845.34"),
                    fill_level=Decimal("0.75"),
                    entry_type="auto_fuel_sync",
                ),
            ]
        )
        await db_session.commit()

        response = await client.get(f"/api/analytics/vehicles/{vin}", headers=auth_headers)
        assert response.status_code == 200
        def_analysis = response.json()["def_analysis"]
        assert def_analysis is not None
        assert def_analysis["record_count"] == 5
        # Only 2 records carry odometer+liters -> below the 3-record minimum:
        # no consumption rate may be asserted (parity with the DEF tab).
        assert def_analysis["liters_per_1000_km"] is None, (
            "analytics page asserted a DEF rate the DEF endpoint judges "
            "insufficient - duplicate formula is back"
        )
        assert def_analysis["data_confidence"] == "insufficient"

        await db_session.execute(delete(DEFRecord).where(DEFRecord.vin == vin))
        await db_session.commit()
