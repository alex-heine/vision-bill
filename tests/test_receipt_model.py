"""Tests for the Pydantic Receipt model, focused on line-item tag sanitation."""

from decimal import Decimal

import pytest

from vision_bill.model.receipt import MAX_TAG_LENGTH, LineItem


def _line_item(**overrides: object) -> LineItem:
    base: dict = {
        "description": "Item",
        "quantity": 1,
        "unit_price": Decimal("1.00"),
        "total_price": Decimal("1.00"),
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
