"""Pure benchmark scoring helpers; no extraction data is persisted here."""

from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from typing import Any

from ..model.receipt import Receipt

MONEY_TOLERANCE = Decimal("0.01")
SCORING_VERSION = "1"
# Bumped to 3: the line-item `category` field was removed from the schema
# embedded in the prompt (only the receipt carries a category now).
PROMPT_VERSION = "3"
COMPONENT_WEIGHTS = {"header": 0.20, "totals": 0.35, "line_items": 0.30, "taxes": 0.15}


def normalize_money(value: Decimal | float | str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(MONEY_TOLERANCE, rounding=ROUND_HALF_UP)


def money_equal(expected: Any, actual: Any) -> bool:
    left, right = normalize_money(expected), normalize_money(actual)
    return left is not None and right is not None and abs(left - right) <= MONEY_TOLERANCE


def _fraction(matches: int, total: int) -> float:
    return 1.0 if total == 0 else matches / total


def score_receipts(expected: Receipt, actual: Receipt) -> dict[str, float]:
    header_fields = (
        "merchant_name",
        "merchant_address",
        "receipt_number",
        "date",
        "time",
        "currency",
        "category",
        "payment_method",
    )
    header = _fraction(
        sum(getattr(expected, f) == getattr(actual, f) for f in header_fields), len(header_fields)
    )
    total_fields = ("subtotal", "discount_total", "tax_total", "tip", "total")
    totals = _fraction(
        sum(money_equal(getattr(expected, f), getattr(actual, f)) for f in total_fields),
        len(total_fields),
    )
    expected_items, actual_items = expected.line_items, actual.line_items
    item_matches = sum(
        e.description == a.description and money_equal(e.total_price, a.total_price)
        for e, a in zip(expected_items, actual_items, strict=False)
    )
    line_items = _fraction(item_matches, max(len(expected_items), len(actual_items)))
    expected_taxes, actual_taxes = expected.taxes, actual.taxes
    tax_matches = sum(
        e.name == a.name and money_equal(e.amount, a.amount)
        for e, a in zip(expected_taxes, actual_taxes, strict=False)
    )
    taxes = _fraction(tax_matches, max(len(expected_taxes), len(actual_taxes)))
    components = {"header": header, "totals": totals, "line_items": line_items, "taxes": taxes}
    components["overall"] = sum(
        components[name] * weight for name, weight in COMPONENT_WEIGHTS.items()
    )
    return components


def dataset_fingerprint(receipts: list[Receipt]) -> str:
    """Stable fingerprint of the expected, selected data set."""
    rows = [r.model_dump_json(exclude={"confidence"}) for r in receipts]
    return sha256("\n".join(sorted(rows)).encode()).hexdigest()
