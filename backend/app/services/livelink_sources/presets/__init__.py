"""Named bundles that create a device and its topic maps in one action.

Data in code. Not user-authored and not dynamically imported: MyGarage is a
public repository and executing supplied code is a security surface three
sources do not justify.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.livelink_sources.presets import mopeka_two_tank


@dataclass(frozen=True)
class Preset:
    """One device template."""

    name: str
    title: str
    description: str
    kind: str
    rows: list[dict]
    storage_interval_seconds: int


PRESETS: dict[str, Preset] = {
    "mopeka_two_tank": Preset(
        name="mopeka_two_tank",
        title="Mopeka propane (2 tanks)",
        # Shown to the operator as the tab's description and in the Add-source
        # catalogue, which prints the topic count on its own line.
        description=(
            "Two Mopeka Pro Check sensors on 30 lb bottles, published by an ESPHome gateway."
        ),
        kind="generic_mqtt",
        rows=mopeka_two_tank.ROWS,
        storage_interval_seconds=mopeka_two_tank.STORAGE_INTERVAL_SECONDS,
    )
}
