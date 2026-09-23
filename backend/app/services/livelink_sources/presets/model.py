"""What a preset is: one kind of sensor, and the readings it publishes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

#: How the Live tab and the settings drawer show a reading's value.
#: `value` goes through the unit adapter; `boolean` reads Yes or No; `count` is
#: a whole number; `of_max` is "3 of 3" against `PresetReading.max_value`.
ReadingFormat = Literal["value", "boolean", "count", "of_max"]

#: An alert line Settings can offer on a reading: `low` is `warning_min`,
#: `critical` is `critical_min`.
AlertLine = Literal["low", "critical"]


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
    format: ReadingFormat = "value"
    #: The top of the scale for an `of_max` reading.
    max_value: int | None = None
    #: The alert lines a new sensor starts with, which its owner can move or
    #: switch off in Settings: below `low` warns, below `critical` is urgent.
    #: None means the reading offers no such line.
    low: float | None = None
    critical: float | None = None

    @property
    def alert_lines(self) -> tuple[AlertLine, ...]:
        """The lines Settings offers for this reading, in the order it shows them."""
        offered: list[AlertLine] = []
        if self.low is not None:
            offered.append("low")
        if self.critical is not None:
            offered.append("critical")
        return tuple(offered)


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
    #: The reading the Live tab draws as the tank's fill, if the preset has one.
    fill_suffix: str | None = None

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

    def reading(self, suffix: str) -> PresetReading | None:
        """The reading with this suffix, if the preset has one."""
        return next((r for r in self.readings if r.suffix == suffix), None)

    def reading_of_key(self, param_key: str) -> PresetReading | None:
        """The reading a key of this preset's shape is, if the preset has it."""
        parts = self.split_key(param_key)
        return self.reading(parts[1]) if parts else None
