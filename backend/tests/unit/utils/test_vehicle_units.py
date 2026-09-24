"""The per-vehicle distance rule (#172): distance and speed follow the vehicle,
nothing else does, and an unset or unusable value changes nothing."""

from __future__ import annotations

import logging

import pytest
from pydantic import BaseModel

from app.constants.units import IMPERIAL_PRESET, METRIC_PRESET
from app.utils import unit_resolution
from app.utils.unit_resolution import (
    LenientDistanceUnit,
    apply_vehicle_units,
    normalise_distance_unit,
)


class TestApplyVehicleUnits:
    @pytest.mark.parametrize("unset", [None, "", "MI", "miles", 7])
    def test_unset_or_unusable_returns_the_same_object(self, unset: object) -> None:
        assert apply_vehicle_units(METRIC_PRESET, unset) is METRIC_PRESET

    def test_mi_sets_distance_and_speed_only(self) -> None:
        out = apply_vehicle_units(METRIC_PRESET, "mi")
        assert (out.distance, out.speed) == ("mi", "mph")
        assert out.model_dump() | {"distance": "km", "speed": "kmh"} == METRIC_PRESET.model_dump()

    def test_km_sets_distance_and_speed_only(self) -> None:
        out = apply_vehicle_units(IMPERIAL_PRESET, "km")
        assert (out.distance, out.speed) == ("km", "kmh")
        assert out.volume == "gal_us" and out.consumption == "mpg_us"

    def test_a_mismatched_account_is_overridden_on_both_fields(self) -> None:
        odd = METRIC_PRESET.model_copy(update={"speed": "mph"})
        out = apply_vehicle_units(odd, "km")
        assert (out.distance, out.speed) == ("km", "kmh")


class TestNormalise:
    def test_in_vocabulary_passes_through(self) -> None:
        assert normalise_distance_unit("km") == "km"
        assert normalise_distance_unit("mi") == "mi"
        assert normalise_distance_unit(None) is None

    def test_a_bad_value_warns_once_per_vin_and_value(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(unit_resolution, "_warned_distance_units", set())
        with caplog.at_level(logging.WARNING, logger="app.utils.unit_resolution"):
            for _ in range(3):
                assert normalise_distance_unit("MI", vin="V1") is None
            assert normalise_distance_unit("MI", vin="V2") is None
            assert normalise_distance_unit("miles") is None
        messages = [r.getMessage() for r in caplog.records]
        assert len(messages) == 3
        assert any("V2" in m for m in messages)


class _Carrier(BaseModel):
    vin: str
    distance_unit: LenientDistanceUnit = None


def test_the_lenient_type_serves_a_bad_row_as_null_and_names_the_vin(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(unit_resolution, "_warned_distance_units", set())
    with caplog.at_level(logging.WARNING, logger="app.utils.unit_resolution"):
        assert (
            _Carrier.model_validate({"vin": "VBAD1", "distance_unit": "MI"}).distance_unit is None
        )
    assert _Carrier.model_validate({"vin": "VOK", "distance_unit": "mi"}).distance_unit == "mi"
    assert "VBAD1" in caplog.records[0].getMessage()
