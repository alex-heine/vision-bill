from datetime import date
from decimal import Decimal

from vision_bill.model.receipt import Receipt
from vision_bill.service.benchmark_scoring import PROMPT_VERSION, SCORING_VERSION, score_receipts


def _receipt(items: list[tuple[str, str]]) -> Receipt:
    return Receipt(
        confidence=90,
        merchant_name="Test Store",
        date=date(2025, 1, 1),
        line_items=[
            {
                "description": description,
                "spending_category": category,
                "quantity": 1,
                "unit_price": Decimal("2.00"),
                "total_price": Decimal("2.00"),
            }
            for description, category in items
        ],
        subtotal=Decimal("2.00"),
        total=Decimal("2.00"),
    )


def test_wrong_category_is_scored_separately_from_correct_item_and_price() -> None:
    expected = _receipt([("Milk", "milk")])
    actual = _receipt([("Milk", "cheese")])

    scores = score_receipts(expected, actual)

    assert scores["line_items"] == 1.0
    assert scores["spending_categories"] == 0.0
    assert scores["overall"] == score_receipts(expected, expected)["overall"]


def test_unknown_expected_categories_are_excluded() -> None:
    expected = _receipt([("Milk", "milk"), ("Mystery item", "unknown")])
    actual = _receipt([("Milk", "milk"), ("Mystery item", "cheese")])

    assert score_receipts(expected, actual)["spending_categories"] == 1.0


def test_missing_actual_item_counts_as_category_mismatch() -> None:
    expected = _receipt([("Milk", "milk"), ("Bread", "bread_bakery")])
    actual = _receipt([("Milk", "milk")])

    assert score_receipts(expected, actual)["spending_categories"] == 0.5


def test_category_on_wrong_description_does_not_match() -> None:
    expected = _receipt([("Milk", "milk")])
    actual = _receipt([("Bread", "milk")])

    assert score_receipts(expected, actual)["spending_categories"] == 0.0


def test_category_component_is_omitted_without_expected_labels() -> None:
    scores = score_receipts(_receipt([("Mystery item", "unknown")]), _receipt([]))

    assert "spending_categories" not in scores


def test_prompt_and_scoring_versions_reflect_category_changes() -> None:
    assert PROMPT_VERSION == "4"
    assert SCORING_VERSION == "2"
