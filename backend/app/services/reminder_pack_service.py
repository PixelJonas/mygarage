"""Load and apply built-in reminder packs."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.maintenance import AnchorChoice, ApplyPackPreview
from app.schemas.reminder import ReminderResponse
from app.schemas.reminder_pack import ReminderPackDetail, ReminderPackSummary
from app.services import maintenance_service, reminder_service
from app.utils.logging_utils import sanitize_for_log

logger = logging.getLogger(__name__)

PACKS_DIR = Path(__file__).resolve().parent.parent / "data" / "reminder_packs"
# Pack ids are filenames (minus .json). Reject anything that could traverse.
_PACK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _path_within_packs(path: Path) -> Path | None:
    """Return the resolved path if it stays inside PACKS_DIR, else None."""
    try:
        resolved = path.resolve()
        resolved.relative_to(PACKS_DIR.resolve())
    except ValueError, OSError:
        return None
    return resolved


def _load_pack_file(path: Path) -> ReminderPackDetail:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return ReminderPackDetail.model_validate(data)


def _pack_paths() -> dict[str, Path]:
    """Map filename stem -> resolved path for every readable pack in PACKS_DIR.

    Every path here comes from directory enumeration, never from caller input,
    so a caller-supplied id is only ever used as a dict *key*. That keeps user
    data out of path expressions entirely instead of relying on a
    validate-then-join round trip to make it safe after the fact.
    """
    index: dict[str, Path] = {}
    if not PACKS_DIR.is_dir():
        return index
    for candidate in sorted(PACKS_DIR.glob("*.json")):
        resolved = _path_within_packs(candidate)
        if resolved is None or not resolved.is_file():
            continue
        index[candidate.stem] = resolved
    return index


def list_packs(vehicle_type: str | None = None) -> list[ReminderPackSummary]:
    """List built-in reminder packs (sorted by name).

    When ``vehicle_type`` is provided, packs that declare a non-empty
    ``vehicle_types`` list are included only if that type is listed.
    Packs with an empty ``vehicle_types`` list apply to every vehicle.
    """
    packs: list[ReminderPackSummary] = []
    if not PACKS_DIR.is_dir():
        logger.warning("Reminder packs directory missing: %s", PACKS_DIR)
        return packs

    for path in _pack_paths().values():
        try:
            detail = _load_pack_file(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.error("Failed to load reminder pack %s: %s", path.name, sanitize_for_log(exc))
            continue
        if vehicle_type and detail.vehicle_types and vehicle_type not in detail.vehicle_types:
            continue
        packs.append(
            ReminderPackSummary(
                id=detail.id,
                name=detail.name,
                description=detail.description,
                reminder_count=len(detail.reminders),
                vehicle_types=list(detail.vehicle_types),
            )
        )
    packs.sort(key=lambda p: p.name.lower())
    return packs


def get_pack(pack_id: str) -> ReminderPackDetail:
    """Load a single pack by id, or raise 404.

    ``pack_id`` is checked against a conservative identifier pattern and then
    used only as a key into the enumerated pack index, so it never becomes a
    path component. ``../`` and absolute paths 404.
    """
    if not _PACK_ID_RE.fullmatch(pack_id):
        raise HTTPException(status_code=404, detail=f"Reminder pack '{pack_id}' not found")

    index = _pack_paths()
    path = index.get(pack_id)
    if path is not None:
        try:
            detail = _load_pack_file(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.error(
                "Failed to load reminder pack %s: %s",
                sanitize_for_log(pack_id),
                sanitize_for_log(exc),
            )
            raise HTTPException(status_code=500, detail="Failed to load reminder pack") from exc
        if detail.id != pack_id:
            raise HTTPException(status_code=404, detail=f"Reminder pack '{pack_id}' not found")
        return detail

    # A pack's filename may differ from the id it declares, so fall back to
    # reading the declared id out of each enumerated pack.
    for resolved in index.values():
        try:
            detail = _load_pack_file(resolved)
        except OSError, json.JSONDecodeError, ValueError:
            continue
        if detail.id == pack_id:
            return detail

    raise HTTPException(status_code=404, detail=f"Reminder pack '{pack_id}' not found")


async def apply_pack(
    vin: str,
    pack_id: str,
    db: AsyncSession,
    anchors: dict[str, AnchorChoice | None] | None = None,
) -> list[ReminderResponse]:
    """Apply a reminder pack to a vehicle through the maintenance lifecycle.

    Each item becomes (or reuses) a per-vehicle maintenance rule; the rule's
    pending reminder is anchored on the vehicle's most recent qualifying
    service, adopts a loose reminder of the same type instead of duplicating
    it, and is created from today's readings only when nothing is on record.
    See ``maintenance_service.apply_pack`` and the design's section 5.4.

    Returns the pending reminder of every rule the pack touched, in pack
    order, the list shape this endpoint always returned.
    """
    pack = get_pack(pack_id)
    reminders = await maintenance_service.apply_pack(db, vin, pack, anchors)
    return [await reminder_service.enrich_with_estimate(r, db) for r in reminders]


async def preview_pack(
    vin: str,
    pack_id: str,
    db: AsyncSession,
    anchors: dict[str, AnchorChoice | None] | None = None,
) -> ApplyPackPreview:
    """What ``apply_pack`` would do, with no writes."""
    pack = get_pack(pack_id)
    return await maintenance_service.plan_pack(db, vin, pack, anchors)
