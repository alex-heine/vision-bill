"""Tests for ReceiptDB — pool lifecycle and SQL behaviour with mocked asyncpg."""

import logging
from datetime import UTC, datetime
from datetime import date as Date
from datetime import time as Time
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from vision_bill.config import Settings
from vision_bill.model.receipt import LineItem, Receipt, TaxLine
from vision_bill.provider.db.receipt_db import (
    DELETE_LINE_ITEMS_SQL,
    DELETE_RECEIPT_SQL,
    DELETE_TAXES_SQL,
    INSERT_LINE_ITEM_SQL,
    INSERT_TAG_SQL,
    INSERT_TAX_SQL,
    LIST_TAGS_SQL,
    SEARCH_PRODUCTS_BASE_SQL,
    ReceiptDB,
)

PATCH_TARGET = "vision_bill.provider.db.receipt_db.asyncpg"
RECEIPT_ID = UUID("00000000-0000-4000-8000-000000000001")
OTHER_RECEIPT_ID = UUID("00000000-0000-4000-8000-000000000002")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000003")
LINE_ITEM_ID = UUID("00000000-0000-4000-8000-000000000004")
TAX_ID = UUID("00000000-0000-4000-8000-000000000005")


def _make_pool(conn: AsyncMock) -> MagicMock:
    """Build a mock pool whose acquire() yields the given conn."""
    pool = MagicMock()
    pool.acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=None),
        )
    )
    return pool


def _receipt_row(
    receipt_id: UUID = RECEIPT_ID,
    **overrides: object,
) -> dict[str, Any]:
    """A realistic asyncpg receipts row (driver types, not strings)."""
    row: dict[str, Any] = {
        "id": receipt_id,
        "confidence": 95,
        "merchant_name": "Test Store",
        "merchant_address": "123 Main St",
        "receipt_number": "R-001",
        "date": Date(2024, 1, 15),
        "time": Time(14, 30),
        "currency": "USD",
        "category": "other",
        "subtotal": Decimal("50.00"),
        "discount_total": Decimal("0.00"),
        "tax_total": Decimal("4.50"),
        "tip": None,
        "total": Decimal("54.50"),
        "payment_method": "credit_card",
        "status": "unverified",
        "image_id": None,
        "created_at": datetime(2024, 1, 15, 14, 30, tzinfo=UTC),
        "verified": False,
    }
    row.update(overrides)
    return row


def _line_item_row(receipt_id: UUID = RECEIPT_ID) -> dict[str, Any]:
    return {
        "id": LINE_ITEM_ID,
        "receipt_id": receipt_id,
        "description": "Item A",
        "quantity": Decimal("2.0000"),
        "unit_price": Decimal("10.00"),
        "total_price": Decimal("20.00"),
        "tags": ["test"],
    }


def _tax_row(receipt_id: UUID = RECEIPT_ID) -> dict[str, Any]:
    return {
        "id": TAX_ID,
        "receipt_id": receipt_id,
        "name": "VAT",
        "rate": Decimal("0.1900"),
        "amount": Decimal("4.50"),
    }


def _make_receipt(merchant_name: str = "Test Store") -> Receipt:
    return Receipt(
        confidence=95,
        merchant_name=merchant_name,
        merchant_address="123 Main St",
        receipt_number="R-001",
        date=Date(2024, 1, 15),
        time="14:30",
        currency="USD",
        category="grocery",
        line_items=[
            LineItem(
                description="Item A",
                quantity=2,
                unit_price=Decimal("10.00"),
                total_price=Decimal("20.00"),
                tags=["test"],
            )
        ],
        taxes=[TaxLine(name="VAT", rate=0.19, amount=Decimal("4.50"))],
        subtotal=Decimal("50.00"),
        discount_total=Decimal(0),
        tax_total=Decimal("4.50"),
        total=Decimal("54.50"),
        payment_method="credit_card",
    )


@pytest.fixture
def db(settings: Settings) -> ReceiptDB:
    return ReceiptDB(settings.pg)


# ── Connection pool lifecycle tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_init_db_creates_pool(db: ReceiptDB, caplog: pytest.LogCaptureFixture) -> None:
    """init_db should create the pool, run the to_regclass check, and skip DDL."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"missing": False})
    mock_pool = _make_pool(mock_conn)

    with (
        patch(PATCH_TARGET) as mock_asyncpg,
        caplog.at_level(logging.INFO, logger="vision_bill.provider.db.receipt_db"),
    ):
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
        await db.init_db()

    mock_asyncpg.create_pool.assert_called_once()
    assert db._pool is mock_pool
    # No DDL in the app code anymore — migrations own the schema.
    mock_conn.execute.assert_not_called()
    # The to_regclass sanity check IS executed against the acquired connection.
    mock_conn.fetchrow.assert_called_once()
    assert "to_regclass('receipts')" in mock_conn.fetchrow.call_args.args[0]
    # Table present -> no "schema not initialised" warning.
    assert not any("Schema not initialised" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_init_db_warns_when_schema_missing(
    db: ReceiptDB, caplog: pytest.LogCaptureFixture
) -> None:
    """init_db should warn (not raise) when the receipts table is missing."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"missing": True})
    mock_pool = _make_pool(mock_conn)

    with (
        patch(PATCH_TARGET) as mock_asyncpg,
        caplog.at_level(logging.INFO, logger="vision_bill.provider.db.receipt_db"),
    ):
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
        await db.init_db()

    assert db._pool is mock_pool
    mock_conn.execute.assert_not_called()
    assert any("Schema not initialised" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_destroy_db_closes_pool(db: ReceiptDB) -> None:
    """destroy_db should close the pool and set it to None."""
    mock_pool = MagicMock()
    mock_pool.close = AsyncMock()
    db._pool = mock_pool

    await db.destroy_db()

    mock_pool.close.assert_called_once()
    assert db._pool is None


@pytest.mark.asyncio
async def test_init_db_skips_when_already_init(db: ReceiptDB) -> None:
    """init_db should skip if the pool already exists."""
    db._pool = MagicMock()

    with patch(PATCH_TARGET) as mock_asyncpg:
        mock_asyncpg.create_pool = AsyncMock()
        await db.init_db()

    mock_asyncpg.create_pool.assert_not_called()


def test_pool_property_raises_when_not_init(db: ReceiptDB) -> None:
    """pool property should raise RuntimeError if not initialised."""
    with pytest.raises(RuntimeError, match="Database pool not initialised"):
        _ = db.pool


# ── Persist and query tests (mocked pool) ────────────────────────────


@pytest.mark.asyncio
async def test_persist_receipt(db: ReceiptDB) -> None:
    """persist_receipt should insert receipt + line items + taxes."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value=_receipt_row(image_id=IMAGE_ID, category="grocery"))
    mock_conn.execute = AsyncMock()

    receipt = _make_receipt()

    result = await db.persist_receipt(receipt, image_id=IMAGE_ID, status="unverified")

    assert result.id == RECEIPT_ID
    assert result.confidence == 95
    assert result.merchant_name == "Test Store"
    assert result.status == "unverified"
    assert result.category == "grocery"
    assert result.verified is False
    assert result.image_id == IMAGE_ID
    assert result.time == "14:30:00"
    assert result.created_at == Date(2024, 1, 15)

    # The TIME column must be bound as datetime.time, never a string
    fetchrow_call = mock_conn.fetchrow.call_args
    assert fetchrow_call is not None
    # confidence is the first bound parameter
    assert fetchrow_call.args[1] == 95
    bound_time = fetchrow_call.args[6]
    assert isinstance(bound_time, Time)
    assert bound_time == Time(14, 30)
    # category is the 8th bound parameter
    assert fetchrow_call.args[8] == "grocery"
    # status, verified, user_id and image_id are the last bound parameters
    assert fetchrow_call.args[15] == "unverified"
    assert fetchrow_call.args[16] is False
    assert fetchrow_call.args[18] == IMAGE_ID

    assert mock_conn.fetchrow.call_count == 1
    # Deletes replace any previous children, followed by one insert each for
    # the line item and the tax.
    assert mock_conn.execute.call_count == 4


@pytest.mark.asyncio
async def test_get_receipt_by_found(db: ReceiptDB) -> None:
    """get_receipt_by_id should return a ReceiptRow when found."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(
        return_value=_receipt_row(
            receipt_id=RECEIPT_ID, merchant_name="Found Store", status="verified"
        )
    )

    result = await db.get_receipt_by_id(RECEIPT_ID)

    assert result is not None
    assert result.id == RECEIPT_ID
    assert result.merchant_name == "Found Store"
    assert result.status == "verified"


@pytest.mark.asyncio
async def test_get_receipt_by_not_found(db: ReceiptDB) -> None:
    """get_receipt_by_id should return None when the receipt doesn't exist."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value=None)

    result = await db.get_receipt_by_id(OTHER_RECEIPT_ID)

    assert result is None


@pytest.mark.asyncio
async def test_list_receipts(db: ReceiptDB) -> None:
    """list_receipts should return a paginated list of receipts."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetch = AsyncMock(
        return_value=[
            _receipt_row(receipt_id=OTHER_RECEIPT_ID, merchant_name="Store B"),
            _receipt_row(receipt_id=RECEIPT_ID, merchant_name="Store A"),
        ]
    )

    results = await db.list_receipts(limit=10, offset=0)

    assert len(results) == 2
    assert results[0].merchant_name == "Store B"
    assert results[1].merchant_name == "Store A"


@pytest.mark.asyncio
async def test_search_products(db: ReceiptDB) -> None:
    """search_products should match verified line items and map purchase data."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetch = AsyncMock(
        return_value=[
            {
                **_line_item_row(RECEIPT_ID),
                "description": "Gouda Mittelalt",
                "merchant_name": "Test Store",
                "date": Date(2024, 1, 15),
                "time": Time(14, 30),
                "currency": "EUR",
            }
        ]
    )

    results = await db.search_products("gouda")

    assert len(results) == 1
    assert results[0].description == "Gouda Mittelalt"
    assert results[0].unit_price == Decimal("10.00")
    assert results[0].time == "14:30:00"
    fetch_call = mock_conn.fetch.call_args
    assert fetch_call is not None
    assert fetch_call.args[0].startswith(SEARCH_PRODUCTS_BASE_SQL)
    assert "li.description ILIKE $1" in fetch_call.args[0]
    assert fetch_call.args[1] == "%gouda%"


@pytest.mark.asyncio
async def test_get_receipt_with_details(db: ReceiptDB) -> None:
    """get_receipt_with_details should combine row, line items, taxes and image path.

    fetchrow serves the LEFT JOIN query, so the row carries the receipt columns
    plus an extra ``image_path`` key (the mapper drops it, the detail keeps it).
    """
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(
        return_value=_receipt_row(
            receipt_id=RECEIPT_ID, image_id=IMAGE_ID, image_path="/save/img.png"
        )
    )

    def fetch_side_effect(sql: str, *args: object) -> list[dict[str, Any]]:
        if "line_items" in sql:
            return [_line_item_row(RECEIPT_ID)]
        if "taxes" in sql:
            return [_tax_row(RECEIPT_ID)]
        return []

    mock_conn.fetch = AsyncMock(side_effect=fetch_side_effect)

    details = await db.get_receipt_with_details(RECEIPT_ID)

    assert details is not None
    assert details.receipt.id == RECEIPT_ID
    assert details.receipt.image_id == IMAGE_ID
    assert details.image_path == "/save/img.png"
    assert len(details.line_items) == 1
    assert details.line_items[0].description == "Item A"
    assert details.line_items[0].quantity == 2.0
    assert details.line_items[0].tags == ["test"]
    assert len(details.taxes) == 1
    assert details.taxes[0].rate == 0.19


# ── Update and verify ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_receipt(db: ReceiptDB) -> None:
    """update_receipt should UPDATE ... RETURNING, delete children, re-insert."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(
        return_value=_receipt_row(receipt_id=RECEIPT_ID, merchant_name="Updated Store")
    )
    mock_conn.execute = AsyncMock()

    receipt = _make_receipt(merchant_name="Updated Store")

    result = await db.update_receipt(RECEIPT_ID, receipt)

    assert result is not None
    assert result.merchant_name == "Updated Store"

    fetchrow_call = mock_conn.fetchrow.call_args
    assert fetchrow_call is not None
    assert "UPDATE receipts" in fetchrow_call.args[0]
    assert "RETURNING *" in fetchrow_call.args[0]

    executed_sqls = [call.args[0] for call in mock_conn.execute.call_args_list]
    assert DELETE_LINE_ITEMS_SQL in executed_sqls
    assert DELETE_TAXES_SQL in executed_sqls
    assert INSERT_LINE_ITEM_SQL in executed_sqls
    assert INSERT_TAX_SQL in executed_sqls
    # Children must be replaced: deletes happen before re-inserts
    assert executed_sqls.index(DELETE_LINE_ITEMS_SQL) < executed_sqls.index(INSERT_LINE_ITEM_SQL)


@pytest.mark.asyncio
async def test_update_receipt_not_found(db: ReceiptDB) -> None:
    """update_receipt should return None when no receipt row matched."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()

    result = await db.update_receipt(OTHER_RECEIPT_ID, _make_receipt())

    assert result is None
    mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_verify_receipt(db: ReceiptDB) -> None:
    """verify_receipt should set status='verified' and map the RETURNING row."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(
        return_value=_receipt_row(
            receipt_id=RECEIPT_ID, status="verified", verified=True, image_id=IMAGE_ID
        )
    )

    result = await db.verify_receipt(RECEIPT_ID)

    assert result is not None
    assert result.status == "verified"
    assert result.verified is True
    assert result.image_id == IMAGE_ID

    fetchrow_call = mock_conn.fetchrow.call_args
    assert fetchrow_call is not None
    assert "status = 'verified'" in fetchrow_call.args[0]
    assert "verified = TRUE" in fetchrow_call.args[0]
    assert "RETURNING *" in fetchrow_call.args[0]
    assert fetchrow_call.args[1] == RECEIPT_ID


@pytest.mark.asyncio
async def test_verify_receipt_not_found(db: ReceiptDB) -> None:
    """verify_receipt should return None when no receipt row matched."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value=None)

    result = await db.verify_receipt(OTHER_RECEIPT_ID)

    assert result is None


# ── Delete ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_receipt(db: ReceiptDB) -> None:
    """delete_receipt should DELETE ... RETURNING and map the removed row."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(
        return_value=_receipt_row(
            receipt_id=RECEIPT_ID, image_id=IMAGE_ID, merchant_name="Doomed Store"
        )
    )

    result = await db.delete_receipt(RECEIPT_ID)

    assert result is not None
    assert result.id == RECEIPT_ID
    assert result.image_id == IMAGE_ID

    fetchrow_call = mock_conn.fetchrow.call_args
    assert fetchrow_call is not None
    assert fetchrow_call.args[0] == DELETE_RECEIPT_SQL
    assert fetchrow_call.args[1] == RECEIPT_ID


@pytest.mark.asyncio
async def test_delete_receipt_not_found(db: ReceiptDB) -> None:
    """delete_receipt should return None when no receipt row matched."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value=None)

    result = await db.delete_receipt(OTHER_RECEIPT_ID)

    assert result is None


# ── Tags (vocabulary) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tags(db: ReceiptDB) -> None:
    """list_tags maps the name column and preserves the DB ordering."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetch = AsyncMock(return_value=[{"name": "coffee"}, {"name": "food"}])

    result = await db.list_tags()

    assert result == ["coffee", "food"]
    fetch_call = mock_conn.fetch.await_args
    assert fetch_call is not None
    assert fetch_call.args[0] == LIST_TAGS_SQL


@pytest.mark.asyncio
async def test_create_tag_new(db: ReceiptDB) -> None:
    """create_tag inserts the name and reports a fresh creation."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value={"name": "coffee"})

    created = await db.create_tag("coffee")

    assert created is True
    fetchrow_call = mock_conn.fetchrow.await_args
    assert fetchrow_call is not None
    assert fetchrow_call.args[0] == INSERT_TAG_SQL
    assert fetchrow_call.args[1] == "coffee"


@pytest.mark.asyncio
async def test_create_tag_existing_is_not_an_error(db: ReceiptDB) -> None:
    """ON CONFLICT DO NOTHING returns no row for a known tag -> False, no raise."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value=None)

    created = await db.create_tag("coffee")

    assert created is False
    # The insert must be conflict-safe, not a plain INSERT.
    insert_sql = mock_conn.fetchrow.await_args.args[0]
    assert "ON CONFLICT (name) DO NOTHING" in insert_sql


def test_insert_line_item_sql_has_no_category_column() -> None:
    """Line items no longer persist a category; the receipt owns it."""
    assert "category" not in INSERT_LINE_ITEM_SQL
