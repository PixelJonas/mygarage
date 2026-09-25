"""Unit tests for the propane refill rate, the towable card's fuel-economy analog.

A trailer has no odometer, so its consumption is volume over TIME rather than
over distance: the litres put in after the first refill, spread over the days
between the first and the last refill, scaled to a month.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.fuel import FuelRecord
from app.services.fuel_service import propane_fills, propane_l_per_month

D0 = date(2026, 1, 1)


def _fill(days: int, liters: str) -> tuple[date, Decimal]:
    return (D0 + timedelta(days=days), Decimal(liters))


@pytest.mark.unit
@pytest.mark.fuel
class TestPropaneLitersPerMonth:
    def test_fewer_than_two_fills_has_no_rate(self):
        assert propane_l_per_month([]) is None
        assert propane_l_per_month([_fill(0, "30")]) is None

    def test_thirty_liters_over_thirty_days_is_one_average_month(self):
        # 30 L / 30 days * 30.4375 days per month.
        assert propane_l_per_month([_fill(0, "30"), _fill(30, "30")]) == Decimal("30.44")

    def test_the_first_fill_only_starts_the_clock(self):
        # Its volume was burned BEFORE the window, exactly like the first full
        # tank in a distance economy.
        assert propane_l_per_month([_fill(0, "100"), _fill(30, "30")]) == Decimal("30.44")

    def test_a_partial_refill_counts_by_its_volume(self):
        # 8.5 L over 60 days: a top-up is not a whole tank.
        assert propane_l_per_month([_fill(0, "29.46"), _fill(60, "8.5")]) == Decimal("4.31")

    def test_same_day_fills_have_no_span(self):
        assert propane_l_per_month([_fill(0, "30"), _fill(0, "30")]) is None


@pytest.mark.unit
@pytest.mark.fuel
class TestPropaneFills:
    def _record(self, days: int, **fields) -> FuelRecord:
        return FuelRecord(vin="4EZFD3821P6080615", date=D0 + timedelta(days=days), **fields)

    def test_keeps_only_bottle_refills_in_date_order(self):
        records = [
            self._record(30, propane_liters=Decimal("29.46")),
            self._record(0, propane_liters=Decimal("29.46")),
            # A propane-POWERED vehicle's fill-up carries liters or kwh too: not a bottle.
            self._record(10, propane_liters=Decimal("40"), liters=Decimal("40")),
            self._record(15, propane_liters=Decimal("40"), kwh=Decimal("10")),
            self._record(20, liters=Decimal("50")),
            self._record(40, propane_liters=None),
        ]
        assert propane_fills(records) == [_fill(0, "29.46"), _fill(30, "29.46")]
