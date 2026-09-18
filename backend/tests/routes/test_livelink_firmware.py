"""Endpoint tests for track-aware firmware routes (Task 4).

Fixtures:
  - ``client`` / ``auth_headers`` — from tests/conftest.py (base conftest).
  - ``seed_cache`` — defined here; inserts a LiveLinkFirmwareCache row directly.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.livelink_firmware_cache import LiveLinkFirmwareCache
from app.utils.datetime_utils import utc_now


@pytest_asyncio.fixture
async def seed_cache(db_session: AsyncSession):
    """Return a coroutine-callable that inserts/replaces a firmware cache row."""
    from sqlalchemy import select

    async def _seed(track: str, version: str, tag: str) -> None:
        result = await db_session.execute(
            select(LiveLinkFirmwareCache).where(LiveLinkFirmwareCache.track == track)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = LiveLinkFirmwareCache(track=track)
            db_session.add(row)
        row.latest_version = version
        row.latest_tag = tag
        row.release_url = f"https://example.com/{tag}"
        row.release_notes = None
        row.checked_at = utc_now()
        await db_session.commit()

    return _seed


@pytest.mark.asyncio
async def test_latest_defaults_to_pro(client: AsyncClient, auth_headers, seed_cache):
    """GET /firmware/latest with no ?track= returns the 'pro' cache row."""
    await seed_cache(track="pro", version="4.50", tag="v4.50p")
    await seed_cache(track="obd", version="4.21", tag="v4.21")

    r = await client.get("/api/livelink/firmware/latest", headers=auth_headers)

    assert r.status_code == 200
    body = r.json()
    assert body["firmware_track"] == "pro"
    assert body["latest_version"] == "4.50"


@pytest.mark.asyncio
async def test_latest_obd_track(client: AsyncClient, auth_headers, seed_cache):
    """GET /firmware/latest?track=obd returns the 'obd' cache row."""
    await seed_cache(track="obd", version="4.21", tag="v4.21")

    r = await client.get("/api/livelink/firmware/latest?track=obd", headers=auth_headers)

    assert r.status_code == 200
    assert r.json()["latest_version"] == "4.21"


@pytest.mark.asyncio
async def test_latest_invalid_track_422(client: AsyncClient, auth_headers):
    """GET /firmware/latest?track=bogus returns 422 (invalid enum value)."""
    r = await client.get("/api/livelink/firmware/latest?track=bogus", headers=auth_headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_check_returns_single_default_track(client: AsyncClient, auth_headers, monkeypatch):
    """POST /firmware/check refreshes both tracks and returns one FirmwareInfoResponse."""

    async def fake_check(self):
        return {"tracks": {"pro": {"latest_version": "4.50"}, "obd": {"latest_version": "4.21"}}}

    monkeypatch.setattr(
        "app.services.firmware_service.FirmwareService.check_firmware_updates", fake_check
    )

    # Also patch get_cached_firmware_info so it doesn't hit a cold DB after fake_check
    async def fake_cached(self, track: str = "pro"):
        data = {"pro": {"latest_version": "4.50"}, "obd": {"latest_version": "4.21"}}
        return {
            "latest_version": data[track]["latest_version"],
            "latest_tag": f"v{data[track]['latest_version']}{'p' if track == 'pro' else ''}",
            "release_url": None,
            "release_notes": None,
            "checked_at": utc_now(),
            "firmware_track": track,
        }

    monkeypatch.setattr(
        "app.services.firmware_service.FirmwareService.get_cached_firmware_info", fake_cached
    )

    r = await client.post("/api/livelink/firmware/check", headers=auth_headers)

    assert r.status_code == 200
    body = r.json()
    # Single FirmwareInfoResponse for the default (pro) track, not an aggregate.
    assert body["firmware_track"] == "pro"
    assert "tracks" not in body


# ---------------------------------------------------------------------------
# Skip-this-version endpoints (plan 2026-09-18, feature B)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seed_device(db_session: AsyncSession):
    """Insert/replace one pro device; returns the row (module-local id)."""
    from sqlalchemy import delete

    from app.models.livelink_device import LiveLinkDevice

    device_id = "fwskiproute01"
    await db_session.execute(delete(LiveLinkDevice).where(LiveLinkDevice.device_id == device_id))
    device = LiveLinkDevice(device_id=device_id, hw_version="WiCAN-OBD-PRO", fw_version="4.45")
    db_session.add(device)
    await db_session.commit()
    # The plain id, not the ORM row: the client's requests expire the session
    # and a later attribute access would sync-refresh into MissingGreenlet.
    return device_id


@pytest.mark.asyncio
async def test_skip_and_unskip_round_trip(
    client: AsyncClient, auth_headers, seed_device, db_session
):
    """POST sets firmware_skipped_version; DELETE clears it."""
    from sqlalchemy import select

    from app.models.livelink_device import LiveLinkDevice

    r = await client.post(
        f"/api/livelink/devices/{seed_device}/firmware/skip",
        headers=auth_headers,
        json={"version": "4.50"},
    )
    assert r.status_code == 200, r.text

    db_session.expire_all()
    row = (
        await db_session.execute(
            select(LiveLinkDevice).where(LiveLinkDevice.device_id == seed_device)
        )
    ).scalar_one()
    assert row.firmware_skipped_version == "4.50"

    r = await client.delete(
        f"/api/livelink/devices/{seed_device}/firmware/skip",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    db_session.expire_all()
    row = (
        await db_session.execute(
            select(LiveLinkDevice).where(LiveLinkDevice.device_id == seed_device)
        )
    ).scalar_one()
    assert row.firmware_skipped_version is None


@pytest.mark.asyncio
async def test_skip_unknown_device_404(client: AsyncClient, auth_headers):
    r = await client.post(
        "/api/livelink/devices/doesnotexist99/firmware/skip",
        headers=auth_headers,
        json={"version": "4.50"},
    )
    assert r.status_code == 404
    r = await client.delete(
        "/api/livelink/devices/doesnotexist99/firmware/skip", headers=auth_headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_skip_requires_admin(client: AsyncClient, non_admin_headers, seed_device):
    """Admin-only, like the rest of /firmware/*: 403 for a plain user."""
    r = await client.post(
        f"/api/livelink/devices/{seed_device}/firmware/skip",
        headers=non_admin_headers,
        json={"version": "4.50"},
    )
    assert r.status_code == 403
    r = await client.delete(
        f"/api/livelink/devices/{seed_device}/firmware/skip",
        headers=non_admin_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_skip_requires_auth(client: AsyncClient, seed_device):
    r = await client.post(
        f"/api/livelink/devices/{seed_device}/firmware/skip",
        json={"version": "4.50"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_skip_rejects_blank_and_overlong_versions(
    client: AsyncClient, auth_headers, seed_device
):
    for bad in ("", "x" * 21):
        r = await client.post(
            f"/api/livelink/devices/{seed_device}/firmware/skip",
            headers=auth_headers,
            json={"version": bad},
        )
        assert r.status_code == 422, (bad, r.text)


@pytest.mark.asyncio
async def test_firmware_devices_surfaces_skipped_version(
    client: AsyncClient, auth_headers, seed_device, seed_cache, db_session
):
    """R1-F2: the explicit DeviceFirmwareStatus(...) constructor in
    /firmware/devices must pass skipped_version through, or the HTTP
    response stays null while the DB row is set."""
    await seed_cache(track="pro", version="4.50", tag="v4.50p")
    r = await client.post(
        f"/api/livelink/devices/{seed_device}/firmware/skip",
        headers=auth_headers,
        json={"version": "4.50"},
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/livelink/firmware/devices", headers=auth_headers)
    assert r.status_code == 200, r.text
    mine = [d for d in r.json() if d["device_id"] == seed_device]
    assert mine, r.json()
    assert mine[0]["skipped_version"] == "4.50"
