"""The Torque Pro Android app, over HTTP GET/POST.

Extracted verbatim in behavior from `routes/torque.py:_ingest`.

Deliberately does NOT declare ODOMETER: `store_torque_telemetry` never called
`_sync_odometer_from_telemetry`, so declaring it would silently start syncing
odometer for every Torque user. The design document's capability table is
wrong on this point.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.livelink_device import LiveLinkDevice
from app.services.livelink_sources.base import (
    BaseSourceModule,
    Capability,
    ExplicitSession,
    GeoPoint,
    HttpEnvelope,
    IngestBatch,
    Reading,
    StoragePolicy,
)
from app.services.torque_pid_map import parse_torque_query

logger = logging.getLogger(__name__)


def _to_decimal(value: float | None) -> Decimal | None:
    """Optional float to Decimal for the location_points Numeric columns."""
    return Decimal(str(value)) if value is not None else None


class TorqueModule(BaseSourceModule):
    """Torque Pro."""

    kind = "torque"
    capabilities = frozenset({Capability.TELEMETRY, Capability.DRIVE_SESSION, Capability.LOCATION})
    #: Exactly store_torque_telemetry's behavior: newer-only latest updates so a
    #: backfilled row never clobbers a fresher live one, and no storage-interval
    #: check because that method never performed one.
    storage_policy = StoragePolicy(
        latest="if_newer",
        apply_storage_interval=False,
        sync_odometer=False,
        observe_movement=False,
    )

    async def resolve_device(self, db: AsyncSession, device_key: str) -> LiveLinkDevice | None:
        """Torque's device_key is a path token, not a device id."""
        from app.services.torque_service import TorqueService

        return await TorqueService(db).resolve_by_token(device_key)

    async def parse(self, env) -> IngestBatch | None:
        if not isinstance(env, HttpEnvelope):
            return None

        reading = parse_torque_query(env.params)
        now = datetime.now(UTC).replace(tzinfo=None)
        ts = now
        if reading.time_ms:
            try:
                candidate = datetime.fromtimestamp(reading.time_ms / 1000, tz=UTC).replace(
                    tzinfo=None
                )
            except OverflowError, OSError, ValueError:
                # `time_ms` is only digit-validated, never range-checked. Degrade
                # to server-now rather than 500ing: Torque retries on any non-OK
                # response, so a bad device clock would wedge in a retry loop.
                candidate = now
            # Trust a PAST device clock (legitimate replay/backfill) but never a
            # future one: a future started_at finalizes to a NEGATIVE duration
            # and poisons ordering and dedup (R2-H2).
            ts = min(candidate, now)

        location = None
        lat, lon = reading.gps.get("latitude"), reading.gps.get("longitude")
        if lat is not None and lon is not None:
            location = GeoPoint(
                latitude=Decimal(str(lat)),
                longitude=Decimal(str(lon)),
                speed=_to_decimal(reading.gps.get("speed")),
                heading=_to_decimal(reading.gps.get("heading")),
                altitude=_to_decimal(reading.gps.get("altitude")),
            )

        return IngestBatch(
            device_key=env.token,
            readings=[Reading(k, float(v)) for k, v in reading.obd.items()],
            # `_ingest` returns OK! and does nothing at all for an unlinked
            # device, so Torque never touched status for one.
            requires_link=True,
            # Torque has no pending-offline concept and has NEVER sent
            # threshold alerts (zero check_thresholds calls in routes/torque.py).
            clear_pending_offline=False,
            alert_on_thresholds=False,
            # An actively-uploading device is online. resolve_torque_session may
            # have just ended a stale prior trip and set ecu_status offline, so
            # re-assert it whenever real data arrives.
            ecu_status="online" if (reading.obd or reading.gps) else None,
            device_status="online",
            session=ExplicitSession(external_id=reading.session),
            location=location,
            timestamp=ts,
        )
