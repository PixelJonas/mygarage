"""Unit tests for the `check_firmware_updates` scheduled job (plan 2026-09-18,
feature B: notify once per version + per-device skip).

The job used to re-notify every device every morning at 03:00 for as long as
an update was pending. Now each device carries `firmware_notified_version`
(stamped only when at least one notification backend actually accepted the
send — the telemetry threshold-alert precedent) and
`firmware_skipped_version` (admin's "skip this version"); the job skips a
device when either matches the latest release exactly, and a NEWER release
matches neither, so it re-notifies.

Session plumbing mirrors test_check_def_levels.py: the job opens
`AsyncSessionLocal()` internally, so `app.tasks.livelink_tasks.AsyncSessionLocal`
is monkeypatched to hand back the fixture-managed `db_session` in a no-op
async context manager. GitHub is never touched:
`FirmwareService.check_firmware_updates` is stubbed and the cache row is
seeded directly. Only the dispatcher is replaced by a recording stub.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.livelink_device import LiveLinkDevice
from app.models.livelink_firmware_cache import LiveLinkFirmwareCache
from app.models.settings import Setting
from app.tasks.livelink_tasks import check_firmware_updates
from app.utils.datetime_utils import utc_now

_DEVICE_ID = "fwtestdevice"

pytestmark = pytest.mark.asyncio


class _PassthroughSessionContext:
    """Hand back the already-open fixture session without closing it."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


@pytest_asyncio.fixture(autouse=True)
async def _clean_slate(db_session: AsyncSession) -> None:
    """Wipe ALL device rows, not just this module's.

    The job scans the whole ``livelink_devices`` table, so a device left
    behind by another module (the shared test database persists across
    files) would receive a dispatch and skew the counts here. Every other
    module seeds its own devices per-test, so a full wipe is safe.
    """
    await db_session.execute(delete(LiveLinkDevice))
    await db_session.commit()


@pytest_asyncio.fixture
async def firmware_world(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    """Settings on, cache at 4.50 (pro), one pro device at 4.45, stub dispatcher.

    Returns (device, sent, set_latest, set_dispatch_result):
      sent — list of (device_id, latest_version) per dispatch call.
      set_latest(version) — repoint the cache (and the stubbed track summary).
      set_dispatch_result(dict) — what the stub dispatcher reports per send.
    """
    monkeypatch.setattr(
        "app.tasks.livelink_tasks.AsyncSessionLocal",
        lambda: _PassthroughSessionContext(db_session),
    )

    for key, value in (
        ("livelink_enabled", "true"),
        ("livelink_firmware_check_enabled", "true"),
        ("livelink_notify_firmware_update", "true"),
    ):
        existing = await db_session.get(Setting, key)
        if existing is None:
            db_session.add(Setting(key=key, value=value))
        else:
            existing.value = value

    state = {"latest": "4.50", "dispatch_result": {"discord": True}}

    result = await db_session.execute(
        select(LiveLinkFirmwareCache).where(LiveLinkFirmwareCache.track == "pro")
    )
    cache = result.scalar_one_or_none()
    if cache is None:
        cache = LiveLinkFirmwareCache(track="pro")
        db_session.add(cache)

    def _apply_cache(version: str) -> None:
        cache.latest_version = version
        cache.latest_tag = f"v{version}p"
        cache.release_url = f"https://example.com/v{version}p"
        cache.release_notes = None
        cache.checked_at = utc_now()

    _apply_cache(state["latest"])

    device = LiveLinkDevice(
        device_id=_DEVICE_ID,
        hw_version="WiCAN-OBD-PRO",
        fw_version="4.45",
        ecu_status="unknown",
        device_status="unknown",
    )
    db_session.add(device)
    await db_session.commit()

    async def fake_check(self):
        return {"tracks": {"pro": {"latest_version": state["latest"]}}}

    monkeypatch.setattr(
        "app.services.firmware_service.FirmwareService.check_firmware_updates", fake_check
    )

    sent: list[tuple[str, str]] = []

    class _StubDispatcher:
        def __init__(self, db) -> None:
            pass

        async def notify_livelink_firmware_update(
            self, device_id, current_version, latest_version, release_url=None
        ):
            sent.append((device_id, latest_version))
            return dict(state["dispatch_result"])

    monkeypatch.setattr("app.tasks.livelink_tasks.NotificationDispatcher", _StubDispatcher)

    async def set_latest(version: str) -> None:
        state["latest"] = version
        _apply_cache(version)
        await db_session.commit()

    def set_dispatch_result(result: dict[str, bool]) -> None:
        state["dispatch_result"] = result

    return device, sent, set_latest, set_dispatch_result


async def _device_row(db_session: AsyncSession) -> LiveLinkDevice:
    db_session.expire_all()
    result = await db_session.execute(
        select(LiveLinkDevice).where(LiveLinkDevice.device_id == _DEVICE_ID)
    )
    return result.scalar_one()


async def test_notifies_once_per_version_and_the_stamp_survives_a_rollback(
    db_session, firmware_world
):
    _, sent, _, _ = firmware_world

    await check_firmware_updates()
    assert sent == [(_DEVICE_ID, "4.50")]

    # The job must COMMIT the stamp (it never used to write anything): a
    # rollback right after must not lose it, or tomorrow re-notifies anyway.
    await db_session.rollback()
    device = await _device_row(db_session)
    assert device.firmware_notified_version == "4.50"

    await check_firmware_updates()
    assert sent == [(_DEVICE_ID, "4.50")], "second run for the same version re-notified"


async def test_a_skipped_version_is_never_notified(db_session, firmware_world):
    device, sent, _, _ = firmware_world
    device.firmware_skipped_version = "4.50"
    await db_session.commit()

    await check_firmware_updates()
    assert sent == []
    device = await _device_row(db_session)
    assert device.firmware_notified_version is None


async def test_a_newer_release_renotifies_past_both_stamps(db_session, firmware_world):
    device, sent, set_latest, _ = firmware_world
    device.firmware_notified_version = "4.50"
    device.firmware_skipped_version = "4.50"
    await db_session.commit()

    await check_firmware_updates()
    assert sent == [], "stamped version notified again"

    await set_latest("4.51")
    await check_firmware_updates()
    assert sent == [(_DEVICE_ID, "4.51")]
    device = await _device_row(db_session)
    assert device.firmware_notified_version == "4.51"


async def test_no_stamp_when_every_backend_refused_so_the_next_run_retries(
    db_session, firmware_world
):
    _, sent, _, set_dispatch_result = firmware_world
    set_dispatch_result({"discord": False})

    await check_firmware_updates()
    assert sent == [(_DEVICE_ID, "4.50")]
    device = await _device_row(db_session)
    assert device.firmware_notified_version is None, "an all-failed dispatch was stamped"

    set_dispatch_result({"discord": True})
    await check_firmware_updates()
    assert sent == [(_DEVICE_ID, "4.50"), (_DEVICE_ID, "4.50")]
    device = await _device_row(db_session)
    assert device.firmware_notified_version == "4.50"


async def test_unskip_lets_the_next_run_notify(db_session, firmware_world):
    device, sent, _, _ = firmware_world
    device.firmware_skipped_version = "4.50"
    await db_session.commit()

    await check_firmware_updates()
    assert sent == []

    device = await _device_row(db_session)
    device.firmware_skipped_version = None
    await db_session.commit()

    await check_firmware_updates()
    assert sent == [(_DEVICE_ID, "4.50")]


async def test_unskip_after_an_already_sent_notification_stays_suppressed(
    db_session, firmware_world
):
    """Notify-once pin: a release notified BEFORE being skipped is not
    re-notified by unskipping — notified_version still matches. Designed
    behaviour (plan 4.2), not a bug."""
    device, sent, _, _ = firmware_world

    await check_firmware_updates()
    assert sent == [(_DEVICE_ID, "4.50")]

    device = await _device_row(db_session)
    device.firmware_skipped_version = "4.50"
    await db_session.commit()
    device = await _device_row(db_session)
    device.firmware_skipped_version = None
    await db_session.commit()

    await check_firmware_updates()
    assert sent == [(_DEVICE_ID, "4.50")]
