"""One Telegram message in, at most one reply out.

Only the configured chat may log fuel: anyone on Telegram can message a bot.
The reply to any other chat names that chat's ID, which is the value that
goes in the setting.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from app.models.fuel import FuelRecord
from app.models.odometer import OdometerRecord
from app.services.telegram_fuel_commands import USAGE, handle_message


def _message(text, chat=42, sent_at=None):
    message = {"message_id": 1, "chat": {"id": chat}, "date": sent_at or 1_790_000_000}
    if text is not None:
        message["text"] = text
    return message


@pytest_asyncio.fixture(autouse=True)
async def _no_telegram_fill_ups(db_session):
    async def _wipe():
        ids = select(FuelRecord.id).where(FuelRecord.notes == "via telegram")
        await db_session.execute(
            delete(OdometerRecord).where(OdometerRecord.fuel_record_id.in_(ids))
        )
        await db_session.execute(delete(FuelRecord).where(FuelRecord.notes == "via telegram"))
        await db_session.commit()

    await _wipe()
    yield
    await db_session.rollback()
    await _wipe()


async def _fill_ups(db_session, vin):
    return await db_session.scalar(
        select(func.count())
        .select_from(FuelRecord)
        .where(FuelRecord.vin == vin, FuelRecord.notes == "via telegram")
    )


@pytest.mark.asyncio
async def test_no_text_gets_no_reply(db_session):
    result = await handle_message(db_session, _message(None), "42")
    assert (result.reply, result.logged) == (None, False)


@pytest.mark.asyncio
@pytest.mark.parametrize("configured", ["999", ""], ids=["other-chat", "none-set"])
async def test_another_chat_is_told_its_id_and_logs_nothing(db_session, test_vehicle, configured):
    vin = test_vehicle["vin"]
    result = await handle_message(
        db_session, _message(f"fuel {vin} 10000 40", chat=123), configured
    )

    assert result.logged is False
    assert "can't log fuel" in result.reply
    assert "123" in result.reply
    assert await _fill_ups(db_session, vin) == 0


@pytest.mark.asyncio
async def test_a_configured_chat_with_spaces_still_matches(db_session):
    result = await handle_message(db_session, _message("help"), " 42 ")
    assert result.reply == USAGE


@pytest.mark.asyncio
async def test_a_group_chat_with_a_negative_id_is_allowed(db_session):
    result = await handle_message(
        db_session, _message("help", chat=-1001234567890), "-1001234567890"
    )
    assert result.reply == USAGE


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["help", "/help", "start", "/start", "/help@MyGarageBot"])
async def test_help_answers_with_the_usage(db_session, text):
    result = await handle_message(db_session, _message(text), "42")
    assert (result.reply, result.logged) == (USAGE, False)


@pytest.mark.asyncio
async def test_a_bad_command_says_why(db_session):
    result = await handle_message(db_session, _message("fuel wat"), "42")
    assert result.logged is False
    assert result.reply.startswith("Could not log that")


@pytest.mark.asyncio
async def test_an_out_of_range_value_logs_nothing(db_session, test_vehicle):
    vin = test_vehicle["vin"]
    result = await handle_message(db_session, _message(f"fuel {vin} 999999999999 40"), "42")

    assert result.logged is False
    assert "out of range" in result.reply
    assert await _fill_ups(db_session, vin) == 0


@pytest.mark.asyncio
async def test_a_command_logs_a_fill_up(db_session, test_vehicle):
    vin = test_vehicle["vin"]
    result = await handle_message(
        db_session, _message(f"/fuel {vin} 10000mi 12gal 3.50 42.00"), "42"
    )

    assert result.logged is True
    assert result.reply.startswith(f"Logged fill-up for {vin}")
    record = await db_session.scalar(
        select(FuelRecord).where(FuelRecord.vin == vin, FuelRecord.notes == "via telegram")
    )
    assert float(record.liters) == pytest.approx(45.425, abs=0.01)


@pytest.mark.asyncio
async def test_a_fill_up_is_dated_the_day_it_was_sent(db_session, test_vehicle):
    """Resumed messages can be handled hours late; the day they were sent wins."""
    from app.utils import household_time

    token = household_time.household_zone_var.set(ZoneInfo("America/Chicago"))
    try:
        sent = datetime(2026, 9, 21, 23, 30, tzinfo=ZoneInfo("America/Chicago"))
        vin = test_vehicle["vin"]

        result = await handle_message(
            db_session, _message(f"fuel {vin} 10000 40", sent_at=int(sent.timestamp())), "42"
        )
    finally:
        household_time.household_zone_var.reset(token)

    assert result.logged is True
    record = await db_session.scalar(
        select(FuelRecord).where(FuelRecord.vin == vin, FuelRecord.notes == "via telegram")
    )
    assert record.date == date(2026, 9, 21)


@pytest.mark.asyncio
async def test_a_message_with_an_unreadable_date_is_dated_today(db_session, test_vehicle):
    from app.utils.household_time import household_today

    vin = test_vehicle["vin"]
    message = _message(f"fuel {vin} 10000 40")
    message["date"] = "x"
    result = await handle_message(db_session, message, "42")

    assert result.logged is True
    record = await db_session.scalar(
        select(FuelRecord).where(FuelRecord.vin == vin, FuelRecord.notes == "via telegram")
    )
    assert record.date == household_today()
