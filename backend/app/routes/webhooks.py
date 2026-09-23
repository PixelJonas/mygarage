"""Inbound webhook endpoints for fuel, odometer, reminders, and Telegram.

Authenticated with the shared ``webhook_ingest_token`` setting via the
``X-Webhook-Token`` header (Telegram sends it in a header of its own, see
``webhook_telegram``). Used by the Home Assistant integration, n8n, and the
structured Telegram bot.

The token is deliberately NOT accepted as a query parameter: it would be
written verbatim into granian, Traefik, and Cloudflare access logs, none of
which this application controls.
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.odometer import OdometerRecord
from app.models.reminder import Reminder
from app.services.fuel_ingest import WebhookFuelPayload, create_fuel_record, resolve_vehicle
from app.services.settings_service import SettingsService
from app.utils.household_time import household_today
from app.utils.units import UnitConverter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# Shared-secret auth with no account lockout, so cap guess rate per source IP.
# Local Limiter instance matching the established pattern in routes/auth.py.
limiter = Limiter(key_func=get_remote_address)

# fuel <vin|nickname> <odometer> <volume> [price_per_unit] [cost]
# volume may end with L, gal, or kWh; odometer may end with km/mi
_FUEL_CMD = re.compile(
    r"""^fuel\s+
        (?P<vehicle>\S+)\s+
        (?P<odo>[\d.]+)(?P<odo_unit>km|mi)?\s+
        (?P<vol>[\d.]+)(?P<vol_unit>L|l|gal|kWh|kwh|KWH)?
        (?:\s+(?P<price>[\d.]+))?
        (?:\s+(?P<cost>[\d.]+))?
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


async def require_webhook_token(db: AsyncSession, provided_token: str | None) -> str:
    """Validate the ingest token. Empty/unset configured token -> 503.

    Deliberately NOT a FastAPI dependency: dependencies resolve before slowapi's
    endpoint wrapper runs, so a 401 raised from here would bypass the rate limit
    and leave the shared secret brute-forceable at full request rate.
    """
    setting = await SettingsService.get(db, "webhook_ingest_token")
    expected = (setting.value or "").strip() if setting else ""
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook ingest token is not configured",
        )
    provided = (provided_token or "").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token"
        )
    return provided


class WebhookOdometerPayload(BaseModel):
    vin: str = Field(..., max_length=17)
    odometer_km: Decimal
    date: date_type | None = None
    notes: str | None = None


class WebhookCompleteReminderPayload(BaseModel):
    vin: str = Field(..., max_length=17)
    reminder_id: int


@router.post("/fuel")
@limiter.limit(settings.rate_limit_webhooks)
async def webhook_fuel(
    request: Request,
    payload: WebhookFuelPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a fuel / charge record (metric canonical)."""
    # In-body, not Depends: see require_webhook_token's docstring.
    await require_webhook_token(db, request.headers.get("X-Webhook-Token"))
    return await create_fuel_record(db, payload)


@router.post("/odometer")
@limiter.limit(settings.rate_limit_webhooks)
async def webhook_odometer(
    request: Request,
    payload: WebhookOdometerPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # In-body, not Depends: see require_webhook_token's docstring.
    await require_webhook_token(db, request.headers.get("X-Webhook-Token"))
    vehicle = await resolve_vehicle(db, payload.vin)
    reading = OdometerRecord(
        vin=vehicle.vin,
        date=payload.date or household_today(),
        odometer_km=payload.odometer_km,
        notes=payload.notes,
        source="webhook",
    )
    db.add(reading)
    await db.commit()
    await db.refresh(reading)
    return {"id": reading.id, "vin": reading.vin, "odometer_km": str(reading.odometer_km)}


@router.post("/reminders/complete")
@limiter.limit(settings.rate_limit_webhooks)
async def webhook_complete_reminder(
    request: Request,
    payload: WebhookCompleteReminderPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # In-body, not Depends: see require_webhook_token's docstring.
    await require_webhook_token(db, request.headers.get("X-Webhook-Token"))
    vehicle = await resolve_vehicle(db, payload.vin)
    result = await db.execute(
        select(Reminder).where(
            Reminder.id == payload.reminder_id,
            Reminder.vin == vehicle.vin,
        )
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    # "done" is the app's completion status. reminders.py filters on
    # pending|done|dismissed and the UI renders exactly those three tabs, so any
    # other value makes the reminder invisible and unrecoverable. Routed through
    # the legacy completion so a recurring reminder still gets its successor,
    # anchored on today and the nearest readings.
    if reminder.status == "pending":
        from app.schemas.maintenance import ReminderCompleteRequest
        from app.services.maintenance_service import complete_reminder

        result = await complete_reminder(
            db,
            vehicle.vin,
            reminder.id,
            ReminderCompleteRequest(completed_date=household_today(), mode="mark_only"),
        )
        return {"id": result.reminder.id, "status": result.reminder.status}
    reminder.status = "done"
    await db.commit()
    return {"id": reminder.id, "status": reminder.status}


class TelegramUpdate(BaseModel):
    """Minimal Telegram Bot API Update subset."""

    update_id: int | None = None
    message: dict[str, Any] | None = None


def _parse_fuel_command(text: str) -> tuple[str, WebhookFuelPayload]:
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


@router.post("/telegram")
@limiter.limit(settings.rate_limit_webhooks)
async def webhook_telegram(
    request: Request,
    update: TelegramUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Telegram bot webhook — structured text fuel commands only (no OCR).

    Auth: the webhook ingest token. Telegram cannot send a custom header, but
    it returns the ``secret_token`` given to setWebhook in
    ``X-Telegram-Bot-Api-Secret-Token``, so that header is read first;
    ``X-Webhook-Token`` works too.

    Past auth, every answer is a 200: Telegram redelivers an update it gets a
    4xx for, so a typo, a stranger or a switched-off bot would each become a
    loop. Commands are taken only while Telegram and its fuel commands are
    both switched on (Settings > Notifications > Telegram), and only from the
    chat set there.
    """
    # Authenticate BEFORE reporting whether Telegram ingest is enabled, so an
    # unauthenticated caller cannot probe the instance's configuration.
    await require_webhook_token(
        db,
        request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        or request.headers.get("X-Webhook-Token"),
    )

    if not (
        await SettingsService.get_bool(db, "telegram_enabled")
        and await SettingsService.get_bool(db, "telegram_inbound_enabled")
    ):
        return {"ok": True, "ignored": True}

    message = update.message or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    def _reply(message_text: str) -> dict[str, Any]:
        """Telegram acts on a response body only when it names a method.

        An unknown key like "reply" is discarded, so the user saw nothing.
        """
        return {"method": "sendMessage", "chat_id": chat_id, "text": message_text}

    # An update with no text (an edit, a join) has no chat to answer.
    if not text:
        return {"ok": True, "ignored": True}

    # Anyone can message a bot. With no chat set, no chat ID matches; the reply
    # names the ID, which is the value that goes in the setting.
    chat_setting = await SettingsService.get(db, "telegram_chat_id")
    configured_chat = (chat_setting.value or "").strip() if chat_setting else ""
    if str(chat_id) != configured_chat:
        return _reply(
            f"This chat can't log fuel. To allow it, set Chat ID to {chat_id} "
            "under Settings > Notifications > Telegram in MyGarage."
        )

    if text.lower() in ("help", "/help", "start", "/start"):
        return _reply(
            "MyGarage fuel bot\n"
            "fuel <vin|nickname> <odometer>[km|mi] <volume>[L|gal|kWh] [price] [cost]"
        )

    # Bad input gets a reply, not a 4xx. ValidationError is caught alongside
    # HTTPException because the payload bounds are enforced by pydantic, not by
    # the router, and a bare ValidationError here surfaces as a 500.
    try:
        vehicle_key, payload = _parse_fuel_command(text)
        vehicle = await resolve_vehicle(db, vehicle_key)
        payload.vin = vehicle.vin
        result = await create_fuel_record(db, payload)
    except HTTPException as exc:
        return _reply(f"Could not log that: {exc.detail}")
    except ValidationError as exc:
        logger.info("Telegram command rejected by validation (%d errors)", exc.error_count())
        return _reply("Could not log that: one of those values is out of range.")

    return _reply(f"Logged fill-up for {result['vin']} on {result['date']}.")
