"""Two Mopeka Pro Check sensors on 30 lb bottles, via an ESPHome gateway.

Every topic is a bare scalar at a fixed path, which is why this device needs
no ingest code at all: it is seventeen rows in livelink_topic_maps.

Semantics worth knowing when reading these values (verified against the
gateway's component source, not assumed):

- `minimum_signal_quality: MEDIUM` gates ONLY level_percent and depth_mm.
  Temperature and battery publish on every packet, so `availability` means
  "radio heard from", not "measurement valid".
- PROPANE_Tn_REJECTED > 0 is the real "the retained level is stale" flag.
- `availability` is not cleared when the gateway dies. AND it with
  RV_GATEWAY_ONLINE.
- 30LB_V calibrates empty at 38 mm and full at 381 mm. A full bottle reads
  395-400 mm, so it is SATURATED at 100% and the first ~4% of consumption is
  invisible. Burn-rate maths must account for a flat top.

`mygarage/rv/gateway/ip` is deliberately absent: vehicle_telemetry.value is a
Float and an IP address is not a number.
"""

from __future__ import annotations

#: Seconds between persisted samples. REQUIRED, not tuning: retained messages
#: replay on every resubscribe and the storage path stamps server time, so
#: without this each reconnect writes a fresh row. Turns ~79,000 messages/day
#: into ~4,608 stored rows/day, about 415,000 at the 90-day retention.
STORAGE_INTERVAL_SECONDS = 300

_PER_TANK = [
    ("level_percent", "LEVEL_PCT", "%", "propane"),
    ("depth_mm", "DEPTH_MM", "mm", "propane"),
    ("temperature_c", "TEMP_C", "C", "temperature"),
    ("battery_percent", "SENSOR_BATT_PCT", "%", "battery"),
    ("reading_quality", "QUALITY", None, "diagnostic"),
    ("rejected_readings", "REJECTED", None, "diagnostic"),
    ("availability", "AVAILABLE", None, "diagnostic"),
]


def _rows() -> list[dict]:
    """The seventeen mapping rows: 14 propane, 2 gateway, 1 status."""
    rows: list[dict] = [
        {
            "topic": "mygarage/rv/status",
            "role": "status",
            "param_key": None,
            "unit": None,
            "param_class": None,
        }
    ]
    for tank in (1, 2):
        for suffix, key, unit, klass in _PER_TANK:
            rows.append(
                {
                    "topic": f"mygarage/rv/propane/tank{tank}/{suffix}",
                    "role": "telemetry",
                    "param_key": f"PROPANE_T{tank}_{key}",
                    "unit": unit,
                    "param_class": klass,
                }
            )
    rows.append(
        {
            "topic": "mygarage/rv/gateway/wifi_rssi",
            "role": "telemetry",
            "param_key": "RV_GATEWAY_RSSI",
            "unit": "dBm",
            "param_class": "signal",
        }
    )
    rows.append(
        {
            "topic": "mygarage/rv/gateway/uptime_seconds",
            "role": "telemetry",
            "param_key": "RV_GATEWAY_UPTIME_S",
            "unit": "s",
            "param_class": "diagnostic",
        }
    )
    return rows


ROWS = _rows()
