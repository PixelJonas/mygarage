"""Torque query-string parsing, including the device-clock clamp."""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.livelink_sources.base import (
    Capability,
    ExplicitSession,
    HttpEnvelope,
    MqttEnvelope,
)
from app.services.livelink_sources.torque import TorqueModule

M = TorqueModule()


def test_does_not_declare_odometer_because_torque_never_synced_it():
    assert Capability.ODOMETER not in M.capabilities
    assert M.capabilities == frozenset(
        {Capability.TELEMETRY, Capability.DRIVE_SESSION, Capability.LOCATION}
    )


def test_storage_policy_matches_store_torque_telemetry():
    assert M.storage_policy.latest == "if_newer"
    assert M.storage_policy.apply_storage_interval is False
    assert M.storage_policy.sync_odometer is False
    assert M.storage_policy.observe_movement is False


@pytest.mark.asyncio
async def test_ignores_an_mqtt_envelope():
    assert await M.parse(MqttEnvelope("a/b", b"1")) is None


@pytest.mark.asyncio
async def test_device_key_is_the_path_token():
    batch = await M.parse(HttpEnvelope(token="tok123", params={"session": "9"}))
    assert batch.device_key == "tok123"
    assert batch.session == ExplicitSession(external_id="9")


@pytest.mark.asyncio
async def test_a_past_device_clock_is_trusted():
    past = datetime.now(UTC) - timedelta(hours=2)
    batch = await M.parse(
        HttpEnvelope(token="t", params={"time": str(int(past.timestamp() * 1000))})
    )
    assert batch.timestamp is not None
    assert batch.timestamp < datetime.now(UTC).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_a_future_device_clock_is_clamped_to_now():
    future = datetime.now(UTC) + timedelta(days=3)
    batch = await M.parse(
        HttpEnvelope(token="t", params={"time": str(int(future.timestamp() * 1000))})
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    assert batch.timestamp <= now + timedelta(seconds=5)


@pytest.mark.asyncio
async def test_garbage_time_degrades_to_server_now_rather_than_raising():
    batch = await M.parse(HttpEnvelope(token="t", params={"time": "9" * 20}))
    assert batch.timestamp is not None


@pytest.mark.asyncio
async def test_flags_preserve_torques_current_side_effects():
    batch = await M.parse(HttpEnvelope(token="t", params={"kc": "900"}))
    assert batch.requires_link is True
    assert batch.alert_on_thresholds is False, "Torque has never sent threshold alerts"
    assert batch.clear_pending_offline is False


@pytest.mark.asyncio
async def test_gps_becomes_a_geopoint():
    batch = await M.parse(
        HttpEnvelope(token="t", params={"kff1006": "45.5", "kff1005": "-122.6"})
    )
    assert batch.location is not None
    assert float(batch.location.latitude) == pytest.approx(45.5)


@pytest.mark.asyncio
async def test_a_reading_with_data_asserts_ecu_online():
    batch = await M.parse(HttpEnvelope(token="t", params={"kc": "900"}))
    assert batch.ecu_status == "online"
