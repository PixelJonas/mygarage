"""`validate_period_history`: the write-side twin of the projection's guards.

The projection suppresses a figure when a tire's periods contradict each
other. Until this validator, the same contradictions could be WRITTEN: a
dismount dated before its own mount, a remount at an odometer below the last
dismount. With dates on every dialog those shapes become reachable from the
UI, so they are refused at write time instead.

Every rule has a fixture that passes without it. Kill check per rule: delete
the rule, the test named for it fails.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.models.tire import TireMountPeriod, TireReading
from app.services.tire_history import (
    CONTRADICTS_READING,
    OVERLAPPING_DATES,
    OVERLAPPING_ODOMETER,
    REVERSED_DATES,
    REVERSED_ODOMETER,
    PeriodFault,
    fault_map,
    new_or_touched_faults,
    validate_period_history,
)

D = dt.date


def _period(
    pid: int,
    *,
    start: D | None,
    end: D | None,
    start_odo: str | None,
    end_odo: str | None,
    position: str = "FL",
) -> TireMountPeriod:
    return TireMountPeriod(
        id=pid,
        position=position,
        mounted_on=start,
        dismounted_on=end,
        mounted_odometer_km=None if start_odo is None else Decimal(start_odo),
        dismounted_odometer_km=None if end_odo is None else Decimal(end_odo),
        is_assumed=False,
        observed_active_on=None,
    )


def _reading(day: D, odo: str) -> TireReading:
    return TireReading(recorded_at=day, odometer_km=Decimal(odo), tread_depth_mm=Decimal("5.0"))


def _codes(faults) -> list[tuple[int, str]]:
    return [(f.period_id, f.code) for f in faults]


class TestSingleRules:
    def test_reversed_dates(self):
        p = _period(1, start=D(2026, 4, 10), end=D(2026, 3, 1), start_odo="1000", end_odo="2000")
        assert _codes(validate_period_history([p], [])) == [(1, REVERSED_DATES)]

    def test_reversed_odometer(self):
        p = _period(1, start=D(2026, 1, 1), end=D(2026, 3, 1), start_odo="5000", end_odo="4000")
        assert _codes(validate_period_history([p], [])) == [(1, REVERSED_ODOMETER)]

    def test_a_period_starting_before_the_previous_dismount_date(self):
        p = _period(1, start=D(2026, 1, 1), end=D(2026, 3, 1), start_odo="1000", end_odo="2000")
        q = _period(2, start=D(2026, 2, 15), end=D(2026, 5, 1), start_odo="2000", end_odo="3000")
        faults = validate_period_history([q, p], [])  # order of input must not matter
        assert _codes(faults) == [(2, OVERLAPPING_DATES)]
        # The fault names the intruding period first.
        assert faults[0].message.startswith("period 2")

    def test_a_period_starting_while_an_earlier_one_is_still_open(self):
        p = _period(1, start=D(2026, 1, 1), end=None, start_odo="1000", end_odo=None)
        q = _period(2, start=D(2026, 2, 1), end=D(2026, 3, 1), start_odo="1500", end_odo="1800")
        assert _codes(validate_period_history([p, q], [])) == [(2, OVERLAPPING_DATES)]

    def test_a_mount_odometer_below_an_earlier_dismount(self):
        p = _period(1, start=D(2026, 1, 1), end=D(2026, 3, 1), start_odo="1000", end_odo="2000")
        q = _period(2, start=D(2026, 4, 1), end=None, start_odo="1900", end_odo=None)
        assert _codes(validate_period_history([p, q], [])) == [(2, OVERLAPPING_ODOMETER)]

    def test_a_later_remount_below_an_earlier_dismount_is_caught_in_date_order(self):
        """Plan review R2-H1. A sweep sorted by odometer alone puts the 500 first
        and sees nothing; chronology is what makes this a contradiction."""
        p = _period(1, start=D(2026, 1, 1), end=D(2026, 1, 31), start_odo="1000", end_odo="2000")
        q = _period(2, start=D(2026, 3, 1), end=None, start_odo="500", end_odo=None)
        faults = validate_period_history([q, p], [])
        assert _codes(faults) == [(2, OVERLAPPING_ODOMETER)]
        assert faults[0].counterpart_id == 1

    def test_two_undated_spans_that_intersect_are_a_fault_regardless_of_order(self):
        """The order-free form: a tire cannot be in two places at once."""
        p = _period(1, start=None, end=None, start_odo="1000", end_odo="3000")
        q = _period(2, start=None, end=None, start_odo="2000", end_odo="4000")
        faults = validate_period_history([p, q], [])
        assert _codes(faults) == [(2, OVERLAPPING_ODOMETER)]
        assert faults[0].counterpart_id == 1

    def test_a_period_nested_by_odometer_inside_a_non_adjacent_earlier_one(self):
        """Running maximum, not the neighbour: p3 is inside p1, two places back."""
        p1 = _period(1, start=D(2025, 1, 1), end=D(2025, 6, 1), start_odo="0", end_odo="30000")
        p2 = _period(2, start=D(2025, 7, 1), end=D(2025, 8, 1), start_odo="30000", end_odo="31000")
        p3 = _period(3, start=D(2025, 9, 1), end=None, start_odo="20000", end_odo=None)
        assert _codes(validate_period_history([p1, p2, p3], [])) == [(3, OVERLAPPING_ODOMETER)]


class TestReadingsContradictPeriods:
    """The four monotonicity implications, one fixture each. Strict dates."""

    P = _period(1, start=D(2026, 1, 1), end=D(2026, 3, 1), start_odo="1000", end_odo="5000")

    def test_after_dismount_below_dismount_odometer(self):
        assert _codes(validate_period_history([self.P], [_reading(D(2026, 4, 1), "4000")])) == [
            (1, CONTRADICTS_READING)
        ]

    def test_before_mount_above_mount_odometer(self):
        assert _codes(validate_period_history([self.P], [_reading(D(2025, 12, 1), "2000")])) == [
            (1, CONTRADICTS_READING)
        ]

    def test_after_mount_below_mount_odometer(self):
        assert _codes(validate_period_history([self.P], [_reading(D(2026, 2, 1), "500")])) == [
            (1, CONTRADICTS_READING)
        ]

    def test_before_dismount_above_dismount_odometer(self):
        assert _codes(validate_period_history([self.P], [_reading(D(2026, 2, 15), "6000")])) == [
            (1, CONTRADICTS_READING)
        ]


class TestShapesThatMustPass:
    def test_same_day_dismount_and_remount_at_the_same_odometer(self):
        """A rotation: touching endpoints on both axes are not an overlap."""
        p = _period(1, start=D(2026, 1, 1), end=D(2026, 3, 1), start_odo="1000", end_odo="5000")
        q = _period(2, start=D(2026, 3, 1), end=None, start_odo="5000", end_odo=None, position="FR")
        assert validate_period_history([p, q], [_reading(D(2026, 2, 1), "3000")]) == []

    def test_an_assumed_period_with_unknown_start_followed_by_a_bounded_one(self):
        """The migrated shape. Unknown is a gap, never a fault."""
        p = _period(1, start=None, end=D(2026, 1, 15), start_odo=None, end_odo="3000")
        q = _period(2, start=D(2026, 1, 15), end=None, start_odo="3000", end_odo=None)
        assert validate_period_history([q, p], []) == []

    def test_clearing_a_later_open_periods_mount_date_is_not_an_overlap(self):
        """Plan review R1-M1. Sorting an unknown date as earliest put the open
        period first and made every closed period "start while it is open"."""
        p = _period(1, start=D(2026, 1, 1), end=D(2026, 3, 1), start_odo="1000", end_odo="2000")
        q = _period(2, start=None, end=None, start_odo="2500", end_odo=None)
        assert validate_period_history([p, q], []) == []

    def test_an_unknown_start_never_constrains_a_dated_period(self):
        p = _period(1, start=None, end=D(2026, 1, 15), start_odo=None, end_odo="3000")
        q = _period(2, start=D(2025, 12, 1), end=D(2026, 1, 10), start_odo="2500", end_odo="2800")
        assert validate_period_history([p, q], []) == []

    def test_a_lone_open_period_and_an_empty_history(self):
        assert (
            validate_period_history(
                [_period(1, start=D(2026, 1, 1), end=None, start_odo=None, end_odo=None)], []
            )
            == []
        )
        assert validate_period_history([], []) == []

    def test_one_fault_per_period_and_code(self):
        """A period that is reversed on both axes reports two faults, not four."""
        p = _period(1, start=D(2026, 4, 1), end=D(2026, 3, 1), start_odo="5000", end_odo="4000")
        assert sorted(_codes(validate_period_history([p], []))) == sorted(
            [(1, REVERSED_DATES), (1, REVERSED_ODOMETER)]
        )


class TestIncrementalPolicy:
    """Plan review R1-M2 and R2-M1: a write refuses what it introduced, and any
    persisting fault that one of its touched periods participates in."""

    OLD = PeriodFault(1, REVERSED_ODOMETER, "old")
    NEW = PeriodFault(2, OVERLAPPING_DATES, "new")
    PAIR = PeriodFault(2, OVERLAPPING_DATES, "pair", counterpart_id=1)

    def test_a_pre_existing_fault_on_an_untouched_period_survives(self):
        before = {self.OLD.key: self.OLD}
        assert new_or_touched_faults(before, dict(before), touched={2}) == []

    def test_a_pre_existing_fault_on_a_touched_period_refuses(self):
        before = {self.OLD.key: self.OLD}
        assert new_or_touched_faults(before, dict(before), touched={1}) == [self.OLD]

    def test_a_new_fault_anywhere_refuses(self):
        before = {self.OLD.key: self.OLD}
        after = {**before, self.NEW.key: self.NEW}
        assert new_or_touched_faults(before, after, touched=set()) == [self.NEW]

    def test_touching_either_participant_of_a_persisting_pair_fault_refuses(self):
        """R2-M1: the counterpart of an overlap cannot be edited while it persists."""
        before = {self.PAIR.key: self.PAIR}
        assert new_or_touched_faults(before, dict(before), touched={1}) == [self.PAIR]
        assert new_or_touched_faults(before, dict(before), touched={2}) == [self.PAIR]
        assert new_or_touched_faults(before, dict(before), touched={3}) == []

    def test_fault_map_keys_by_period_code_and_counterpart(self):
        p = _period(1, start=D(2026, 4, 1), end=D(2026, 3, 1), start_odo="5000", end_odo="4000")
        assert set(fault_map([p], [])) == {(1, REVERSED_DATES, None), (1, REVERSED_ODOMETER, None)}


class TestRepairingAShadowedCounterpart:
    """Counterparts are running maxima, so a repair can re-label an untouched fault.

    A legacy FL history with two odometer typos. Truth: A 0 to 4,000, B 4,000
    to 8,000, C 8,000 to 12,000. Stored: A's dismount typed as 9,000 and C's
    mount typed as 7,000. Both B and C are reported against A, the period
    holding the highest dismount. Fixing A hands that maximum to B, so C's
    untouched fault is now reported against B. Keyed by counterpart, that
    read as a NEW fault and refused the honest repair; C first is refused
    too, since C still participates in its fault against A. Neither order
    was accepted.
    """

    @staticmethod
    def _history(a_end: str, c_start: str) -> list[TireMountPeriod]:
        return [
            _period(1, start=D(2024, 1, 1), end=D(2024, 3, 1), start_odo="0", end_odo=a_end),
            _period(2, start=D(2024, 3, 1), end=D(2024, 6, 1), start_odo="4000", end_odo="8000"),
            _period(3, start=D(2024, 6, 1), end=D(2024, 9, 1), start_odo=c_start, end_odo="12000"),
        ]

    def test_the_legacy_history_reports_each_intruder_once(self):
        """Rules 4a and 4b both name (B, A) and (C, A): one fault each."""
        faults = validate_period_history(self._history("9000", "7000"), [])
        assert [(f.period_id, f.code, f.counterpart_id) for f in faults] == [
            (2, OVERLAPPING_ODOMETER, 1),
            (3, OVERLAPPING_ODOMETER, 1),
        ]

    def test_fixing_the_period_holding_the_maximum_first_then_the_other(self):
        legacy = fault_map(self._history("9000", "7000"), [])
        a_fixed = fault_map(self._history("4000", "7000"), [])
        # C's fault survives the repair, re-labelled against B.
        assert (3, OVERLAPPING_ODOMETER, 2) in a_fixed
        assert new_or_touched_faults(legacy, a_fixed, touched={1}) == []

        both_fixed = self._history("4000", "8000")
        assert new_or_touched_faults(a_fixed, fault_map(both_fixed, []), touched={3}) == []
        assert validate_period_history(both_fixed, []) == []

    def test_fixing_the_other_period_first_is_still_refused(self):
        """C still sits below A's 9,000, and C is the period being edited."""
        legacy = fault_map(self._history("9000", "7000"), [])
        c_fixed = fault_map(self._history("9000", "8000"), [])
        refused = new_or_touched_faults(legacy, c_fixed, touched={3})
        assert [(f.period_id, f.code, f.counterpart_id) for f in refused] == [
            (3, OVERLAPPING_ODOMETER, 1)
        ]

    def test_one_intruder_keeps_a_fault_per_counterpart(self):
        """Deduplication is by the full triple, never by (period, code).

        Q is mounted below X's dismount in date order (4a; X has no mount
        odometer, so 4b never sees it) and inside Y's span in odometer order
        (4b; Y has no mount date, so 4a never sees it). Y is a participant of
        that one fault and nothing else. Collapsing Q's two faults into one
        would drop Y, and an edit to Y would no longer be refused.
        """
        x = _period(1, start=D(2024, 1, 1), end=D(2024, 2, 1), start_odo=None, end_odo="5000")
        q = _period(2, start=D(2024, 3, 1), end=D(2024, 4, 1), start_odo="4000", end_odo="7000")
        y = _period(3, start=None, end=None, start_odo="0", end_odo="6000")
        faults = validate_period_history([x, q, y], [])
        assert [(f.period_id, f.code, f.counterpart_id) for f in faults] == [
            (2, OVERLAPPING_ODOMETER, 1),
            (2, OVERLAPPING_ODOMETER, 3),
        ]
        before = fault_map([x, q, y], [])
        refused = new_or_touched_faults(before, dict(before), touched={3})
        assert [(f.period_id, f.counterpart_id) for f in refused] == [(2, 3)]
