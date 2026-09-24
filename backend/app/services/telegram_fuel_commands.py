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
from typing import Any, Literal, cast

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.units import DistanceUnit
from app.services.fuel_ingest import WebhookFuelPayload, create_fuel_record, resolve_vehicle
from app.utils.household_time import household_zone
from app.utils.render_context import render_context_for_vehicle
from app.utils.units import UnitConverter

logger = logging.getLogger(__name__)

# The "/" form, because in a group with privacy mode on (the Telegram default)
# only messages starting with "/" reach the bot. It works in a private chat too.
USAGE = (
    "MyGarage fuel bot\n/fuel <vin|nickname> <odometer>[km|mi] <volume>[L|gal|kWh] [price] [cost]\n"
    "An odometer with no km/mi is in the vehicle's unit; a volume with no unit is litres."
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


VolumeUnit = Literal["l", "gal", "kwh"]


@dataclass(frozen=True)
class ParsedFuelCommand:
    """A fuel command as typed: nothing converted yet.

    The odometer's unit is known only once the vehicle is (#172): a bare
    reading is in that vehicle's unit, so conversion waits for
    `build_payload`.
    """

    vehicle_key: str
    odometer: Decimal
    odometer_unit: DistanceUnit | None
    volume: Decimal
    volume_unit: VolumeUnit
    price: Decimal | None
    cost: Decimal | None


def parse_fuel_command(text: str) -> ParsedFuelCommand:
    """Parse a structured fuel command into its typed parts.

    The vehicle key is kept apart because it may be a nickname, which is
    String(100), while the payload's vin field is capped at 17. Building the
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
                "/fuel <vin|nickname> <odometer>[km|mi] <volume>[L|gal|kWh] [price] [cost]"
            ),
        )
    try:
        odo = Decimal(match.group("odo"))
        vol = Decimal(match.group("vol"))
        price = Decimal(match.group("price")) if match.group("price") else None
        cost = Decimal(match.group("cost")) if match.group("cost") else None
    except (InvalidOperation, TypeError) as err:
        raise HTTPException(status_code=400, detail="Invalid numeric values") from err

    odo_unit = match.group("odo_unit")
    return ParsedFuelCommand(
        vehicle_key=match.group("vehicle"),
        odometer=odo,
        odometer_unit=cast(DistanceUnit, odo_unit.lower()) if odo_unit else None,
        volume=vol,
        volume_unit=cast(VolumeUnit, (match.group("vol_unit") or "L").lower()),
        price=price,
        cost=cost,
    )


def build_payload(
    parsed: ParsedFuelCommand, *, vin: str, distance_unit: DistanceUnit
) -> WebhookFuelPayload:
    """The canonical payload for a parsed command on a known vehicle.

    An explicit km/mi suffix wins; a bare odometer is in `distance_unit`, the
    vehicle's effective unit (#172). Constructed ONCE with the final values:
    `WebhookFuelPayload`'s bounds are checked at construction only, so
    converting into an already-built payload would skip them.
    """
    odometer_unit = parsed.odometer_unit or distance_unit
    odometer_km = (
        parsed.odometer * UnitConverter.MILES_TO_KM if odometer_unit == "mi" else parsed.odometer
    )

    liters = None
    kwh = None
    price = parsed.price
    if parsed.volume_unit == "kwh":
        kwh = parsed.volume
        price_basis = "per_kwh"
    elif parsed.volume_unit == "gal":
        liters = parsed.volume * UnitConverter.US_GALLONS_TO_LITERS
        price_basis = "per_volume"
        if price is not None:
            # Convert $/gal to $/L
            price = price / UnitConverter.US_GALLONS_TO_LITERS
    else:
        liters = parsed.volume
        price_basis = "per_volume"

    return WebhookFuelPayload(
        vin=vin,
        odometer_km=odometer_km,
        liters=liters,
        kwh=kwh,
        price_per_unit=price,
        price_basis=price_basis,
        cost=parsed.cost,
        notes="via telegram",
    )


_VOLUME_LABELS: dict[str, str] = {"l": "L", "gal": "gal", "kwh": "kWh"}


def _echo_number(value: Decimal) -> str:
    """A typed number grouped for reading back: 10000 -> 10,000; 40.50 -> 40.5."""
    text = f"{value:,f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


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
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not text:
        return CommandResult(reply=None)
    # In a group only commands are for the bot. With privacy mode on Telegram
    # delivers nothing else, but a bot made a group admin sees every message
    # and must not answer each one.
    if chat.get("type") in ("group", "supergroup") and not text.startswith("/"):
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
        parsed = parse_fuel_command(text)
        vehicle = await resolve_vehicle(db, parsed.vehicle_key)
        # The chat has no MyGarage user, so a bare reading takes the vehicle's
        # effective unit the way a scheduled job does: its own odometer unit,
        # else its owner's, else the instance default (#172).
        ctx = await render_context_for_vehicle(db, vehicle.vin)
        odometer_unit = parsed.odometer_unit or ctx.units.distance
        payload = build_payload(parsed, vin=vehicle.vin, distance_unit=ctx.units.distance)
        payload.date = message_date(message)
        result = await create_fuel_record(db, payload)
    except HTTPException as exc:
        return CommandResult(reply=f"Could not log that: {exc.detail}")
    except ValidationError as exc:
        logger.info("Telegram command rejected by validation (%d errors)", exc.error_count())
        return CommandResult(reply="Could not log that: one of those values is out of range.")
    # Echo each number in the unit it was READ in, so a misread is visible in
    # the chat at once; never re-expressed in the owner's display units.
    reply = (
        f"Logged {_echo_number(parsed.odometer)} {odometer_unit} and "
        f"{_echo_number(parsed.volume)} {_VOLUME_LABELS[parsed.volume_unit]} for "
        f"{vehicle.nickname or result['vin']} on {result['date']}."
    )
    return CommandResult(reply=reply, logged=True)
