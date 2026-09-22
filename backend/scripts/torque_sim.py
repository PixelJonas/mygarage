#!/usr/bin/env python3
"""Replay a scripted Torque Pro drive against a MyGarage instance.

Torque uploads are plain HTTP GETs with `k<hex>` query parameters, so a drive
is a list of dicts and a loop. No phone, no vehicle, no Bluetooth.

Exists because nobody on this project owns a Torque device: the feature was
requested by a user. It gives the Torque ingest path end-to-end coverage it has
never had, and gives that user a reproducible way to report a bug.

PID references (see app/services/torque_pid_map.py):
    k0c     engine RPM            k0d     speed
    k05     coolant temperature   k11     throttle
    kff1006 latitude              kff1005 longitude
    kff1001 GPS speed             kff1007 heading
    kff120c "Vehicle distance (Odometer) saved with profile"

Note on kff120c: that is Torque's OWN accumulated total, kept against the app
profile, not a reading of the vehicle's ECU. It is only as accurate as the
phone's trip coverage. A true odometer needs a vehicle-specific custom PID.
Either way it arrives as an ordinary named parameter, which is why Task 17
makes the odometer parameter a per-device SETTING rather than something
MyGarage tries to infer from the name.

`print()` is used deliberately here and is the one carve-out from the global
"never print()" rule: this is an operator CLI whose entire output contract is
stdout, not a service. It is never imported by application code. If the rule is
enforced by a linter, silence it at this module with a scoped noqa rather than
routing operator output through `logging`.

Usage:
    cd backend && python -m scripts.torque_sim --base-url http://localhost:8686 --token <tok>
"""

from __future__ import annotations

import argparse
import time
from typing import Any

#: Straight-line track heading north out of Portland.
_START_LAT, _START_LON = 45.5200, -122.6700


def build_drive(
    session_id: str,
    minutes: int = 10,
    start_odometer_mi: float = 90170.0,
    interval_s: int = 10,
    start_ms: int | None = None,
) -> list[dict[str, Any]]:
    """One drive as an ordered list of Torque upload query dicts.

    Speed ramps up, holds, then ramps down, so movement detection sees a real
    profile rather than a step function. The odometer advances consistently
    with that speed, so a Task 17 odometer selection has something truthful to
    read.
    """
    if minutes < 1:
        raise ValueError("minutes must be >= 1")
    # Default the drive into the PAST. `routes/torque.py:100` clamps a future
    # device clock with `ts = min(candidate, now)`, so starting at "now" would
    # stamp every frame after the first at server-now: the replayed drive would
    # collapse to ~0 duration and the legitimate past-replay branch would never
    # be exercised.
    if start_ms is None:
        start_ms = int((time.time() - minutes * 60) * 1000)
    steps = max(2, (minutes * 60) // interval_s)
    frames: list[dict[str, Any]] = []
    odometer = float(start_odometer_mi)
    lat, lon = _START_LAT, _START_LON

    for i in range(steps):
        progress = i / (steps - 1)
        if progress < 0.2:
            speed_kmh = 60.0 * (progress / 0.2)
        elif progress > 0.8:
            speed_kmh = 60.0 * ((1.0 - progress) / 0.2)
        else:
            speed_kmh = 60.0

        odometer += (speed_kmh / 1.609344) * (interval_s / 3600.0)
        lat += (speed_kmh / 3600.0) * interval_s / 111.0

        frames.append(
            {
                "session": session_id,
                "time": str(start_ms + i * interval_s * 1000),
                "k0c": f"{800 + speed_kmh * 30:.0f}",
                "k0d": f"{speed_kmh:.0f}",
                "k05": f"{70 + progress * 20:.0f}",
                "k11": f"{10 + speed_kmh / 3:.0f}",
                "kff120c": f"{odometer:.1f}",
                "kff1006": f"{lat:.6f}",
                "kff1005": f"{lon:.6f}",
                "kff1001": f"{speed_kmh:.0f}",
                "kff1007": "0",
            }
        )
    return frames


def replay(base_url: str, token: str, frames: list[dict[str, Any]], pace: float = 0.0) -> None:
    """GET each frame at the real endpoint, printing any non-OK response."""
    import urllib.parse
    import urllib.request

    for i, frame in enumerate(frames, 1):
        url = f"{base_url.rstrip('/')}/api/v1/torque/{token}/upload?" + urllib.parse.urlencode(
            frame
        )
        with urllib.request.urlopen(url) as resp:  # noqa: S310 - operator-supplied local URL
            body = resp.read().decode()
        if body != "OK!":
            print(f"frame {i}: unexpected response {resp.status} {body!r}")
        if pace:
            time.sleep(pace)
    print(f"replayed {len(frames)} frames")


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8686")
    parser.add_argument("--token", required=True)
    parser.add_argument("--session-id", default=str(int(time.time())))
    parser.add_argument("--minutes", type=int, default=10)
    parser.add_argument("--start-odometer", type=float, default=90170.0)
    parser.add_argument("--pace", type=float, default=0.0, help="seconds between frames")
    args = parser.parse_args()

    replay(
        args.base_url,
        args.token,
        build_drive(
            session_id=args.session_id,
            minutes=args.minutes,
            start_odometer_mi=args.start_odometer,
        ),
        pace=args.pace,
    )


if __name__ == "__main__":
    main()
