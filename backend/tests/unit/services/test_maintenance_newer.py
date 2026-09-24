"""Pins for the `_newer` same-day tie-break (plan 2026-09-18, feature D).

`_newer` decides which of two anchors is the later event: by date, then on
the same day by higher odometer (an odometer does not run backwards within
a day), then a service record over a bare completion, then the higher line
item id. Design 16.2; no unit test existed for it before this file.
"""

from datetime import date
from decimal import Decimal

from app.services.maintenance_recurrence import Anchor
from app.services.maintenance_service import _newer

DAY = date(2026, 6, 13)
NEXT_DAY = date(2026, 6, 14)


class TestNewer:
    def test_a_later_date_wins_whatever_else_the_anchors_carry(self):
        older = Anchor("service", DAY, Decimal("99999"), None, 42)
        newer = Anchor("completion", NEXT_DAY, Decimal("1"), None, None)
        assert _newer(newer, older)
        assert not _newer(older, newer)

    def test_same_day_the_higher_odometer_is_the_later_event(self):
        low = Anchor("service", DAY, Decimal("10000"), None, 1)
        high = Anchor("completion", DAY, Decimal("10200"), None, None)
        assert _newer(high, low)
        assert not _newer(low, high)

    def test_same_day_same_reading_a_service_beats_a_bare_completion(self):
        completion = Anchor("completion", DAY, Decimal("10000"), None, None)
        service = Anchor("service", DAY, Decimal("10000"), None, 7)
        assert _newer(service, completion)
        assert not _newer(completion, service)

    def test_same_day_two_services_fall_to_the_higher_line_item_id(self):
        first = Anchor("service", DAY, Decimal("10000"), None, 5)
        second = Anchor("service", DAY, Decimal("10000"), None, 7)
        assert _newer(second, first)
        assert not _newer(first, second)

    def test_hours_are_never_consulted(self):
        # Documenting seam (feature D recon): two same-date hours-only
        # completions with no odometer fall through every branch to the
        # line_item_id tie, where both read 0, so NEITHER is newer. If
        # `_newer` ever learns about hours, this pin is the one to update.
        early = Anchor("completion", DAY, None, Decimal("100"), None)
        late = Anchor("completion", DAY, None, Decimal("200"), None)
        assert not _newer(late, early)
        assert not _newer(early, late)
