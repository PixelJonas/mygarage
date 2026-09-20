"""The standard coverage catalogue and its line parser.

The sample text in these tests is the shape a real Progressive declarations
page flattens to, which is what migration 108 has to read off existing rows
and what the PDF route has to read off an upload.
"""

from decimal import Decimal

import pytest

from app.utils.insurance_coverages import (
    COVERAGE_BY_KEY,
    COVERAGE_KEYS,
    COVERAGES,
    ParsedCoverage,
    format_coverage_lines,
    parse_coverage_lines,
)

PROGRESSIVE = """Liability to Others $315
Bodily Injury Liability $100,000 each person/$300,000 each accident
Property Damage Liability $100,000 each accident
Personal Injury Protection $2,500 each person/each accident
Uninsured/Underinsured Motorist Bodily Injury $100,000 each person/$300,000 each accident
Uninsured/Underinsured Motorist Property Damage $100,000 each accident $250
Comprehensive Actual Cash Value $995
Comprehensive Window Glass $0 glass
Collision Actual Cash Value $995
Rental Reimbursement up to $50 each day/maximum 30 days
Roadside Assistance"""


def parsed(text: str) -> dict[str, object]:
    """The parse keyed by coverage, for assertions that name one coverage."""
    return {item.key: item for item in parse_coverage_lines(text).coverages}


class TestCatalogue:
    def test_keys_are_unique(self):
        assert len(COVERAGE_KEYS) == len(set(COVERAGE_KEYS))

    def test_every_coverage_is_reachable_by_a_phrase(self):
        """A coverage with no phrase can never be imported, only typed."""
        for coverage in COVERAGES:
            assert coverage.phrases, f"{coverage.key} has no matching phrase"

    def test_a_secondary_slot_implies_a_primary_one(self):
        """`limit_secondary` with no `limit_primary` would render a gap."""
        for coverage in COVERAGES:
            assert not (coverage.secondary and not coverage.primary), coverage.key


class TestPhraseMatching:
    def test_the_longest_phrase_wins(self):
        """ "Comprehensive Window Glass" is glass, not comprehensive."""
        assert "glass" in parsed("Comprehensive Window Glass $0 glass")

    def test_uninsured_motorist_beats_bodily_injury(self):
        result = parsed("Uninsured/Underinsured Motorist Bodily Injury $100,000 each person")
        assert "uninsured_bodily_injury" in result
        assert "bodily_injury" not in result

    def test_matching_ignores_case_bullets_and_indentation(self):
        assert "collision" in parsed("   - COLLISION   Actual Cash Value $500")

    def test_an_unknown_line_is_not_forced_onto_a_coverage(self):
        assert parse_coverage_lines("Pest Damage Protection $5,000 $250").coverages == []


class TestAmounts:
    def test_qualified_amounts_reach_their_own_slots(self):
        item = parsed(PROGRESSIVE)["bodily_injury"]
        assert item.limit_primary == Decimal("100000")
        assert item.limit_secondary == Decimal("300000")

    def test_a_single_qualified_amount_reaches_the_primary_slot(self):
        item = parsed("Property Damage Liability $100,000 each accident")["property_damage"]
        assert item.limit_primary == Decimal("100000")
        assert item.limit_secondary is None

    def test_a_qualifier_with_no_amount_is_not_invented(self):
        """ "$2,500 each person/each accident" prices ONE slot."""
        item = parsed(PROGRESSIVE)["personal_injury_protection"]
        assert item.limit_primary == Decimal("2500")
        assert item.limit_secondary is None

    def test_an_unqualified_amount_falls_to_the_next_free_slot(self):
        """The trailing $250 is the deductible column, the only slot left."""
        item = parsed(PROGRESSIVE)["uninsured_property_damage"]
        assert item.limit_primary == Decimal("100000")
        assert item.deductible == Decimal("250")

    def test_column_order_is_limits_then_deductible_then_premium(self):
        item = parsed("Comprehensive Actual Cash Value $1,000 $146.00")["comprehensive"]
        assert item.deductible == Decimal("1000")
        assert item.premium == Decimal("146.00")

    def test_an_explicit_deductible_skips_the_limit_column(self):
        """A named deductible is the deductible even when a limit is unfilled.

        Column order alone would read the $250 as the limit, this coverage's
        first free slot, and leave the deductible empty.
        """
        item = parsed("Uninsured Motorist Property Damage $250 deductible")[
            "uninsured_property_damage"
        ]
        assert item.deductible == Decimal("250")
        assert item.limit_primary is None

    def test_a_count_slot_reads_a_bare_number(self):
        item = parsed(PROGRESSIVE)["rental_reimbursement"]
        assert item.limit_primary == Decimal("50")
        assert item.limit_secondary == Decimal("30")

    def test_a_zero_is_kept_not_treated_as_missing(self):
        assert parsed("Comprehensive Window Glass $0 glass")["glass"].deductible == Decimal("0")

    def test_a_coverage_with_no_amounts_is_still_a_row(self):
        """Its existence is the fact: the coverage is carried."""
        item = parsed(PROGRESSIVE)["roadside_assistance"]
        assert (item.limit_primary, item.limit_secondary, item.deductible, item.premium) == (
            None,
            None,
            None,
            None,
        )


class TestLeftovers:
    def test_a_line_with_a_value_becomes_a_named_field(self):
        result = parse_coverage_lines("Roof Protection Plus $5,000 $250")
        assert result.fields == [("Roof Protection Plus", "$5,000 $250")]
        assert result.notes == []

    def test_a_line_with_no_value_stays_prose(self):
        result = parse_coverage_lines("Disappearing Deductibles")
        assert result.notes == ["Disappearing Deductibles"]
        assert result.fields == []

    def test_a_long_leftover_is_returned_whole(self):
        """How wide a named field may be is the writer's business, not the
        parser's: the migration and the importer own that column."""
        label = "L" * 80
        result = parse_coverage_lines(f"{label} $5")
        assert result.fields[0][0] == label

    def test_blank_lines_are_dropped(self):
        assert parse_coverage_lines("\n\n   \n").fields == []


class TestRepeatedCoverages:
    def test_a_heading_and_its_detail_become_one_row(self):
        result = parse_coverage_lines("Collision:\nCollision Actual Cash Value $1,000 $299")
        assert len(result.coverages) == 1
        assert result.coverages[0].deductible == Decimal("1000")

    def test_a_bare_repeat_is_not_kept_as_prose(self):
        """It says only what the row it duplicates already says."""
        result = parse_coverage_lines("Collision Actual Cash Value $1,000\nCollision:")
        assert result.notes == []

    def test_a_repeat_that_adds_an_amount_fills_the_empty_slot(self):
        result = parse_coverage_lines("Collision\nCollision $500 deductible")
        assert len(result.coverages) == 1
        assert result.coverages[0].deductible == Decimal("500")

    def test_a_priced_coverage_is_not_topped_up_by_a_later_reading(self):
        """On a multi-vehicle page the same coverage appears once per vehicle.
        Letting the second fill the first's empty slots posts one vehicle's
        limit as another's premium."""
        result = parse_coverage_lines(
            "Bodily Injury Liability $100,000 each person/$300,000 each accident\n"
            "Bodily Injury Liability $25,000 each person/$50,000 each accident"
        )
        (item,) = result.coverages
        assert item.limit_primary == Decimal("100000")
        assert item.premium is None
        assert len(result.notes) == 1

    def test_a_conflicting_repeat_is_kept_rather_than_discarded(self):
        result = parse_coverage_lines("Collision $500 deductible $10\nCollision $900 deductible")
        assert result.coverages[0].deductible == Decimal("500")
        assert result.notes == ["Collision $900 deductible"]


class TestWholeDocument:
    def test_the_progressive_page_reads_end_to_end(self):
        result = parse_coverage_lines(PROGRESSIVE)
        assert [item.key for item in result.coverages] == [
            "bodily_injury",
            "property_damage",
            "uninsured_bodily_injury",
            "uninsured_property_damage",
            "personal_injury_protection",
            "comprehensive",
            "collision",
            "glass",
            "rental_reimbursement",
            "roadside_assistance",
        ]

    def test_coverages_come_back_in_catalogue_order(self):
        """The card and the form both walk this order, so the parse shares it."""
        result = parse_coverage_lines(PROGRESSIVE)
        order = [COVERAGE_KEYS.index(item.key) for item in result.coverages]
        assert order == sorted(order)

    def test_the_only_unmatched_line_is_the_section_subtotal(self):
        result = parse_coverage_lines(PROGRESSIVE)
        assert result.fields == [("Liability to Others", "$315")]

    def test_empty_text_parses_to_nothing(self):
        for value in (None, "", "   "):
            result = parse_coverage_lines(value)
            assert (result.coverages, result.fields, result.notes) == ([], [], [])


@pytest.mark.parametrize("key", COVERAGE_KEYS)
def test_each_catalogue_key_survives_a_round_trip(key):
    """Every coverage can be read back from the phrase the UI shows for it."""
    phrase = COVERAGE_BY_KEY[key].phrases[0]
    assert parsed(phrase).get(key) is not None


class TestFormatting:
    """The flat exports write one line per coverage; the importer reads it back."""

    def test_a_line_names_the_word_that_pins_each_amount(self):
        text = format_coverage_lines(parse_coverage_lines(PROGRESSIVE).coverages)
        assert "Bodily Injury Liability $100,000.00 each person/$300,000.00 each accident" in text
        assert "Rental Reimbursement $50.00 each day/30 maximum days" in text

    def test_a_coverage_with_no_amounts_is_just_its_name(self):
        text = format_coverage_lines(parse_coverage_lines("Roadside Assistance").coverages)
        assert text == "Roadside Assistance"

    def test_a_deductible_survives_a_round_trip_through_the_text(self):
        first = parse_coverage_lines("Comprehensive $500 deductible $146.00").coverages
        again = parse_coverage_lines(format_coverage_lines(first)).coverages
        assert (again[0].deductible, again[0].premium) == (Decimal("500"), Decimal("146.00"))

    def test_the_whole_page_survives_a_round_trip(self):
        """Export then re-import must not move a single amount."""
        first = parse_coverage_lines(PROGRESSIVE).coverages
        again = parse_coverage_lines(format_coverage_lines(first)).coverages
        assert [
            (c.key, c.limit_primary, c.limit_secondary, c.deductible, c.premium) for c in again
        ] == [(c.key, c.limit_primary, c.limit_secondary, c.deductible, c.premium) for c in first]


@pytest.mark.parametrize("key", COVERAGE_KEYS)
def test_every_coverage_round_trips_with_every_slot_filled(key):
    """Each catalogue entry, written out full and read back unchanged."""
    coverage = COVERAGE_BY_KEY[key]
    item = ParsedCoverage(key)
    if coverage.primary:
        item.limit_primary = Decimal("100000.00")
    if coverage.secondary:
        item.limit_secondary = (
            Decimal("30") if coverage.secondary.kind == "count" else Decimal("300000.00")
        )
    if coverage.has_deductible:
        item.deductible = Decimal("500.00")
    if coverage.has_premium:
        item.premium = Decimal("146.00")

    again = parse_coverage_lines(format_coverage_lines([item])).coverages
    assert len(again) == 1, f"{key} did not read back"
    assert again[0] == item


class TestSlotsAreTheOneDefinition:
    """Which amounts a coverage carries is stated once, on the catalogue."""

    def test_a_coverage_names_its_amounts_in_column_order(self):
        assert [name for name, _ in COVERAGE_BY_KEY["bodily_injury"].slots()] == [
            "limit_primary",
            "limit_secondary",
            "premium",
        ]
        assert [name for name, _ in COVERAGE_BY_KEY["comprehensive"].slots()] == [
            "deductible",
            "premium",
        ]

    def test_a_deductible_is_an_ordinary_slot_with_its_own_word(self):
        """It used to be a special case ahead of the generic loop."""
        slots = dict(COVERAGE_BY_KEY["collision"].slots())
        assert "deductible" in slots["deductible"].qualifiers

    def test_a_parsed_coverage_reads_its_slots_from_the_catalogue(self):
        assert ParsedCoverage("glass").slots() == COVERAGE_BY_KEY["glass"].slots()
