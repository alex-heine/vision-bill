"""Tests for the Pydantic Receipt model, focused on line-item tag sanitation."""

from datetime import date as Date
from decimal import Decimal

import pytest

from vision_bill.model.receipt import MAX_TAG_LENGTH, LineItem, Receipt


def _line_item(**overrides: object) -> LineItem:
    base: dict = {
        "description": "Item",
        "quantity": 1,
        "unit_price": Decimal("1.00"),
        "total_price": Decimal("1.00"),
    }
    base.update(overrides)
    return LineItem(**base)


def _pfand_line_item(**overrides: object) -> LineItem:
    """A German bottle-deposit refund: quantity * (-unit_price) = total_price."""
    base: dict = {
        "description": "Pfand (Flaschen)",
        "quantity": 3,
        "unit_price": Decimal("-0.25"),
        "total_price": Decimal("-0.75"),
    }
    base.update(overrides)
    return LineItem(**base)


@pytest.mark.parametrize(
    "raw, expected",
    [
        pytest.param([], [], id="empty"),
        pytest.param(["coffee"], ["coffee"], id="pass_through"),
        pytest.param(["  coffee  "], ["coffee"], id="trims_whitespace"),
        pytest.param(["  hot   drink "], ["hot drink"], id="collapses_inner_whitespace"),
        pytest.param(["coffee", "Coffee", "COFFEE"], ["coffee"], id="case_insensitive_dedupe"),
        pytest.param(["", "   "], [], id="drops_blank"),
        pytest.param(["coffee", "food"], ["coffee", "food"], id="keeps_distinct"),
        pytest.param(["x" * (MAX_TAG_LENGTH + 1)], [], id="drops_over_length"),
        pytest.param(["x" * MAX_TAG_LENGTH], ["x" * MAX_TAG_LENGTH], id="keeps_at_limit"),
    ],
)
def test_line_item_tag_sanitization(raw: list[str], expected: list[str]) -> None:
    item = _line_item(tags=raw)
    assert item.tags == expected


def test_line_item_tags_default_to_empty() -> None:
    assert _line_item().tags == []


def test_line_item_has_no_category_field() -> None:
    """Only the receipt carries a category; line items use tags instead."""
    assert "category" not in LineItem.model_fields


def test_receipt_schema_keeps_only_receipt_level_category() -> None:
    """The LLM JSON schema exposes category on the receipt, not on line items."""
    schema = Receipt.model_json_schema()
    assert "category" not in schema["$defs"]["LineItem"]["properties"]
    assert "category" in schema["properties"]


# ── Negative prices (Pfand / bottle-deposit refunds) ──────────────────


def test_line_item_accepts_negative_unit_and_total_price() -> None:
    """A Pfand refund is a line item whose unit and total price are negative.

    The price must round-trip with its sign intact, not be clamped to zero.
    """
    item = _pfand_line_item()
    assert item.unit_price == Decimal("-0.25")
    assert item.total_price == Decimal("-0.75")
    assert item.unit_price < 0
    assert item.total_price < 0


def test_receipt_validates_a_pfand_refund_line_item() -> None:
    """A receipt mixing a purchase with a negative Pfand line item must validate."""
    receipt = Receipt(
        confidence=90,
        merchant_name="Supermarkt",
        date=Date(2024, 1, 15),
        currency="EUR",
        category="grocery",
        line_items=[
            LineItem(
                description="Cola 1L",
                quantity=1,
                unit_price=Decimal("1.50"),
                total_price=Decimal("1.50"),
            ),
            _pfand_line_item(),
        ],
        # subtotal / total fold the negative line item in (1.50 + -0.75 = 0.75).
        subtotal=Decimal("0.75"),
        discount_total=Decimal(0),
        tax_total=Decimal(0),
        total=Decimal("0.75"),
    )
    assert receipt.line_items[1].unit_price == Decimal("-0.25")
    assert receipt.line_items[1].total_price == Decimal("-0.75")


def test_receipt_accepts_net_negative_pfand_return() -> None:
    """A pure deposit return hands money back, so subtotal and total may be negative.

    The Pfand change relaxes the receipt-level subtotal/total as well as the
    individual line items.
    """
    receipt = Receipt(
        confidence=90,
        merchant_name="Supermarkt",
        date=Date(2024, 1, 15),
        currency="EUR",
        category="grocery",
        line_items=[_pfand_line_item()],
        subtotal=Decimal("-0.75"),
        discount_total=Decimal(0),
        tax_total=Decimal(0),
        total=Decimal("-0.75"),
    )
    assert receipt.subtotal == Decimal("-0.75")
    assert receipt.total == Decimal("-0.75")
