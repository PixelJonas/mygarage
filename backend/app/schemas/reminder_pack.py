"""Pydantic schemas for built-in reminder packs.

Pack format v2 (v3.5.0): an item declares a canonical ``maintenance_type``
and INTERVALS (``interval_km``, ``interval_months``, ``interval_days``,
``interval_hours``); applying a pack creates a per-vehicle rule from them.
The v1 keys (``due_mileage_km``, ``due_date_offset_days``, ``due_hours``,
``reminder_type``) are still accepted: the first three as aliases of the
interval fields, the last ignored, so a pack written for v3.4 still loads.
"""

from __future__ import annotations

import re
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.maintenance import AnchorChoice, validate_maintenance_type

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """A key for a pack item that declares none: 'Oil & Filter Change' -> 'oil_filter_change'."""
    slug = _SLUG_RE.sub("_", title.lower()).strip("_")
    return slug[:64] or "item"


class ReminderPackItem(BaseModel):
    """A single maintenance rule template inside a pack."""

    title: str
    key: str | None = Field(None, max_length=64)
    maintenance_type: str | None = Field(None, max_length=50)
    interval_km: Decimal | None = Field(
        None, gt=0, validation_alias=AliasChoices("interval_km", "due_mileage_km")
    )
    interval_months: int | None = Field(None, gt=0)
    interval_days: int | None = Field(
        None, gt=0, validation_alias=AliasChoices("interval_days", "due_date_offset_days")
    )
    interval_hours: Decimal | None = Field(
        None, gt=0, validation_alias=AliasChoices("interval_hours", "due_hours")
    )
    #: v1 field, accepted and ignored: the type is derived from the intervals.
    reminder_type: str | None = None
    notes: str | None = None

    _validate_type = field_validator("maintenance_type")(validate_maintenance_type)

    @model_validator(mode="after")
    def fill_key_and_check_intervals(self) -> ReminderPackItem:
        """Every item has a key and at least one interval."""
        if self.key is None:
            self.key = self.maintenance_type or slugify(self.title)
        if (
            self.interval_km is None
            and self.interval_months is None
            and self.interval_days is None
            and self.interval_hours is None
        ):
            raise ValueError(f"pack item '{self.title}' declares no interval")
        if self.interval_km is not None and self.interval_hours is not None:
            raise ValueError(f"pack item '{self.title}' mixes distance and hours intervals")
        return self


class ReminderPackSummary(BaseModel):
    """Pack metadata returned by list endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    reminder_count: int = Field(..., description="Number of reminders created when applied")
    vehicle_types: list[str] = Field(
        default_factory=list,
        description="Applicable vehicle types; empty means all types",
    )


class ReminderPackDetail(BaseModel):
    """Full pack definition including reminder templates."""

    id: str
    name: str
    description: str
    reminders: list[ReminderPackItem]
    vehicle_types: list[str] = Field(
        default_factory=list,
        description="Applicable vehicle types; empty means all types",
    )


class ApplyReminderPackRequest(BaseModel):
    """Request body for applying (or previewing) a reminder pack on a vehicle.

    ``anchors`` maps a pack item key to the caller's anchor choice; an item
    not named keeps the preview's proposal.
    """

    pack_id: str = Field(..., min_length=1, max_length=100)
    anchors: dict[str, AnchorChoice | None] | None = None
