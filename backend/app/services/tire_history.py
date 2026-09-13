"""Refuse a tire history that contradicts itself, at write time.

The projection already knows the shapes that make a per-tire figure
meaningless: a period whose bounds run backwards, two periods claiming the
same kilometres, dates and odometers that describe two different histories.
It handles them by withholding the figure. This module applies the same
rules, plus one the projection never needed, BEFORE the write commits, so
the contradiction is refused with a sentence instead of stored and explained
later.

The extra rule is date overlap. The projection is odometer-based and never
needed it; an editor that lets a user type dates does, because a tire is
never in two places on the same day.

Pure. Takes ORM objects but touches no session, so the unit tests build
periods in memory, and every writer calls it over the tire's RESULTING period
list after a flush and before the commit.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.models.tire import TireMountPeriod, TireReading

REVERSED_DATES = "reversed_dates"
REVERSED_ODOMETER = "reversed_odometer"
OVERLAPPING_DATES = "overlapping_dates"
OVERLAPPING_ODOMETER = "overlapping_odometer"
CONTRADICTS_READING = "contradicts_reading"


@dataclass(frozen=True)
class PeriodFault:
    """One contradiction, on the period that introduces it.

    `counterpart_id` is the period it contradicts, for the pair rules. Both
    are participants: the incremental policy refuses a write that touches
    EITHER side of a persisting contradiction, so the counterpart of an
    overlap cannot be edited to make it worse under an unchanged key.
    """

    period_id: int
    code: str
    message: str
    counterpart_id: int | None = None

    @property
    def key(self) -> tuple[int, str, int | None]:
        return (self.period_id, self.code, self.counterpart_id)

    @property
    def participants(self) -> frozenset[int]:
        return frozenset(i for i in (self.period_id, self.counterpart_id) if i is not None)


def _label(period: TireMountPeriod) -> str:
    return f"period {period.id} ({period.position})"


def validate_period_history(
    periods: Sequence[TireMountPeriod], readings: Sequence[TireReading]
) -> list[PeriodFault]:
    """Every contradiction in this tire's history, or an empty list.

    Every comparison is STRICT, so a same-day dismount and remount, and a
    remount at exactly the last dismount odometer, pass: that is what a
    rotation looks like. An unknown bound is a gap, never a fault; the
    migrated assumed period has two of them.

    Rules 1, 2 and 5 look at every period. Rules 3 and 4 are orderings, and
    each runs ONLY over the periods whose ordering key is known: the mount
    date for 3 and 4a, a fully known odometer span for 4b. A period with an
    unknown key is neither judged nor used to judge others. Rules 3 and 4a
    name every earlier period a later one contradicts, so one period can carry
    several faults of one code, one per counterpart. Sorting unknown dates as "earliest", the
    way the response sorts for display, is wrong here: clearing a later open
    period's mount date would sort it first, and every earlier closed period
    would then "start while it is still open".

    Faults name the LATER period of a pair, the one that intrudes on history
    already recorded.
    """
    faults: list[PeriodFault] = []
    seen: set[tuple[int, str, int | None]] = set()

    def add(
        period: TireMountPeriod,
        code: str,
        message: str,
        counterpart: TireMountPeriod | None = None,
    ) -> None:
        fault = PeriodFault(period.id, code, message, counterpart.id if counterpart else None)
        if fault.key not in seen:
            seen.add(fault.key)
            faults.append(fault)

    # 1 and 2: a period against itself.
    for p in periods:
        if (
            p.mounted_on is not None
            and p.dismounted_on is not None
            and p.dismounted_on < p.mounted_on
        ):
            add(
                p,
                REVERSED_DATES,
                f"{_label(p)} is dismounted on {p.dismounted_on} before it was mounted on {p.mounted_on}.",
            )
        if (
            p.mounted_odometer_km is not None
            and p.dismounted_odometer_km is not None
            and p.dismounted_odometer_km < p.mounted_odometer_km
        ):
            add(
                p,
                REVERSED_ODOMETER,
                f"{_label(p)} is dismounted at {p.dismounted_odometer_km} km, below its mount "
                f"odometer of {p.mounted_odometer_km} km.",
            )

    # 3: dates, over periods with a known mount date, in date order. Each
    # period is judged against EVERY earlier one, not a running maximum. A
    # running maximum names only the period holding it, so an earlier period
    # that also contradicts the later one is no participant of any fault, and
    # the incremental policy cannot see a write that made it contradict. Rule 3
    # could not actually hide one that way (every dated period is both judged
    # and a possible counterpart); it is written like 4a so the two stay one
    # shape.
    dated = sorted(
        (p for p in periods if p.mounted_on is not None), key=lambda p: (p.mounted_on, p.id or 0)
    )
    for index, q in enumerate(dated):
        # Narrowed again for pyright, which cannot see the filter that built
        # `dated` through the generator.
        mounted_on = q.mounted_on
        assert mounted_on is not None
        for earlier in dated[:index]:
            if earlier.dismounted_on is None:
                add(
                    q,
                    OVERLAPPING_DATES,
                    f"{_label(q)} starts while {_label(earlier)} is still open.",
                    counterpart=earlier,
                )
            elif mounted_on < earlier.dismounted_on:
                add(
                    q,
                    OVERLAPPING_DATES,
                    f"{_label(q)} is mounted on {mounted_on}, before {_label(earlier)} was "
                    f"dismounted on {earlier.dismounted_on}.",
                    counterpart=earlier,
                )
            # 4a rides along the same chronological order: the odometer cannot
            # go down between a known earlier dismount and a known later mount.
            # This is the rule a running maximum really did hide behind: a
            # period with a dismount odometer and no mount odometer can be a
            # counterpart but is never judged, so nothing else names it.
            if (
                q.mounted_odometer_km is not None
                and earlier.dismounted_odometer_km is not None
                and q.mounted_odometer_km < earlier.dismounted_odometer_km
            ):
                add(
                    q,
                    OVERLAPPING_ODOMETER,
                    f"{_label(q)} is mounted at {q.mounted_odometer_km} km, below "
                    f"{_label(earlier)}'s dismount at {earlier.dismounted_odometer_km} km.",
                    counterpart=earlier,
                )

    # 4b: order-free. Two fully bounded spans that strictly intersect are a
    # contradiction whatever their dates say: a tire cannot be in two places
    # at once. Sorted by mount odometer; the later-by-odometer span is the
    # intruder. Where 4a already named the same pair, `add` deduplicates.
    #
    # A running maximum is safe HERE, unlike in 3 and 4a, because every span
    # is both judged and a possible counterpart. An earlier span P that a later
    # span intersects, without holding the maximum, is itself a participant: if
    # P is not an intruder, the maximum after P is P's own dismount, so the
    # next span in order (whose mount is below it) is reported against P.
    spans = sorted(
        (
            p
            for p in periods
            if p.mounted_odometer_km is not None and p.dismounted_odometer_km is not None
        ),
        key=lambda p: (p.mounted_odometer_km, p.id or 0),
    )
    covered: tuple[Decimal, TireMountPeriod] | None = None
    for q in spans:
        if covered is not None and q.mounted_odometer_km < covered[0]:
            add(
                q,
                OVERLAPPING_ODOMETER,
                f"{_label(q)} claims kilometres {_label(covered[1])} already covers "
                f"(it starts at {q.mounted_odometer_km} km, before that period ended at {covered[0]} km).",
                counterpart=covered[1],
            )
        if covered is None or q.dismounted_odometer_km > covered[0]:
            # `spans` is filtered to periods with a known dismount odometer;
            # this asserts that invariant for pyright, which cannot see
            # through the generator filter that built `spans`.
            end = q.dismounted_odometer_km
            assert end is not None
            covered = (end, q)

    # 5: the projection's own monotonicity rule, unchanged. Imported lazily:
    # tire_service imports this module for its writers, and a top-level import
    # here would be circular.
    from app.services.tire_service import _odometer_goes_backwards

    by_id = {p.id: p for p in periods}
    for pid in _odometer_goes_backwards(list(periods), tuple(readings)):
        p = by_id.get(pid)
        if p is not None:
            add(
                p,
                CONTRADICTS_READING,
                f"{_label(p)}'s dates and odometers contradict a tread reading: the vehicle's "
                "odometer would have to run backwards.",
            )
    return faults


FaultMap = dict[tuple[int, str, int | None], PeriodFault]


def fault_map(periods: Sequence[TireMountPeriod], readings: Sequence[TireReading]) -> FaultMap:
    """`validate_period_history` keyed by (period, code, counterpart), for a before/after comparison."""
    return {f.key: f for f in validate_period_history(periods, readings)}


def new_or_touched_faults(
    before: FaultMap, after: FaultMap, touched: set[int]
) -> list[PeriodFault]:
    """The faults a write must refuse: any it introduced, and any persisting one
    that a period it touched participates in.

    Writers before v3.4.0 committed without validation, so a tire can carry
    two independently contradictory legacy periods. Refusing every fault
    would make that history unrepairable (fixing either period leaves the
    other) and the tire undismountable. A write is judged on what it changed:
    a fault that was already there, on periods it did not touch, survives and
    stays flagged on the wire, to be repaired in its own turn. Judged on
    PARTICIPANTS, not on the intruder alone: the counterpart of an overlap
    cannot be edited to make it worse while the fault persists.

    The faults about a touched period come first, keeping their order among
    themselves: a writer raises the first one, and the sentence a user reads
    should be about the change they just made.

    "Introduced" means the period now carries a CODE it did not carry before:
    a fault is new when its `(period_id, code)` was not faulted in `before`.
    The counterpart is deliberately left out of that test. The pair rules name
    a running maximum, the period holding the highest dismount so far, so
    repairing that period hands the maximum to the next one and re-labels an
    untouched fault against a different counterpart. Judged by the full key,
    that relabelled fault read as new and refused the honest repair, and a
    history with two legacy typos could be refused in either order. Nothing is
    lost by leaving the counterpart out: a fault between two untouched periods
    depends only on their own bounds, so no write can create one, and a fault
    whose new counterpart IS a touched period is still refused through its
    participants. `FaultMap` keeps the full triple so each counterpart is
    still a participant.
    """
    pre_existing = {(f.period_id, f.code) for f in before.values()}
    refused = [
        f
        for f in after.values()
        if (f.period_id, f.code) not in pre_existing or (f.participants & touched)
    ]
    # Stable, so the validator's order holds within each group.
    return sorted(refused, key=lambda f: not (f.participants & touched))
