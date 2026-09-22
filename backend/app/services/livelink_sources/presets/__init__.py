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
    #: param_key to operator-facing name. Kept apart from `rows` because each
    #: row is splatted straight into LiveLinkTopicMap(**row).
    display_names: dict[str, str]


PRESETS: dict[str, Preset] = {
    "mopeka_two_tank": Preset(
        name="mopeka_two_tank",
        title="Mopeka",
        # Shown to the operator as the tab's description and in the Add-source
        # catalogue, which prints the topic count on its own line.
        # No bottle size: the 30 lb calibration is the gateway's setting, not
        # anything MyGarage does. "Two" stays while the preset maps exactly two.
        description="Two Mopeka Pro Check propane sensors, published by an ESPHome gateway.",
        kind="generic_mqtt",
        rows=mopeka_two_tank.ROWS,
        storage_interval_seconds=mopeka_two_tank.STORAGE_INTERVAL_SECONDS,
        display_names=mopeka_two_tank.DISPLAY_NAMES,
    )
}
