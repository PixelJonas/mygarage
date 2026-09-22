"""Name an existing Mopeka install's readings ("Tank 1 level").

Applying the preset now names its parameters, but that cannot reach a device
that already exists: applying again to the same device id is a 409. Without
this, an install made before the names existed keeps showing
"Propane T1 Level Pct" in the settings drawer's reading list for good.

Two guards, both about not overwriting what is not ours:

- Only when a device with ``preset_key = 'mopeka_two_tank'`` exists. A database
  that never applied the preset may own these keys from some other source.
- Only rows whose ``display_name`` is NULL or still the auto default (the key
  title-cased). A name someone chose is theirs.

``_NAMES`` is a SNAPSHOT of ``mopeka_two_tank.DISPLAY_NAMES`` at the time of
writing, inlined per the convention migration 096 states, and deliberately not
kept in step with it: an applied migration's behaviour must not change under a
database that has already run it.

FATAL = False: a skipped rename costs a friendlier label, not correctness.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

FATAL = False

_PRESET = "mopeka_two_tank"

#: Snapshot. See the module docstring.
_NAMES = {
    "PROPANE_T1_LEVEL_PCT": "Tank 1 level",
    "PROPANE_T1_DEPTH_MM": "Tank 1 depth",
    "PROPANE_T1_TEMP_C": "Tank 1 temperature",
    "PROPANE_T1_SENSOR_BATT_PCT": "Tank 1 sensor battery",
    "PROPANE_T1_QUALITY": "Tank 1 reading quality",
    "PROPANE_T1_REJECTED": "Tank 1 rejected readings",
    "PROPANE_T1_AVAILABLE": "Tank 1 sensor heard",
    "PROPANE_T2_LEVEL_PCT": "Tank 2 level",
    "PROPANE_T2_DEPTH_MM": "Tank 2 depth",
    "PROPANE_T2_TEMP_C": "Tank 2 temperature",
    "PROPANE_T2_SENSOR_BATT_PCT": "Tank 2 sensor battery",
    "PROPANE_T2_QUALITY": "Tank 2 reading quality",
    "PROPANE_T2_REJECTED": "Tank 2 rejected readings",
    "PROPANE_T2_AVAILABLE": "Tank 2 sensor heard",
    "RV_GATEWAY_RSSI": "Gateway Wi-Fi signal",
    "RV_GATEWAY_UPTIME_S": "Gateway uptime",
}


def _get_fallback_engine():
    db_path = os.environ.get("DATABASE_PATH")
    if db_path:
        return create_engine(f"sqlite:///{db_path}")
    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    return create_engine(f"sqlite:///{data_dir / 'mygarage.db'}")


def upgrade(engine=None) -> None:
    """Name the preset's parameters on a database that has a preset device."""
    if engine is None:
        engine = _get_fallback_engine()

    inspector = inspect(engine)
    if not (inspector.has_table("livelink_devices") and inspector.has_table("livelink_parameters")):
        print("  → LiveLink tables missing; skip")
        return

    with engine.begin() as conn:
        present = conn.execute(
            text("SELECT 1 FROM livelink_devices WHERE preset_key = :p LIMIT 1"),
            {"p": _PRESET},
        ).first()
        if not present:
            print(f"✓ No {_PRESET} device; nothing to name")
            return

        renamed = 0
        for key, name in _NAMES.items():
            renamed += conn.execute(
                text(
                    "UPDATE livelink_parameters SET display_name = :name "
                    "WHERE param_key = :key AND (display_name IS NULL OR display_name = :auto)"
                ),
                # The same rule as TelemetryService._format_display_name.
                {"name": name, "key": key, "auto": key.replace("_", " ").title()},
            ).rowcount
        print(f"✓ Named {renamed} {_PRESET} parameter(s)")


def downgrade():  # pragma: no cover
    raise NotImplementedError("Migration 115 is forward-only.")


if __name__ == "__main__":
    upgrade()
