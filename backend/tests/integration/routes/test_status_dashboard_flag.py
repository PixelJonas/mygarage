"""The live status reports each reading's dashboard switch, and keeps the reading.

The Live tab hides a gauge whose switch is off. The status endpoint must still
return the value: the vehicle widget looks readings up by key and would lose
its speed or battery the moment someone hid that gauge.
"""

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.utils.datetime_utils import utc_now

_PREFIX = "DASHFLAG_"
HIDDEN = f"{_PREFIX}HIDDEN"
UNREGISTERED = f"{_PREFIX}UNREGISTERED"


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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_hidden_reading_is_flagged_and_still_returned(
    client, auth_headers, db_session, test_vehicle
):
    from app.models.livelink_parameter import LiveLinkParameter
    from app.models.vehicle_telemetry import VehicleTelemetryLatest

    vin = test_vehicle["vin"]
    at = utc_now() - timedelta(minutes=1)
    db_session.add(LiveLinkParameter(param_key=HIDDEN, show_on_dashboard=False, archive_only=False))
    for key in (HIDDEN, UNREGISTERED):
        db_session.add(VehicleTelemetryLatest(vin=vin, param_key=key, value=1.0, timestamp=at))
    await db_session.commit()

    response = await client.get(f"/api/vehicles/{vin}/livelink/status", headers=auth_headers)

    assert response.status_code == 200
    values = {v["param_key"]: v for v in response.json()["latest_values"]}
    assert values[HIDDEN]["show_on_dashboard"] is False
    # A key with no parameter row has never been switched off.
    assert values[UNREGISTERED]["show_on_dashboard"] is True
