"""The live status says which alert line each reading is past.

The tank card colours its fill by it: amber below low, red below critical. The
band comes from the server, so the page never re-derives the rule.
"""

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.utils.datetime_utils import utc_now

_PREFIX = "ALERTLINE_"


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    from app.models.livelink_parameter import LiveLinkParameter
    from app.models.vehicle_telemetry import VehicleTelemetryLatest

    async def _wipe():
        await db_session.execute(
            delete(VehicleTelemetryLatest).where(
                VehicleTelemetryLatest.param_key.like(f"{_PREFIX}%")
            )
        )
        await db_session.execute(
            delete(LiveLinkParameter).where(LiveLinkParameter.param_key.like(f"{_PREFIX}%"))
        )
        await db_session.commit()

    await _wipe()
    yield
    await _wipe()


async def _values(client, auth_headers, db_session, vin, rows) -> dict[str, dict]:
    """Seed (key, value, warning_min, critical_min) rows; return latest_values by key."""
    from app.models.livelink_parameter import LiveLinkParameter
    from app.models.vehicle_telemetry import VehicleTelemetryLatest

    at = utc_now() - timedelta(minutes=1)
    for key, value, low, critical in rows:
        db_session.add(
            LiveLinkParameter(
                param_key=f"{_PREFIX}{key}",
                warning_min=low,
                critical_min=critical,
                show_on_dashboard=True,
                archive_only=False,
            )
        )
        db_session.add(
            VehicleTelemetryLatest(vin=vin, param_key=f"{_PREFIX}{key}", value=value, timestamp=at)
        )
    await db_session.commit()

    response = await client.get(f"/api/vehicles/{vin}/livelink/status", headers=auth_headers)
    assert response.status_code == 200
    return {
        v["param_key"].removeprefix(_PREFIX): v
        for v in response.json()["latest_values"]
        if v["param_key"].startswith(_PREFIX)
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_each_value_says_which_line_it_is_past(
    client, auth_headers, db_session, test_vehicle
):
    values = await _values(
        client,
        auth_headers,
        db_session,
        test_vehicle["vin"],
        [
            ("FULL", 72.0, 25.0, 10.0),
            ("LOW", 24.0, 25.0, 10.0),
            ("EMPTY", 9.0, 25.0, 10.0),
            ("OFF", 1.0, None, None),
        ],
    )

    bands = {key: (v["alert_band"], v["in_warning"]) for key, v in values.items()}
    assert bands == {
        "FULL": (None, False),
        "LOW": ("low", True),
        "EMPTY": ("critical", True),
        "OFF": (None, False),
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_critical_line_alone_puts_a_value_in_warning(
    client, auth_headers, db_session, test_vehicle
):
    values = await _values(
        client,
        auth_headers,
        db_session,
        test_vehicle["vin"],
        [("BELOW", 5.0, None, 10.0), ("ABOVE", 15.0, None, 10.0)],
    )

    assert (values["BELOW"]["alert_band"], values["BELOW"]["in_warning"]) == ("critical", True)
    assert (values["ABOVE"]["alert_band"], values["ABOVE"]["in_warning"]) == (None, False)
