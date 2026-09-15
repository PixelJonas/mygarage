"""A CSV import longer than about ten rows reaches the importer (#163).

The upload check rejected every export past roughly 1 KB with "Invalid CSV
format: Could not determine delimiter", before any importer ran.
"""

from __future__ import annotations

import uuid
from io import BytesIO

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, func, select

from app.models import FuelRecord
from app.models.vehicle import Vehicle

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def vehicle(db_session, test_user):
    """A vehicle for this test alone; its fuel records go with it."""
    vin = f"CSVBIG{uuid.uuid4().hex[:11].upper()}"
    db_session.add(
        Vehicle(vin=vin, user_id=test_user["id"], nickname="Large CSV", vehicle_type="Car")
    )
    await db_session.commit()
    yield vin
    await db_session.execute(delete(Vehicle).where(Vehicle.vin == vin))
    await db_session.commit()


async def test_a_fuel_export_of_twenty_rows_imports(
    client: AsyncClient, auth_headers, vehicle, db_session
):
    header = (
        "units_version,unit_system,Date,Filled At,Odometer (km),Engine Hours,Liters,"
        "Price Per Liter,Rebate,Total Cost,Full Tank,Missed Fill-up,Is Hauling,"
        "Fuel Type Used,Station ID,Station,Driver ID,Driver,Payment Method,Trip Type,"
        "Outside Temp (C),OBC L/100km,OBC Avg Speed (km/h),OBC Trip Duration (s),"
        "SOC Start (%),SOC End (%),Charge Level,Charge Location,Battery SOH (%),Notes"
    )
    # Odometers with two decimals, as the export writes them. Whether the old
    # check refused a file depended on which characters fell in its sample:
    # whole-number odometers at a "Shell" station happened to pass, as a
    # delimiter of "R".
    rows = [
        f"6,metric,2028-02-{i + 1:02d},,{140000 + i * 450:.2f},,38.2,1.05,,{40.11 + i:.2f},"
        "Yes,No,No,Regular,,Shell,,,,,,,,,,,,,,"
        for i in range(20)
    ]
    csv_content = "\n".join([header, *rows]) + "\n"
    assert len(csv_content) > 1024

    response = await client.post(
        f"/api/import/vehicles/{vehicle}/fuel/csv",
        headers=auth_headers,
        files={"file": ("fuel.csv", BytesIO(csv_content.encode()), "text/csv")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["success_count"] == 20, response.json()
    stored = (
        await db_session.execute(
            select(func.count()).select_from(FuelRecord).where(FuelRecord.vin == vehicle)
        )
    ).scalar_one()
    assert stored == 20
