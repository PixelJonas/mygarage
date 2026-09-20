"""The standard coverage catalogue, and the parser that maps text onto it.

A declarations page prints the same four things for every coverage it lists:
the limits, the deductible and the premium. `COVERAGES` below is that table,
in the order it is shown to the user, and `insurance_coverages` rows carry one
entry each.

WHY A CATALOGUE AND NOT COLUMNS. Every coverage would otherwise want its own
pair of columns ("each person", "each accident", "each day", "maximum days"),
and adding one would be a schema change. Instead the row has two generic limit
slots and this module says, per coverage, what they mean and whether they hold
money or a count. The table never moves when a coverage is added here.

A ROW'S EXISTENCE means the coverage is on the policy; its amounts say how
much. So a `roadside_assistance` row with four NULLs is not an empty row, it
is "included", and deleting it is how a user says the coverage is not carried.

THE PARSER (`parse_coverage_lines`) has two callers that must never disagree:
migration 108, converting the free text this catalogue replaced, and the PDF
route, converting a declarations page. Keeping it here, beside the phrases it
matches on, is what keeps them the same parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

SlotKind = Literal["money", "count"]


@dataclass(frozen=True)
class Slot:
    """One amount a coverage can carry, and the words that name it."""

    kind: SlotKind
    #: Phrases that pin an amount on a parsed line to THIS slot, whatever
    #: order the line happens to put them in.
    qualifiers: tuple[str, ...] = ()


EACH_PERSON = Slot("money", ("each person", "per person"))
EACH_ACCIDENT = Slot("money", ("each accident", "per accident"))
EACH_DAY = Slot("money", ("each day", "per day", "a day"))
MAXIMUM_DAYS = Slot("count", ("maximum days", "maximum", "days"))
LIMIT = Slot("money")
#: Deductible and premium are slots like any other, not special cases: that is
#: what lets one loop read, write, validate and render all four amounts.
DEDUCTIBLE = Slot("money", ("deductible",))
PREMIUM = Slot("money", ("premium",))


@dataclass(frozen=True)
class Coverage:
    """One row of the standard catalogue."""

    key: str
    #: English, for the backend's own English-only surfaces (CSV export, PDF
    #: reports). The UI labels a coverage from its own translated catalogue.
    label: str = ""
    primary: Slot | None = None
    secondary: Slot | None = None
    has_deductible: bool = False
    has_premium: bool = True
    #: Openings that identify this coverage on a declarations line. Matching is
    #: longest-first across the WHOLE catalogue, so "comprehensive window
    #: glass" reaches `glass` rather than `comprehensive`.
    phrases: tuple[str, ...] = ()

    def slots(self) -> tuple[tuple[str, Slot], ...]:
        """Column name -> slot, in the order a declarations page prints them.

        THE single definition of which amounts a coverage may carry. The
        parser fills by it, the API validates by it, the importer re-validates
        by it and the flat exports render by it, so a coverage gaining a slot
        is one edit here.
        """
        pairs: list[tuple[str, Slot]] = []
        if self.primary:
            pairs.append(("limit_primary", self.primary))
        if self.secondary:
            pairs.append(("limit_secondary", self.secondary))
        if self.has_deductible:
            pairs.append(("deductible", DEDUCTIBLE))
        if self.has_premium:
            pairs.append(("premium", PREMIUM))
        return tuple(pairs)


#: The catalogue, in display order. This order is the layout: the policy card
#: and the form both walk it, so two vehicles on one policy can never show
#: their coverages in a different sequence.
COVERAGES: tuple[Coverage, ...] = (
    Coverage(
        "bodily_injury",
        label="Bodily Injury Liability",
        primary=EACH_PERSON,
        secondary=EACH_ACCIDENT,
        phrases=("bodily injury liability", "bodily injury"),
    ),
    Coverage(
        "property_damage",
        label="Property Damage Liability",
        primary=EACH_ACCIDENT,
        phrases=("property damage liability", "property damage"),
    ),
    Coverage(
        "uninsured_bodily_injury",
        label="Uninsured/Underinsured Motorist Bodily Injury",
        primary=EACH_PERSON,
        secondary=EACH_ACCIDENT,
        phrases=(
            "uninsured/underinsured motorist bodily injury",
            "uninsured / underinsured motorist bodily injury",
            "underinsured motorist bodily injury",
            "uninsured motorist bodily injury",
            "um/uim bodily injury",
        ),
    ),
    Coverage(
        "uninsured_property_damage",
        label="Uninsured/Underinsured Motorist Property Damage",
        primary=EACH_ACCIDENT,
        has_deductible=True,
        phrases=(
            "uninsured/underinsured motorist property damage",
            "uninsured / underinsured motorist property damage",
            "underinsured motorist property damage",
            "uninsured motorist property damage",
            "um/uim property damage",
        ),
    ),
    Coverage(
        "personal_injury_protection",
        label="Personal Injury Protection",
        primary=EACH_PERSON,
        has_deductible=True,
        phrases=("personal injury protection",),
    ),
    Coverage(
        "medical_payments",
        label="Medical Payments",
        primary=EACH_PERSON,
        phrases=("medical payments", "medical expense", "med pay"),
    ),
    Coverage(
        "comprehensive", label="Comprehensive", has_deductible=True, phrases=("comprehensive",)
    ),
    Coverage("collision", label="Collision", has_deductible=True, phrases=("collision",)),
    Coverage(
        "glass",
        label="Glass",
        has_deductible=True,
        phrases=("comprehensive window glass", "window glass", "full glass", "glass"),
    ),
    Coverage(
        "rental_reimbursement",
        label="Rental Reimbursement",
        primary=EACH_DAY,
        secondary=MAXIMUM_DAYS,
        phrases=("rental reimbursement", "rental car reimbursement", "rental"),
    ),
    Coverage(
        "roadside_assistance",
        label="Roadside Assistance",
        phrases=(
            "roadside assistance",
            "emergency roadside service",
            "towing and labor",
            "roadside",
        ),
    ),
    Coverage(
        "loan_lease_gap",
        label="Loan/Lease Gap",
        phrases=(
            "loan/lease payoff",
            "loan or lease payoff",
            "loan/lease gap",
            "gap coverage",
            "lease gap",
        ),
    ),
    Coverage(
        "custom_equipment",
        label="Custom Parts and Equipment",
        primary=LIMIT,
        has_deductible=True,
        phrases=("custom parts and equipment", "custom equipment", "custom parts"),
    ),
)

COVERAGE_KEYS: tuple[str, ...] = tuple(c.key for c in COVERAGES)
COVERAGE_BY_KEY: dict[str, Coverage] = {c.key: c for c in COVERAGES}
#: Catalogue position per key, for sorting without a linear scan per row.
COVERAGE_ORDER: dict[str, int] = {key: index for index, key in enumerate(COVERAGE_KEYS)}

#: Every phrase, longest first, so the most specific coverage wins a line.
_PHRASES: tuple[tuple[str, str], ...] = tuple(
    sorted(
        ((phrase, coverage.key) for coverage in COVERAGES for phrase in coverage.phrases),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)

#: `$1,234.56`, `1,234.56` or `1234`. The dollar sign is optional because a
#: flattened column ("Comprehensive Actual Cash Value 1000 146.00") loses it.
_AMOUNT = re.compile(r"\$?\s?(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")


@dataclass
class ParsedCoverage:
    """One catalogue coverage read off a line, ready to become a row."""

    key: str
    limit_primary: Decimal | None = None
    limit_secondary: Decimal | None = None
    deductible: Decimal | None = None
    premium: Decimal | None = None

    def slots(self) -> tuple[tuple[str, Slot], ...]:
        """This coverage's amounts, from the catalogue."""
        return COVERAGE_BY_KEY[self.key].slots()


@dataclass
class CoverageParse:
    """What a block of coverage text turned into.

    Three destinations, because nothing a user could read before an upgrade may
    be discarded: lines this catalogue knows become `coverages`, a leftover
    that splits into a label and an amount becomes a named `field`, and a
    leftover with no amount at all stays prose in `notes`.
    """

    coverages: list[ParsedCoverage] = field(default_factory=list)
    fields: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:  # pragma: no cover - the regex admits nothing else
        return None


def _normalize(line: str) -> str:
    """Lower-case, with bullets and runs of whitespace flattened."""
    return re.sub(r"\s+", " ", line.strip().lstrip("-•*·• ").strip()).lower()


def _match_phrase(normalized: str) -> tuple[str, str] | None:
    """The coverage a line opens with, and the text left after its phrase."""
    for phrase, key in _PHRASES:
        if normalized.startswith(phrase):
            return key, normalized[len(phrase) :].lstrip(" :-")
    return None


def _read_amounts(remainder: str, parsed: ParsedCoverage) -> None:
    """Fill `parsed`'s slots from the amounts in `remainder`.

    Two passes, because a declarations line qualifies some of its amounts and
    leaves the rest to column order. Qualified amounts ("$300,000 each
    accident", "$500 deductible") go to the slot whose own words claim them,
    wherever on the line they appear; whatever is left fills the remaining
    slots in the order the page prints its columns, which is limits, then
    deductible, then premium.
    """
    slots = COVERAGE_BY_KEY[parsed.key].slots()
    matches = list(_AMOUNT.finditer(remainder))
    if not matches:
        return

    # An amount's qualifier is the words between it and the next amount.
    spans = [
        (
            match,
            remainder[
                match.end() : (matches[i + 1].start() if i + 1 < len(matches) else len(remainder))
            ],
        )
        for i, match in enumerate(matches)
    ]

    unclaimed = []
    for match, qualifier in spans:
        value = _to_decimal(match.group(1))
        if value is None:
            continue
        claimed = next(
            (
                name
                for name, slot in slots
                if any(q in qualifier for q in slot.qualifiers) and getattr(parsed, name) is None
            ),
            None,
        )
        if claimed:
            setattr(parsed, claimed, value)
        else:
            unclaimed.append(value)

    for value in unclaimed:
        for name, _slot in slots:
            if getattr(parsed, name) is None:
                setattr(parsed, name, value)
                break


def _split_leftover(line: str) -> tuple[str, str] | None:
    """A leftover line as label + value, or None when it carries no value.

    Returned in full: what a label may be truncated to is the named-field
    table's business, and the callers that write that table apply it.
    """
    match = re.search(r"[$\d]", line)
    if match is None or match.start() == 0:
        return None
    label = line[: match.start()].strip().rstrip(":-,").strip()
    value = line[match.start() :].strip()
    if not label or not value:
        return None
    return label, value


def parse_coverage_lines(text: str | None) -> CoverageParse:
    """Read a block of coverage text into catalogue rows and leftovers.

    The same parser serves the upgrade from free text (migration 108) and a
    parsed declarations page, so a policy typed by hand and one imported from a
    PDF land in exactly the same shape.

    A second line for a coverage already read fills only the slots still empty:
    a page that prints "Collision" as a section header and then "Collision
    Actual Cash Value $1,000 $299" must end with one row holding the amounts.
    A repeat that adds nothing and is nothing but the phrase itself is dropped,
    being a heading that the row it duplicates already says.
    """
    result = CoverageParse()
    if not text:
        return result

    by_key: dict[str, ParsedCoverage] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-•*·• ").strip()
        if not line:
            continue
        normalized = _normalize(raw_line)
        matched = _match_phrase(normalized)
        if matched is None:
            split = _split_leftover(line)
            if split:
                result.fields.append(split)
            else:
                result.notes.append(line)
            continue

        key, remainder = matched
        existing = by_key.get(key)
        if existing is None:
            parsed = ParsedCoverage(key)
            _read_amounts(remainder, parsed)
            by_key[key] = parsed
            result.coverages.append(parsed)
            continue

        # A repeat completes the row ONLY when the row is still a bare
        # heading. Once a coverage has an amount, a second line naming it is a
        # different reading of it -- most often the same coverage on the next
        # vehicle of a multi-vehicle page -- and letting that fill the slots
        # still empty would post one vehicle's limit as another's premium.
        if all(getattr(existing, name) is None for name, _slot in existing.slots()):
            _read_amounts(remainder, existing)
            if any(getattr(existing, name) is not None for name, _slot in existing.slots()):
                continue
        # Contributed nothing. A bare repeat of the phrase is a heading the
        # row already carries; anything more is kept rather than discarded.
        if remainder.strip():
            result.notes.append(line)

    result.coverages.sort(key=lambda parsed: COVERAGE_ORDER[parsed.key])
    return result


def format_coverage_lines(coverages: list[ParsedCoverage]) -> str:
    """Render coverages as the text `parse_coverage_lines` reads back.

    The flat exports (CSV) and the English-only PDF reports have one column for
    a vehicle's coverage, so the rows are flattened to one line each. Every
    amount is written with the word that pins it to its slot, so a file
    exported and re-imported comes back as exactly the same rows rather than
    depending on column order.
    """
    lines = []
    for item in coverages:
        coverage = COVERAGE_BY_KEY[item.key]
        limits, extras = [], []
        for name, slot in coverage.slots():
            value = getattr(item, name)
            if value is None:
                continue
            amount = f"${value:,.2f}" if slot.kind == "money" else f"{value:,.0f}"
            qualifier = f" {slot.qualifiers[0]}" if slot.qualifiers else ""
            # The limits read as one figure ("$100,000 each person/$300,000
            # each accident"); the deductible and the premium follow it.
            (limits if name.startswith("limit_") else extras).append(f"{amount}{qualifier}")
        rendered = " ".join(filter(None, ["/".join(limits), *extras]))
        lines.append(f"{coverage.label} {rendered}".strip())
    return "\n".join(lines)


def coverage_text(rows: list[Any]) -> str:
    """Flatten stored coverage rows to text, in catalogue order.

    `rows` is anything carrying the columns (ORM rows, schema entries). The
    flat surfaces -- the CSV export and the English-only PDF reports -- have
    one column for a vehicle's coverage and this is what goes in it.
    """
    items = [
        ParsedCoverage(
            row.coverage_key,
            row.limit_primary,
            row.limit_secondary,
            row.deductible,
            row.premium,
        )
        for row in rows
        if row.coverage_key in COVERAGE_BY_KEY
    ]
    items.sort(key=lambda item: COVERAGE_ORDER[item.key])
    return format_coverage_lines(items)


def coverage_row(item: ParsedCoverage) -> dict[str, Any]:
    """One parsed coverage as the columns `insurance_coverages` stores.

    The single projection: migration 108 binds it as SQL parameters, the
    importer hands it to the ORM, and `coverage_payload` stringifies it for
    the document-parse route.
    """
    return {
        "coverage_key": item.key,
        "limit_primary": item.limit_primary,
        "limit_secondary": item.limit_secondary,
        "deductible": item.deductible,
        "premium": item.premium,
    }


def coverage_payload(items: list[ParsedCoverage]) -> list[dict[str, str | None]]:
    """Parsed coverages as a JSON payload, amounts as strings.

    The document-parse routes return raw dictionaries rather than schemas, and
    stringify every amount so a Decimal never reaches `json.dumps` as a float.
    """
    return [
        {
            name: value if name == "coverage_key" or value is None else str(value)
            for name, value in coverage_row(item).items()
        }
        for item in items
    ]
