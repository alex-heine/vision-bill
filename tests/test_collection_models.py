"""Pure model/helper tests for collections (no DB)."""

from datetime import date

import pytest
from pydantic import ValidationError

from vision_bill.model.collection import (
    Collection,
    CollectionCreate,
    CollectionDetail,
    CollectionSummary,
    is_valid_hex_color,
    normalize_collection_name,
)
from vision_bill.model.db.receipt import ReceiptRow


def test_normalize_collection_name_collapses_whitespace() -> None:
    assert normalize_collection_name("  Berlin   Trip  2026 ") == "Berlin Trip 2026"
    assert normalize_collection_name("   ") == ""
    assert normalize_collection_name("") == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#123", True),
        ("#123456", True),
        ("#aabbcc", True),
        ("#AABBCC", True),
        ("123", False),
        ("#12345", False),
        ("#1234567", False),
        ("", False),
        ("red", False),
    ],
)
def test_is_valid_hex_color(value: str, expected: bool) -> None:
    assert is_valid_hex_color(value) is expected


def test_create_requires_name() -> None:
    with pytest.raises(ValidationError):
        CollectionCreate(name="   ")
    c = CollectionCreate(
        name="Berlin", color="#112233", start_date=date(2026, 6, 3), end_date=date(2026, 6, 9)
    )
    assert c.name == "Berlin" and c.color == "#112233"


def test_summary_and_detail_defaults() -> None:
    import uuid

    cid = uuid.uuid4()
    s = CollectionSummary(id=cid, name="Berlin", receipt_count=0, totals=[])
    assert s.receipt_count == 0
    d = CollectionDetail(id=cid, name="Berlin", totals=[], receipts=[])
    assert d.receipts == []
