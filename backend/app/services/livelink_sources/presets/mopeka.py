"""One Mopeka Pro Check propane sensor.

Mopeka sensors speak only Bluetooth. Something nearby (an ESP32 running
ESPHome, a Home Assistant bridge, another gateway) hears them and republishes
each reading to MQTT, and that relay is transport, like the broker: each sensor
is its own device. Where a gateway publishes is its owner's choice, so a sensor
is added from its level topic and the other readings' topics are suggested from
it, not assumed.

Semantics worth knowing when reading these values (verified against the
operator's ESPHome gateway, the reference layout the default topic names come
from):

- The gateway's `minimum_signal_quality` gates ONLY the level and depth.
  Temperature and battery publish on every packet, so "sensor heard" means the
  radio was heard, not that the measurement is valid.
- Rejected readings > 0 is the real "the retained level is stale" flag.
- "Sensor heard" is not cleared when the gateway itself dies.
- A 30 lb bottle calibrated empty at 38 mm and full at 381 mm reads 395-400 mm
  when full, so the level is SATURATED at 100% and the first few percent of
  consumption are invisible. Burn-rate maths must allow for a flat top.
"""

from __future__ import annotations

#: Seconds between persisted samples. REQUIRED, not tuning: retained messages
#: replay on every resubscribe and the storage path stamps server time, so
#: without this each reconnect writes a fresh row.
STORAGE_INTERVAL_SECONDS = 300

#: (suffix, name, unit, param_class, default topic, keywords, required), in the
#: order a sensor's readings are shown. Keywords are lowercase substrings that
#: identify a reading's topic segment in any layout.
READINGS: tuple[tuple[str, str, str | None, str, str, tuple[str, ...], bool], ...] = (
    ("LEVEL_PCT", "level", "%", "propane", "level_percent", ("level",), True),
    ("TEMP_C", "temperature", "C", "temperature", "temperature_c", ("temp",), False),
    ("SENSOR_BATT_PCT", "battery", "%", "battery", "battery_percent", ("batt",), False),
    (
        "QUALITY",
        "reading quality",
        None,
        "diagnostic",
        "reading_quality",
        ("quality", "signal"),
        False,
    ),
    ("DEPTH_MM", "depth", "mm", "propane", "depth_mm", ("depth", "distance"), False),
    (
        "REJECTED",
        "rejected readings",
        None,
        "diagnostic",
        "rejected_readings",
        ("reject", "ignored"),
        False,
    ),
    ("AVAILABLE", "sensor heard", None, "diagnostic", "availability", ("avail", "heard"), False),
)
