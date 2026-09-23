"""When a reading's alert lines notify: the band a value is in, and the
notify-once crossing a preset sensor's readings use.

A tank sits below its low line for days, so a cooldown would repeat the same
alert every half hour until the refill. Once per crossing instead: notify on
entering a band, again only for a worse one, and re-arm only after the value
climbs clear of the line.
"""

from dataclasses import dataclass

import pytest

from app.services.livelink_alerts import REARM_MARGIN, alert_band, band_line, crossing


@dataclass
class Lines:
    warning_min: float | None = None
    critical_min: float | None = None
    warning_max: float | None = None


TANK = Lines(warning_min=25.0, critical_min=10.0)
BATTERY = Lines(warning_min=20.0)


@pytest.mark.unit
class TestAlertBand:
    @pytest.mark.parametrize(
        ("value", "band"),
        [
            (72.0, None),
            (25.0, None),
            (24.9, "low"),
            (10.0, "low"),
            (9.9, "critical"),
            (0.0, "critical"),
        ],
    )
    def test_a_tank(self, value, band):
        assert alert_band(value, TANK) == band

    def test_critical_alone_is_still_a_line(self):
        assert alert_band(5.0, Lines(critical_min=10.0)) == "critical"
        assert alert_band(15.0, Lines(critical_min=10.0)) is None

    def test_high(self):
        lines = Lines(warning_max=100.0)
        assert alert_band(100.1, lines) == "high"
        assert alert_band(100.0, lines) is None

    def test_no_lines_no_band(self):
        assert alert_band(-1000.0, Lines()) is None


@pytest.mark.unit
class TestBandLine:
    def test_each_band_names_its_line(self):
        lines = Lines(warning_min=25.0, critical_min=10.0, warning_max=90.0)
        assert [band_line(b, lines) for b in ("low", "critical", "high")] == [25.0, 10.0, 90.0]

    def test_a_band_without_its_line_is_an_error(self):
        with pytest.raises(ValueError):
            band_line("critical", Lines(warning_min=25.0))


@pytest.mark.unit
class TestCrossing:
    def test_dropping_below_low_notifies_low(self):
        assert crossing(None, 24.0, TANK) == ("low", None)

    def test_staying_below_low_is_silent(self):
        assert crossing("low", 22.0, TANK) == (None, "low")

    def test_falling_below_critical_notifies_once_more(self):
        assert crossing("low", 9.0, TANK) == ("critical", "low")

    def test_staying_below_critical_is_silent(self):
        assert crossing("critical", 5.0, TANK) == (None, "critical")

    def test_straight_to_critical_skips_low(self):
        assert crossing(None, 5.0, TANK) == ("critical", None)

    def test_climbing_back_between_the_lines_is_silent_and_stays_critical(self):
        """A partial recovery is not a refill: back below critical must not
        notify again."""
        assert crossing("critical", 20.0, TANK) == (None, "critical")

    def test_jitter_just_above_the_line_keeps_the_state(self):
        assert crossing("low", 25.0 + REARM_MARGIN - 0.1, TANK) == (None, "low")
        assert crossing("critical", 26.0, TANK) == (None, "critical")

    def test_clearing_the_low_line_by_the_margin_rearms(self):
        assert crossing("low", 25.0 + REARM_MARGIN, TANK) == (None, None)
        assert crossing("critical", 100.0, TANK) == (None, None)

    def test_after_rearming_the_next_drop_notifies_again(self):
        notify, state = crossing("critical", 100.0, TANK)
        assert (notify, state) == (None, None)
        assert crossing(state, 24.0, TANK) == ("low", None)

    def test_a_critical_line_alone_rearms_against_itself(self):
        lines = Lines(critical_min=10.0)
        assert crossing("critical", 10.0 + REARM_MARGIN - 0.1, lines) == (None, "critical")
        assert crossing("critical", 10.0 + REARM_MARGIN, lines) == (None, None)

    def test_clearing_every_line_rearms(self):
        """Someone switched the alerts off while one was held."""
        assert crossing("low", 3.0, Lines()) == (None, None)

    def test_the_battery(self):
        assert crossing(None, 19.0, BATTERY) == ("low", None)
        assert crossing("low", 5.0, BATTERY) == (None, "low")
        assert crossing("low", 20.0 + REARM_MARGIN, BATTERY) == (None, None)

    def test_high_notifies_once_and_rearms_below_the_line(self):
        lines = Lines(warning_max=60.0)
        assert crossing(None, 61.0, lines) == ("high", None)
        assert crossing("high", 70.0, lines) == (None, "high")
        assert crossing("high", 60.0 - REARM_MARGIN + 0.1, lines) == (None, "high")
        assert crossing("high", 60.0 - REARM_MARGIN, lines) == (None, None)

    def test_high_line_gone_rearms(self):
        assert crossing("high", 70.0, Lines(warning_min=10.0)) == (None, None)

    def test_the_other_direction_notifies(self):
        lines = Lines(warning_min=10.0, warning_max=60.0)
        assert crossing("high", 5.0, lines) == ("low", "high")
        assert crossing("low", 61.0, lines) == ("high", "low")
