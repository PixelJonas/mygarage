"""The chart picker's parameter list is scoped to one vehicle.

`/api/livelink/parameters` is the fleet-wide catalog: every parameter any
device has ever sent. The charts tab read it, auto-selected the first three
and drew "No data available for the selected time range" on a propane trailer
whose only parameters were tank levels, because the three it picked were
engine PIDs belonging to somebody else's car.
"""

import itertools
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.livelink_parameter import LiveLinkParameter
from app.models.vehicle_telemetry import VehicleTelemetryLatest
from app.utils.datetime_utils import utc_now

_SEQ = itertools.count()

BASE = "/api/vehicles/{vin}/livelink/parameters"


async def _param(db_session: AsyncSession, key: str) -> None:
    """Register a parameter in the global catalog."""
    db_session.add(LiveLinkParameter(param_key=key, display_name=key, unit=None))


async def _reported(db_session: AsyncSession, vin: str, key: str, *, age_days: int = 0) -> None:
    """Record that this vin has reported this parameter."""
    db_session.add(
        VehicleTelemetryLatest(
            vin=vin,
            param_key=key,
            value=1.0,
            timestamp=utc_now() - timedelta(days=age_days),
        )
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lists_only_what_this_vehicle_reports(
    client: AsyncClient, auth_headers, test_vehicle, db_session: AsyncSession
):
    """A parameter in the catalog that this vin never sent must not be offered."""
    vin = test_vehicle["vin"]
    n = next(_SEQ)
    mine, theirs = f"PROPANE_T1_LEVEL_PCT_{n}", f"ENGINE_RPM_{n}"

    await _param(db_session, mine)
    await _param(db_session, theirs)
    await _reported(db_session, vin, mine)
    await db_session.commit()

    response = await client.get(BASE.format(vin=vin), headers=auth_headers)

    assert response.status_code == 200
    keys = [p["param_key"] for p in response.json()["parameters"]]
    assert mine in keys
    assert theirs not in keys


@pytest.mark.integration
@pytest.mark.asyncio
async def test_total_matches_the_returned_rows(
    client: AsyncClient, auth_headers, test_vehicle, db_session: AsyncSession
):
    """`total` counts the scoped rows, not the catalog."""
    vin = test_vehicle["vin"]
    n = next(_SEQ)
    key = f"PROPANE_T2_LEVEL_PCT_{n}"

    await _param(db_session, key)
    await _param(db_session, f"UNRELATED_{n}")
    await _reported(db_session, vin, key)
    await db_session.commit()

    body = (await client.get(BASE.format(vin=vin), headers=auth_headers)).json()

    assert body["total"] == len(body["parameters"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_requires_authentication(client: AsyncClient, test_vehicle):
    response = await client.get(BASE.format(vin=test_vehicle["vin"]))
    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forbidden_for_a_non_owner(client: AsyncClient, non_admin_headers, test_vehicle):
    """Same gate as every other vehicle-LiveLink read.

    This endpoint is the vehicle-scoped counterpart to an admin-only catalog,
    so it must not become a way to read another user's parameter list.
    """
    response = await client.get(BASE.format(vin=test_vehicle["vin"]), headers=non_admin_headers)
    assert response.status_code == 403
