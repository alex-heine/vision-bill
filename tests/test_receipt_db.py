"""Tests for ReceiptDB — pool lifecycle and SQL behaviour with mocked asyncpg."""

import logging
from datetime import UTC, datetime
from datetime import date as Date
from datetime import time as Time
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vision_bill.config import Settings
from vision_bill.model.receipt import LineItem, Receipt, TaxLine
from vision_bill.provider.db.receipt_db import (
    DELETE_LINE_ITEMS_SQL,
    DELETE_TAXES_SQL,
    INSERT_LINE_ITEM_SQL,
    INSERT_TAX_SQL,
    ReceiptDB,
)

PATCH_TARGET = "vision_bill.provider.db.receipt_db.asyncpg"


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
    receipt_id: int = 1,
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
        "subtotal": Decimal("50.00"),
        "discount_total": Decimal("0.00"),
        "tax_total": Decimal("4.50"),
        "tip": None,
        "total": Decimal("54.50"),
        "payment_method": "credit_card",
        "status": "unverified",
        "image_path": None,
        "created_at": datetime(2024, 1, 15, 14, 30, tzinfo=UTC),
        "verified": False,
    }
    row.update(overrides)
    return row


def _line_item_row(receipt_id: int = 1) -> dict[str, Any]:
    return {
        "id": 1,
        "receipt_id": receipt_id,
        "description": "Item A",
        "quantity": Decimal("2.0000"),
        "unit_price": Decimal("10.00"),
        "total_price": Decimal("20.00"),
        "category": "other",
    }


def _tax_row(receipt_id: int = 1) -> dict[str, Any]:
    return {
        "id": 1,
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
        line_items=[
            LineItem(
                description="Item A",
                quantity=2,
                unit_price=Decimal("10.00"),
                total_price=Decimal("20.00"),
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
    mock_conn.fetchrow = AsyncMock(return_value=_receipt_row(image_path="x"))
    mock_conn.execute = AsyncMock()

    receipt = _make_receipt()

    result = await db.persist_receipt(receipt, image_path="x", status="unverified")

    assert result.id == 1
    assert result.confidence == 95
    assert result.merchant_name == "Test Store"
    assert result.status == "unverified"
    assert result.verified is False
    assert result.image_path == "x"
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
    # status and image_path are the last two bound parameters
    assert fetchrow_call.args[14] == "unverified"
    assert fetchrow_call.args[15] == "x"

    assert mock_conn.fetchrow.call_count == 1
    # One execute each for the line item and the tax
    assert mock_conn.execute.call_count == 2


@pytest.mark.asyncio
async def test_get_receipt_by_found(db: ReceiptDB) -> None:
    """get_receipt_by_id should return a ReceiptRow when found."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(
        return_value=_receipt_row(receipt_id=42, merchant_name="Found Store", status="verified")
    )

    result = await db.get_receipt_by_id(42)

    assert result is not None
    assert result.id == 42
    assert result.merchant_name == "Found Store"
    assert result.status == "verified"


@pytest.mark.asyncio
async def test_get_receipt_by_not_found(db: ReceiptDB) -> None:
    """get_receipt_by_id should return None when the receipt doesn't exist."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value=None)

    result = await db.get_receipt_by_id(999)

    assert result is None


@pytest.mark.asyncio
async def test_list_receipts(db: ReceiptDB) -> None:
    """list_receipts should return a paginated list of receipts."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetch = AsyncMock(
        return_value=[
            _receipt_row(receipt_id=2, merchant_name="Store B"),
            _receipt_row(receipt_id=1, merchant_name="Store A"),
        ]
    )

    results = await db.list_receipts(limit=10, offset=0)

    assert len(results) == 2
    assert results[0].merchant_name == "Store B"
    assert results[1].merchant_name == "Store A"


@pytest.mark.asyncio
async def test_get_receipt_with_details(db: ReceiptDB) -> None:
    """get_receipt_with_details should combine row, line items and taxes."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value=_receipt_row(receipt_id=5))

    def fetch_side_effect(sql: str, *args: object) -> list[dict[str, Any]]:
        if "line_items" in sql:
            return [_line_item_row(5)]
        if "taxes" in sql:
            return [_tax_row(5)]
        return []

    mock_conn.fetch = AsyncMock(side_effect=fetch_side_effect)

    details = await db.get_receipt_with_details(5)

    assert details is not None
    assert details.receipt.id == 5
    assert len(details.line_items) == 1
    assert details.line_items[0].description == "Item A"
    assert details.line_items[0].quantity == 2.0
    assert len(details.taxes) == 1
    assert details.taxes[0].rate == 0.19


# ── Update and verify ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_receipt(db: ReceiptDB) -> None:
    """update_receipt should UPDATE ... RETURNING, delete children, re-insert."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(
        return_value=_receipt_row(receipt_id=1, merchant_name="Updated Store")
    )
    mock_conn.execute = AsyncMock()

    receipt = _make_receipt(merchant_name="Updated Store")

    result = await db.update_receipt(1, receipt)

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

    result = await db.update_receipt(999, _make_receipt())

    assert result is None
    mock_conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_verify_receipt(db: ReceiptDB) -> None:
    """verify_receipt should set status='verified' and map the RETURNING row."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(
        return_value=_receipt_row(
            receipt_id=1, status="verified", verified=True, image_path="/save/receipt_1.png"
        )
    )

    result = await db.verify_receipt(1, "/save/receipt_1.png")

    assert result is not None
    assert result.status == "verified"
    assert result.verified is True
    assert result.image_path == "/save/receipt_1.png"

    fetchrow_call = mock_conn.fetchrow.call_args
    assert fetchrow_call is not None
    assert "status = 'verified'" in fetchrow_call.args[0]
    assert "verified = TRUE" in fetchrow_call.args[0]
    assert "RETURNING *" in fetchrow_call.args[0]
    assert fetchrow_call.args[1] == 1
    assert fetchrow_call.args[2] == "/save/receipt_1.png"


@pytest.mark.asyncio
async def test_verify_receipt_not_found(db: ReceiptDB) -> None:
    """verify_receipt should return None when no receipt row matched."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value=None)

    result = await db.verify_receipt(999, None)

    assert result is None
