"""SettingsService.get_bool reads a switch the way the notification dispatcher does.

Telegram fuel commands read ``telegram_enabled`` through it while the
dispatcher reads the same key for sending, so the two must agree on what "on"
means: a value the dispatcher sends on must not leave fuel commands off.
"""

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.models.settings import Setting
from app.services.settings_service import SettingsService

_KEY = "test_get_bool_switch"


@pytest_asyncio.fixture(autouse=True)
async def _clean(db_session):
    async def _wipe():
        await db_session.execute(delete(Setting).where(Setting.key == _KEY))
        await db_session.commit()

    await _wipe()
    yield
    await _wipe()


@pytest.mark.asyncio
async def test_a_switch_that_was_never_saved_reads_off(db_session):
    assert await SettingsService.get_bool(db_session, _KEY) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "on"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("", False),
        (None, False),
    ],
)
async def test_reads_on_as_the_dispatcher_does(db_session, value, on):
    db_session.add(Setting(key=_KEY, value=value))
    await db_session.commit()

    assert await SettingsService.get_bool(db_session, _KEY) is on


@pytest.mark.asyncio
async def test_default_applies_when_never_saved(db_session):
    assert await SettingsService.get_bool(db_session, _KEY, default=True) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["", None])
async def test_default_applies_to_an_empty_value(db_session, value):
    db_session.add(Setting(key=_KEY, value=value))
    await db_session.commit()

    assert await SettingsService.get_bool(db_session, _KEY, default=True) is True


@pytest.mark.asyncio
async def test_a_saved_false_beats_a_true_default(db_session):
    db_session.add(Setting(key=_KEY, value="false"))
    await db_session.commit()

    assert await SettingsService.get_bool(db_session, _KEY, default=True) is False
