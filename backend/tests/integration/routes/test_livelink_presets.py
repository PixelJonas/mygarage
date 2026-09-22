"""Presets create a device plus its rows in one action."""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models.livelink_device import LiveLinkDevice
from app.models.livelink_parameter import LiveLinkParameter
from app.models.livelink_topic_map import LiveLinkTopicMap

BASE = "/api/livelink/presets"


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    """Presets assert exact row counts, and the suite shares one database."""
    from app.models.livelink_device import LiveLinkDevice
    from app.models.livelink_topic_map import LiveLinkTopicMap

    async def _wipe():
        await db_session.execute(delete(LiveLinkTopicMap))
        await db_session.execute(
            delete(LiveLinkDevice).where(LiveLinkDevice.kind == "generic_mqtt")
        )
        await db_session.commit()

    await _wipe()
    yield
    await _wipe()


@pytest.fixture
def no_reload():
    with patch("app.routes.livelink_admin.mqtt_subscriber.reload", new=AsyncMock()) as r:
        yield r


def test_the_preset_has_the_documented_row_count():
    from app.services.livelink_sources.presets import PRESETS

    rows = PRESETS["mopeka_two_tank"].rows
    assert len(rows) == 17
    assert sum(1 for r in rows if r["role"] == "status") == 1
    assert sum(1 for r in rows if r["role"] == "telemetry") == 16


def test_the_preset_maps_no_non_numeric_topic():
    """vehicle_telemetry.value is Float, so gateway/ip is unmappable."""
    from app.services.livelink_sources.presets import PRESETS

    topics = {r["topic"] for r in PRESETS["mopeka_two_tank"].rows}
    assert "mygarage/rv/gateway/ip" not in topics


def test_every_preset_topic_is_exact():
    from app.services.livelink_sources.presets import PRESETS

    for preset in PRESETS.values():
        for row in preset.rows:
            assert "+" not in row["topic"] and "#" not in row["topic"]


@pytest.mark.asyncio
async def test_listing_presets(client, auth_headers):
    resp = await client.get(BASE, headers=auth_headers)
    assert resp.status_code == 200
    assert "mopeka_two_tank" in {p["name"] for p in resp.json()}


@pytest.mark.asyncio
async def test_applying_creates_the_device_and_rows(
    client, auth_headers, db_session, test_vehicle, no_reload
):
    resp = await client.post(
        f"{BASE}/mopeka_two_tank/apply",
        json={"vin": test_vehicle["vin"], "device_id": "rvgw"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    device = (
        await db_session.execute(select(LiveLinkDevice).where(LiveLinkDevice.device_id == "rvgw"))
    ).scalar_one()
    assert device.kind == "generic_mqtt"
    assert device.vin == test_vehicle["vin"]
    rows = (
        (
            await db_session.execute(
                select(LiveLinkTopicMap).where(LiveLinkTopicMap.device_id == "rvgw")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 17
    assert all(r.device_id == "rvgw" for r in rows)


@pytest.mark.asyncio
async def test_applying_sets_the_storage_interval_on_every_param(
    client, auth_headers, db_session, test_vehicle, no_reload
):
    """Without this, retained-message replay writes a row on every reconnect."""
    await client.post(
        f"{BASE}/mopeka_two_tank/apply",
        json={"vin": test_vehicle["vin"], "device_id": "rvgw"},
        headers=auth_headers,
    )
    params = (await db_session.execute(select(LiveLinkParameter))).scalars().all()
    propane = [p for p in params if p.param_key.startswith("PROPANE_")]
    assert len(propane) == 14
    assert all(p.storage_interval_seconds == 300 for p in propane)


@pytest.mark.asyncio
async def test_applying_triggers_a_resubscribe(client, auth_headers, test_vehicle, no_reload):
    await client.post(
        f"{BASE}/mopeka_two_tank/apply",
        json={"vin": test_vehicle["vin"], "device_id": "rvgw"},
        headers=auth_headers,
    )
    no_reload.assert_awaited_once()


@pytest.mark.asyncio
async def test_applying_twice_is_a_conflict(client, auth_headers, test_vehicle, no_reload):
    body = {"vin": test_vehicle["vin"], "device_id": "rvgw"}
    await client.post(f"{BASE}/mopeka_two_tank/apply", json=body, headers=auth_headers)
    resp = await client.post(f"{BASE}/mopeka_two_tank/apply", json=body, headers=auth_headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_an_unknown_preset_is_404(client, auth_headers, test_vehicle):
    resp = await client.post(
        f"{BASE}/nope/apply",
        json={"vin": test_vehicle["vin"], "device_id": "x"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_non_admins_are_refused(client, non_admin_headers, test_vehicle):
    resp = await client.post(
        f"{BASE}/mopeka_two_tank/apply",
        json={"vin": test_vehicle["vin"], "device_id": "x"},
        headers=non_admin_headers,
    )
    assert resp.status_code in (401, 403)
