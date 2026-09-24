"""Sensor templates: what one kind of sensor publishes, so adding one takes a
name, a vehicle and a topic.

A preset describes ONE sensor. Each sensor made from it is its own
`generic_mqtt` device (see `sensors.py`), so two tanks are two devices under
one tab, the way two WiCAN dongles are.

Data in code. Not user-authored and not dynamically imported: MyGarage is a
public repository and executing supplied code is a security surface three
sources do not justify.
"""

from __future__ import annotations

from app.services.livelink_sources.presets import mopeka
from app.services.livelink_sources.presets.model import Preset, PresetReading, ReadingFormat

__all__ = ["PRESETS", "Preset", "PresetReading", "ReadingFormat"]

PRESETS: dict[str, Preset] = {
    "mopeka": Preset(
        name="mopeka",
        title="Mopeka",
        # No bottle size and no gateway: calibration is the gateway's setting,
        # and where it publishes is its owner's choice.
        description="Mopeka Pro Check propane tank sensors.",
        kind="generic_mqtt",
        key_prefix="PROPANE",
        device_prefix="mopeka-t",
        readings=mopeka.READINGS,
        storage_interval_seconds=mopeka.STORAGE_INTERVAL_SECONDS,
        fill_suffix="LEVEL_PCT",
    )
}
