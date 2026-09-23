"""Creating a fuel record from an outside source: the fuel webhook and Telegram.

Moved out of ``routes/webhooks.py`` so the Telegram poller, a service, does not
import a route module's private helpers.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel import FuelRecord
from app.models.vehicle import Vehicle
from app.schemas.fuel import (
    CHARGE_LEVEL_VALUES,
    CHARGE_LOCATION_VALUES,
    _validate_diesel_grade,
    _validate_octane,
)
from app.services.fuel_side_effects import (
    apply_fuel_record_side_effects,
    invalidate_cache_for_vehicle,
)
from app.utils.household_time import household_today


class WebhookFuelPayload(BaseModel):
    """Inbound fuel/charge payload.

    Numeric bounds mirror FuelRecordBase. Without them SQLite stores an absurd
    value silently, and on PostgreSQL the driver raises a DataError that
    surfaces as a 500 rather than a 4xx.

    Unlike FuelRecordCreate, odometer and amount are both optional: a charge
    session legitimately arrives with neither.
    """

    vin: str = Field(..., max_length=17)
    date: date_type | None = None
    odometer_km: Decimal | None = Field(None, ge=0, le=99999999.99)
    liters: Decimal | None = Field(None, ge=0, le=9999.999)
    kwh: Decimal | None = Field(None, ge=0, le=99999.999)
    cost: Decimal | None = Field(None, ge=0, le=99999.99)
    price_per_unit: Decimal | None = Field(None, ge=0, le=999.999)
    price_basis: str | None = None
    is_full_tank: bool = True
    notes: str | None = None
    soc_start_pct: Decimal | None = Field(None, ge=0, le=100)
    soc_end_pct: Decimal | None = Field(None, ge=0, le=100)
    charge_level: str | None = Field(None, max_length=10)
    charge_location: str | None = Field(None, max_length=20)
    battery_soh_pct: Decimal | None = Field(None, ge=0, le=100)
    fuel_type_used: str | None = None
    # #164 — same validators as the fuel input schemas.
    octane: int | None = None
    diesel_grade: str | None = Field(None, max_length=10)

    @field_validator("octane")
    @classmethod
    def _check_octane(cls, v: int | None) -> int | None:
        return _validate_octane(v)

    @field_validator("diesel_grade")
    @classmethod
    def _check_diesel_grade(cls, v: str | None) -> str | None:
        return _validate_diesel_grade(v)

    @field_validator("charge_level")
    @classmethod
    def _check_charge_level(cls, v: str | None) -> str | None:
        if v is not None and v not in CHARGE_LEVEL_VALUES:
            raise ValueError(f"charge_level must be one of {CHARGE_LEVEL_VALUES}, got {v!r}")
        return v

    @field_validator("charge_location")
    @classmethod
    def _check_charge_location(cls, v: str | None) -> str | None:
        if v is not None and v not in CHARGE_LOCATION_VALUES:
            raise ValueError(f"charge_location must be one of {CHARGE_LOCATION_VALUES}, got {v!r}")
        return v


async def resolve_vehicle(db: AsyncSession, vin_or_nick: str) -> Vehicle:
    """The vehicle a VIN or a nickname names (nickname match ignores case).

    Raises ``HTTPException`` 404 when nothing matches and 409 when a nickname
    matches more than one vehicle.
    """
    key = vin_or_nick.strip()
    result = await db.execute(select(Vehicle).where(Vehicle.vin == key.upper()))
    vehicle = result.scalar_one_or_none()
    if vehicle:
        return vehicle
    result = await db.execute(
        select(Vehicle).where(func.lower(Vehicle.nickname) == key.lower()).limit(2)
    )
    matches = result.scalars().all()
    if len(matches) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ambiguous nickname '{vin_or_nick}' matches multiple vehicles; use VIN instead",
        )
    if not matches:
        raise HTTPException(status_code=404, detail=f"Vehicle not found: {vin_or_nick}")
    return matches[0]


async def create_fuel_record(db: AsyncSession, payload: WebhookFuelPayload) -> dict[str, Any]:
    """Log a fill-up and its side effects in ONE commit; returns its id, VIN and date.

    Anything the session already holds (the Telegram poller stages its offset
    there) is committed with it. No date means today in the household zone.
    """
    vehicle = await resolve_vehicle(db, payload.vin)
    fill_date = payload.date or household_today()
    price_basis = payload.price_basis
    if price_basis is None and payload.kwh is not None:
        price_basis = "per_kwh"
    elif price_basis is None and payload.liters is not None:
        price_basis = "per_volume"

    record = FuelRecord(
        vin=vehicle.vin,
        date=fill_date,
        odometer_km=payload.odometer_km,
        liters=payload.liters,
        kwh=payload.kwh,
        cost=payload.cost,
        price_per_unit=payload.price_per_unit,
        price_basis=price_basis,
        is_full_tank=payload.is_full_tank,
        notes=payload.notes,
        soc_start_pct=payload.soc_start_pct,
        soc_end_pct=payload.soc_end_pct,
        charge_level=payload.charge_level,
        charge_location=payload.charge_location,
        battery_soh_pct=payload.battery_soh_pct,
        fuel_type_used=payload.fuel_type_used or ("electric" if payload.kwh is not None else None),
        octane=payload.octane,
        diesel_grade=payload.diesel_grade,
    )
    db.add(record)
    await db.flush()  # populate record.id without committing
    await apply_fuel_record_side_effects(db, record)
    await db.commit()
    await db.refresh(record)
    await invalidate_cache_for_vehicle(vehicle.vin)
    return {"id": record.id, "vin": record.vin, "date": str(record.date)}
