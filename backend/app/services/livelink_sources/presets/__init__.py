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

import re
from dataclasses import dataclass

from app.services.livelink_sources.presets import mopeka


@dataclass(frozen=True)
class PresetReading:
    """One reading a preset's sensor publishes."""

    #: Sensor n's key for this reading is f"{key_prefix}_T{n}_{suffix}".
    suffix: str
    #: Lowercase, shown after the sensor's name: "Front tank level".
    name: str
    unit: str | None
    param_class: str
    #: The last topic segment in the reference layout: the suggestion when the
    #: broker has published nothing to learn from.
    default_topic: str
    #: Lowercase substrings that identify this reading's topic in any layout.
    keywords: tuple[str, ...]
    required: bool = False


@dataclass(frozen=True)
class Preset:
    """One sensor template."""

    name: str
    title: str
    description: str
    kind: str
    key_prefix: str
    device_prefix: str
    readings: tuple[PresetReading, ...]
    storage_interval_seconds: int

    def key(self, index: int, suffix: str) -> str:
        """Sensor `index`'s parameter key for one reading."""
        return f"{self.key_prefix}_T{index}_{suffix}"

    def device_id(self, index: int) -> str:
        """Sensor `index`'s device id."""
        return f"{self.device_prefix}{index}"

    def split_key(self, param_key: str) -> tuple[int, str] | None:
        """(sensor index, reading suffix) for a key of this preset's shape."""
        match = re.match(rf"^{re.escape(self.key_prefix)}_T(\d+)_(.+)$", param_key)
        return (int(match.group(1)), match.group(2)) if match else None

    def index_of_key(self, param_key: str) -> int | None:
        """The sensor index a key of this preset's shape carries, else None."""
        parts = self.split_key(param_key)
        return parts[0] if parts else None

    def index_of_device(self, device_id: str) -> int | None:
        """The sensor index a device id of this preset's shape carries, else None."""
        match = re.match(rf"^{re.escape(self.device_prefix)}(\d+)$", device_id)
        return int(match.group(1)) if match else None


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
        readings=tuple(PresetReading(*row) for row in mopeka.READINGS),
        storage_interval_seconds=mopeka.STORAGE_INTERVAL_SECONDS,
    )
}
