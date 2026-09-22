# LiveLink (WiCAN) Setup

MyGarage ingests real-time vehicle telemetry from [WiCAN](https://github.com/meatpiHQ/wican-fw)
devices. WiCAN PRO with firmware **v4.40 or newer** is required.

## Webhook (HTTPS) ingestion

Point your WiCAN device's webhook at MyGarage's ingest endpoint:

- **Webhook URL:** `https://<your-mygarage-host>/api/v1/livelink/ingest`
- **Method:** `POST`
- **Auth:** include the per-device token issued in MyGarage
  (Settings → Integrations → LiveLink → Configure → device token).

The endpoint returns `202 Accepted` immediately and queues the payload for
async processing.

## Primary + failover webhook (firmware v4.49 / v4.50p)

Recent PRO firmware supports a **primary** and a **failover** webhook URL.
Both may target MyGarage for delivery resilience — if the primary path fails,
the device retries the failover. Configure either or both fields in the
device's web UI to the ingest URL above; MyGarage deduplicates replays, so a
payload delivered via both paths is stored once.

## MQTT ingestion (alternative)

If you run an MQTT broker, MyGarage can subscribe instead of receiving
webhooks. See Settings → Integrations → LiveLink → MQTT.

## Generic MQTT sources

WiCAN and Torque parse their own wire formats in code. Any other MQTT device is
described by rows in `livelink_topic_maps` instead, so adding one is a Settings
task rather than a pull request.

Settings → Integrations → MQTT sources.

### 1. Create the device

A generic MQTT device cannot appear on its own: it has no auto-discovery (unlike
WiCAN, which announces itself) and no token flow (unlike Torque). Create it with
a device ID, an optional label and an optional vehicle. Leaving the vehicle
unset is fine; the device stores nothing until it is linked, exactly like a
freshly discovered WiCAN dongle.

### 2. Find out what it publishes

**Discover** subscribes to a prefix for a few seconds and lists the topics it
saw with one sample payload each. It is bounded server-side: 60 seconds maximum,
500 distinct topics, 256-byte samples, one run at a time, admin only. It uses
its own short-lived connection, so the live subscription set is untouched.

### 3. Map a topic to a parameter

| Field | Meaning |
|---|---|
| Topic | **Exact**, never a wildcard. `+` and `#` are rejected. |
| Parameter key | Where the value is stored. Prefilled from the topic's last segment, uppercased. |
| Unit / class | Display metadata, copied onto the parameter. |
| Value path | Leave empty for a bare scalar payload (`71`). Set a dotted path (`battery.voltage`) to read one value out of a JSON payload. |
| Scale / offset | `value = raw * scale + offset`. This is where unit conversion happens. |
| Role | `telemetry` stores a reading. `status` marks the device online/offline, for an LWT topic. |

Topics are exact by design. Subscriptions then are just the distinct topic
values, dispatch is a dictionary lookup, and there is no way to configure a `#`
that firehoses the broker into the database.

**One topic belongs to one device.** Mapping the same topic under a second
device is rejected with a conflict, because a batch is attributed to a single
device and the alternative is writing one device's readings against another
device's vehicle.

### Payloads that are not numbers

`ON`, `TRUE`, `ONLINE`, `OPEN`, `YES` and `1` become 1.0; `OFF`, `FALSE`,
`OFFLINE`, `CLOSED`, `NO` and `0` become 0.0. Anything else is dropped.

A payload that is neither numeric nor boolean **cannot be mapped at all**:
`vehicle_telemetry.value` is a float. An IP address published on a diagnostics
topic is a common example, and the discovery list flags samples like that.

### Set a storage interval

This is required, not tuning. Mapped topics are usually retained, and retained
messages replay on every resubscribe while the storage path stamps server time,
so without an interval each reconnect writes a fresh row. Setting
`storage_interval_seconds` on the parameter also decides how much history you
keep: at 300 seconds, a device publishing every 10 seconds stores about 288 rows
per parameter per day instead of 8,640.

### Presets

A preset creates the device and all of its mappings in one action, and sets the
storage interval on every parameter.

`mopeka_two_tank` covers two Mopeka Pro Check sensors on 30 lb bottles published
by an ESPHome gateway: 17 topics, no code. Reading its values:

- Signal quality gates only `level_percent` and `depth_mm`. Temperature and
  battery publish regardless, so `availability` means "radio heard from", not
  "measurement valid".
- `PROPANE_Tn_REJECTED > 0` is the real "this retained level is stale" flag.
- `availability` is not cleared when the gateway dies. Read it together with the
  gateway's own status topic.
- A 30 lb bottle calibrates empty at 38 mm and full at 381 mm, and a full bottle
  reads 395 to 400 mm. It is therefore **saturated at 100%** and the first few
  percent of consumption is invisible.

### What a generic source deliberately cannot do

It declares telemetry only. It cannot open a drive session, and that is
structural rather than a guard: the ingest pipeline has no code path reaching
session handling for a module that does not declare the capability. A propane
sensor on a parked trailer reporting every few seconds will never manufacture a
drive.
