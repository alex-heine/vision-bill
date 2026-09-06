"""CollectionDB — SQL behaviour with mocked asyncpg."""

from datetime import date as Date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from vision_bill.provider.db.collection_db import CollectionDB

PATCH_TARGET = "vision_bill.provider.db.collection_db.asyncpg"
CID = UUID("00000000-0000-4000-8000-0000000000c1")
RID = UUID("00000000-0000-4000-8000-0000000000d1")
UID = UUID("00000000-0000-4000-8000-0000000000a1")


def _make_pool(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=None)
        )
    )
    return pool


def _collection_row(**over: Any) -> dict[str, Any]:
    row = {
        "id": CID,
        "user_id": UID,
        "name": "Berlin",
        "color": "#3B82F6",
        "start_date": Date(2026, 6, 3),
        "end_date": Date(2026, 6, 9),
        "active": False,
        "created_at": None,
    }
    row.update(over)
    return row


def _receipt_row() -> dict[str, Any]:
    return {
        "id": RID,
        "confidence": 90,
        "merchant_name": "M",
        "merchant_address": None,
        "receipt_number": None,
        "date": Date(2026, 6, 5),
        "time": None,
        "currency": "EUR",
        "category": "other",
        "subtotal": Decimal("10"),
        "discount_total": Decimal("0"),
        "tax_total": Decimal("0"),
        "tip": None,
        "total": Decimal("10"),
        "payment_method": "unknown",
        "status": "verified",
        "image_id": None,
        "created_at": None,
        "verified": True,
        "user_id": UID,
    }


@pytest.fixture
def db() -> CollectionDB:
    return CollectionDB(MagicMock())  # pool replaced per-test via db._pool


@pytest.mark.asyncio
async def test_create_returns_collection(db: CollectionDB) -> None:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=_collection_row())
    db._pool = _make_pool(conn)
    result = await db.create(UID, "Berlin", "#3B82F6", Date(2026, 6, 3), Date(2026, 6, 9))
    assert result.id == CID and result.name == "Berlin"
    assert "INSERT INTO collections" in conn.fetchrow.call_args.args[0]


@pytest.mark.asyncio
async def test_list_with_totals_builds_summaries(db: CollectionDB) -> None:
    conn = AsyncMock()
    # First fetch = the collection list (each row carries `cnt` via the list
    # SQL's subquery); second fetch = per-currency totals for that (non-empty)
    # collection.
    conn.fetch = AsyncMock(
        side_effect=[
            [
                {
                    "id": CID,
                    "user_id": UID,
                    "name": "Berlin",
                    "color": "#3B82F6",
                    "start_date": None,
                    "end_date": None,
                    "active": False,
                    "created_at": None,
                    "cnt": 3,
                },
            ],
            [{"currency": "EUR", "total": Decimal("100")}],
        ]
    )
    db._pool = _make_pool(conn)
    summaries = await db.list_with_totals(UID, can_see_all=False)
    assert summaries[0].receipt_count == 3
    # per-currency total query ran for the (existing) collection
    total_calls = [c for c in conn.fetch.call_args_list if "GROUP BY r.currency" in c.args[0]]
    assert total_calls, "expected a per-currency totals fetch"


@pytest.mark.asyncio
async def test_assign_is_idempotent_insert(db: CollectionDB) -> None:
    conn = AsyncMock()
    db._pool = _make_pool(conn)
    await db.assign(CID, RID)
    sql = conn.execute.call_args.args[0]
    assert "INSERT INTO receipt_collections" in sql
    assert "ON CONFLICT" in sql


@pytest.mark.asyncio
async def test_unassign_reports_missing(db: CollectionDB) -> None:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    db._pool = _make_pool(conn)
    assert await db.unassign(CID, RID) is False


@pytest.mark.asyncio
async def test_set_receipt_collections_replaces_links(db: CollectionDB) -> None:
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[{"collection_id": CID}])
    db._pool = _make_pool(conn)
    other = UUID("00000000-0000-4000-8000-0000000000c2")
    await db.set_receipt_collections(RID, [CID, other])
    deletes = [
        c.args[0]
        for c in conn.execute.call_args_list
        if "DELETE FROM receipt_collections" in c.args[0]
    ]
    inserts = [
        c.args[0]
        for c in conn.execute.call_args_list
        if "INSERT INTO receipt_collections" in c.args[0]
    ]
    assert deletes and inserts


@pytest.mark.asyncio
async def test_get_scopes_to_owner(db: CollectionDB) -> None:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=_collection_row())
    db._pool = _make_pool(conn)
    got = await db.get(CID, UID, can_see_all=False)
    assert got is not None
    sql = conn.fetchrow.call_args.args[0]
    assert "AND user_id = $2" in sql


@pytest.mark.asyncio
async def test_receipts_in_collection_scopes_owner(db: CollectionDB) -> None:
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[_receipt_row()])
    db._pool = _make_pool(conn)
    rows = await db.receipts_in_collection(CID, UID, can_see_all=False)
    assert len(rows) == 1 and rows[0].id == RID


@pytest.mark.asyncio
async def test_active_collection_scopes_owner(db: CollectionDB) -> None:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=_collection_row(active=True))
    db._pool = _make_pool(conn)
    got = await db.active_collection(UID, can_see_all=False)
    assert got is not None and got.active is True
    sql = conn.fetchrow.call_args.args[0]
    assert "active = TRUE" in sql and "AND user_id = $1" in sql and "LIMIT 1" in sql


@pytest.mark.asyncio
async def test_activate_deactivates_siblings_and_sets_active(db: CollectionDB) -> None:
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=_collection_row(active=True))
    db._pool = _make_pool(conn)
    got = await db.activate(CID, UID, can_see_all=False)
    assert got is not None and got.active is True
    # sibling deactivation ran for the owner, and the set-active SQL carried the owner scope
    exec_sqls = [c.args[0] for c in conn.execute.call_args_list]
    assert any("SET active = FALSE WHERE user_id" in s for s in exec_sqls)
    set_sql = conn.fetchrow.call_args.args[0]
    assert (
        set_sql.startswith("UPDATE collections SET active = TRUE") and "AND user_id = $2" in set_sql
    )


@pytest.mark.asyncio
async def test_activate_returns_none_for_foreign_owner(db: CollectionDB) -> None:
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    db._pool = _make_pool(conn)
    assert await db.activate(CID, UID, can_see_all=False) is None
    # A non-owned target must be a no-op: the sibling deactivation must NOT run,
    # otherwise the caller's own active collection would be silently destroyed.
    conn.execute.assert_not_called()


@pytest.mark.asyncio
async def test_deactivate_sets_inactive(db: CollectionDB) -> None:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=_collection_row(active=False))
    db._pool = _make_pool(conn)
    got = await db.deactivate(CID, UID, can_see_all=False)
    assert got is not None and got.active is False
    assert conn.fetchrow.call_args.args[0].startswith(
        "UPDATE collections SET active = FALSE WHERE id"
    )
