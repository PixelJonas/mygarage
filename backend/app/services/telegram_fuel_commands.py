"""Telegram fuel commands: one message in, at most one reply out.

No HTTP and no polling here: ``telegram_poller`` feeds messages in and sends
the replies. Replies are English because the backend is not translated.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.fuel_ingest import WebhookFuelPayload, create_fuel_record, resolve_vehicle
from app.utils.household_time import household_zone
from app.utils.units import UnitConverter

logger = logging.getLogger(__name__)

USAGE = (
    "MyGarage fuel bot\nfuel <vin|nickname> <odometer>[km|mi] <volume>[L|gal|kWh] [price] [cost]"
)
_HELP = ("help", "/help", "start", "/start")

# fuel <vin|nickname> <odometer> <volume> [price_per_unit] [cost]
# Volume may end with L, gal or kWh; odometer with km or mi. A leading "/" and
# an "@BotName" suffix are accepted: in a group with privacy mode on (the
# Telegram default), a bot only receives messages that start with "/".
_FUEL_CMD = re.compile(
    r"""^/?fuel(?:@\w+)?\s+
        (?P<vehicle>\S+)\s+
        (?P<odo>[\d.]+)(?P<odo_unit>km|mi)?\s+
        (?P<vol>[\d.]+)(?P<vol_unit>L|l|gal|kWh|kwh|KWH)?
        (?:\s+(?P<price>[\d.]+))?
        (?:\s+(?P<cost>[\d.]+))?
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class CommandResult:
    """What to answer, and whether a fill-up was committed."""

    reply: str | None
    logged: bool = False


def parse_fuel_command(text: str) -> tuple[str, WebhookFuelPayload]:
    """Parse a structured fuel command into (vehicle_key, payload).

    The vehicle key is returned separately because it may be a nickname, which
    is String(100), while the payload's vin field is capped at 17. Building the
    payload straight from the raw key raised a bare pydantic ValidationError
    inside the handler, which FastAPI renders as a 500. Resolving the key to a
    real VIN is the caller's job.
    """
    match = _FUEL_CMD.match(text.strip())
    if not match:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unrecognized command. Use: "
                "fuel <vin|nickname> <odometer>[km|mi] <volume>[L|gal|kWh] [price] [cost]"
            ),
        )
    try:
        odo = Decimal(match.group("odo"))
        vol = Decimal(match.group("vol"))
    except (InvalidOperation, TypeError) as err:
        raise HTTPException(status_code=400, detail="Invalid numeric values") from err

    odo_unit = (match.group("odo_unit") or "km").lower()
    vol_unit = (match.group("vol_unit") or "L").lower()
    odometer_km = odo * UnitConverter.MILES_TO_KM if odo_unit == "mi" else odo

    liters = None
    kwh = None
    price_basis = None
    if vol_unit in ("kwh",):
        kwh = vol
        price_basis = "per_kwh"
    elif vol_unit == "gal":
        liters = vol * UnitConverter.US_GALLONS_TO_LITERS
        price_basis = "per_volume"
    else:
        liters = vol
        price_basis = "per_volume"

    price = None
    cost = None
    if match.group("price"):
        price = Decimal(match.group("price"))
        if vol_unit == "gal" and price_basis == "per_volume":
            # Convert $/gal → $/L
            price = price / UnitConverter.US_GALLONS_TO_LITERS
    if match.group("cost"):
        cost = Decimal(match.group("cost"))

    return match.group("vehicle"), WebhookFuelPayload(
        vin="0" * 17,  # placeholder; the caller overwrites with the resolved VIN
        odometer_km=odometer_km,
        liters=liters,
        kwh=kwh,
        price_per_unit=price,
        price_basis=price_basis,
        cost=cost,
        notes="via telegram",
    )


def message_date(message: dict[str, Any]) -> date | None:
    """The day a message was sent, in the household timezone; None without a date."""
    sent = message.get("date")
    if not isinstance(sent, int):
        return None
    return datetime.fromtimestamp(sent, tz=household_zone()).date()


async def handle_message(
    db: AsyncSession, message: dict[str, Any], configured_chat: str
) -> CommandResult:
    """Answer one message. Commits only when it logs a fill-up (``logged=True``).

    Rejections (a bad command, an unknown or ambiguous vehicle, an
    out-of-range value) become replies. Anything else propagates: the caller
    cannot tell a bug or an outage from a bad message, so it must not
    acknowledge the update.
    """
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")
    if not text:
        return CommandResult(reply=None)
    # Anyone can message a bot. With no chat set, no chat ID matches.
    if str(chat_id) != configured_chat.strip():
        return CommandResult(
            reply=(
                f"This chat can't log fuel. To allow it, set Chat ID to {chat_id} "
                "under Settings > Notifications > Telegram in MyGarage."
            )
        )
    if text.lower().split("@", 1)[0] in _HELP:
        return CommandResult(reply=USAGE)
    try:
        vehicle_key, payload = parse_fuel_command(text)
        vehicle = await resolve_vehicle(db, vehicle_key)
        payload.vin = vehicle.vin
        payload.date = message_date(message)
        result = await create_fuel_record(db, payload)
    except HTTPException as exc:
        return CommandResult(reply=f"Could not log that: {exc.detail}")
    except ValidationError as exc:
        logger.info("Telegram command rejected by validation (%d errors)", exc.error_count())
        return CommandResult(reply="Could not log that: one of those values is out of range.")
    return CommandResult(
        reply=f"Logged fill-up for {result['vin']} on {result['date']}.", logged=True
    )
