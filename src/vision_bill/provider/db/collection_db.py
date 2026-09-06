"""Owns the asyncpg pool and all SQL for collections."""

import logging
from collections.abc import Mapping
from datetime import date as Date
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from ...model.collection import Collection, CollectionDetail, CollectionSummary, CurrencyTotal
from ...model.db.receipt import ReceiptRow

logger = logging.getLogger(__name__)

CREATE_COLLECTION_SQL = (
    "INSERT INTO collections (user_id, name, color, start_date, end_date, active) "
    "VALUES ($1, $2, $3, $4, $5, $6) RETURNING *"
)
ACTIVATE_DEACTIVATE_SIBLINGS_SQL = "UPDATE collections SET active = FALSE WHERE user_id = $1"
SET_ACTIVE_SQL = "UPDATE collections SET active = TRUE WHERE id = $1 RETURNING *"
SET_INACTIVE_SQL = "UPDATE collections SET active = FALSE WHERE id = $1 RETURNING *"
GET_ACTIVE_SQL = "SELECT * FROM collections WHERE active = TRUE"
GET_COLLECTION_SQL = "SELECT * FROM collections WHERE id = $1"
# One query per list (no N+1): each collection carries its receipt count via a
# correlated subquery exposed as `cnt`.
LIST_COLLECTIONS_BASE_SQL = (
    "SELECT c.*, (SELECT COUNT(*)::int FROM receipt_collections rc "
    "WHERE rc.collection_id = c.id) AS cnt FROM collections c"
)
UPDATE_COLLECTION_SQL = (
    "UPDATE collections SET name = $3, color = $4, start_date = $5, end_date = $6 "
    "WHERE id = $2 RETURNING *"
)
DELETE_COLLECTION_SQL = "DELETE FROM collections WHERE id = $1 RETURNING id"
EXISTS_COLLECTION_SQL = "SELECT 1 AS x FROM collections WHERE id = $1"

COUNT_COLLECTION_SQL = (
    "SELECT COUNT(*)::int AS cnt FROM receipt_collections WHERE collection_id = $1"
)
TOTALS_PER_CURRENCY_SQL = (
    "SELECT r.currency AS currency, SUM(r.total) AS total "
    "FROM receipt_collections rc JOIN receipts r ON r.id = rc.receipt_id "
    "WHERE rc.collection_id = $1 GROUP BY r.currency ORDER BY total DESC"
)
RECEIPTS_IN_COLLECTION_SQL = (
    "SELECT r.* FROM receipts r JOIN receipt_collections rc "
    "ON rc.receipt_id = r.id WHERE rc.collection_id = $1"
)
ASSIGN_SQL = (
    "INSERT INTO receipt_collections (receipt_id, collection_id) "
    "VALUES ($1, $2) ON CONFLICT (receipt_id, collection_id) DO NOTHING"
)
UNASSIGN_SQL = (
    "DELETE FROM receipt_collections WHERE receipt_id = $1 AND collection_id = $2 RETURNING 1"
)
LIST_COLLECTION_IDS_FOR_RECEIPT_SQL = (
    "SELECT collection_id FROM receipt_collections WHERE receipt_id = $1"
)
DELETE_RECEIPT_COLLECTIONS_SQL = "DELETE FROM receipt_collections WHERE receipt_id = $1"


class CollectionDB:
    """All SQL for collections; reuses the receipt DB's asyncpg pool (no own pool)."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @property
    def pool(self) -> asyncpg.Pool:
        return self._pool

    @staticmethod
    def _collection_from_row(row: Mapping[str, Any]) -> Collection:
        return Collection(
            id=row["id"],
            name=row["name"],
            color=row["color"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            active=row["active"],
            created_at=row["created_at"].date() if row["created_at"] is not None else None,
        )

    def _owner_scope(self, args: list[Any], user_id: UUID | None, can_see_all: bool) -> str:
        """Return an extra WHERE fragment restricting to the owner when needed."""
        if not can_see_all and user_id is not None:
            args.append(user_id)
            return f" AND user_id = ${len(args)}"
        return ""

    async def create(
        self,
        user_id: UUID,
        name: str,
        color: str | None,
        start_date: Date | None,
        end_date: Date | None,
        active: bool = False,
    ) -> Collection:
        async with self.pool.acquire() as conn:
            if active:
                await conn.execute(ACTIVATE_DEACTIVATE_SIBLINGS_SQL, user_id)
            row = await conn.fetchrow(
                CREATE_COLLECTION_SQL, user_id, name, color, start_date, end_date, active
            )
        return self._collection_from_row(row)

    async def list_with_totals(
        self, user_id: UUID | None, can_see_all: bool
    ) -> list[CollectionSummary]:
        args: list[Any] = []
        sql = LIST_COLLECTIONS_BASE_SQL + (
            " WHERE 1=1" + self._owner_scope(args, user_id, can_see_all) + " ORDER BY name"
        )
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            summaries: list[CollectionSummary] = []
            for row in rows:
                base = self._collection_from_row(row)
                count = int(row["cnt"])
                if count > 0:
                    total_rows = await conn.fetch(TOTALS_PER_CURRENCY_SQL, row["id"])
                    totals = [
                        CurrencyTotal(currency=r["currency"], total=Decimal(r["total"]))
                        for r in total_rows
                    ]
                else:
                    totals = []
                summaries.append(
                    CollectionSummary(**base.model_dump(), receipt_count=count, totals=totals)
                )
        return summaries

    async def get(
        self, collection_id: UUID, user_id: UUID | None, can_see_all: bool
    ) -> Collection | None:
        args: list[Any] = [collection_id]
        sql = GET_COLLECTION_SQL + self._owner_scope(args, user_id, can_see_all)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
        return self._collection_from_row(row) if row is not None else None

    async def find_by_name(self, user_id: UUID, name: str) -> Collection | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM collections WHERE user_id = $1 AND lower(name) = lower($2)",
                user_id,
                name,
            )
        return self._collection_from_row(row) if row is not None else None

    async def update(
        self,
        collection_id: UUID,
        user_id: UUID | None,
        can_see_all: bool,
        name: str | None,
        color: str | None,
        start_date: Date | None,
        end_date: Date | None,
    ) -> Collection | None:
        args: list[Any] = [collection_id, collection_id, name, color, start_date, end_date]
        sql = UPDATE_COLLECTION_SQL
        if not can_see_all and user_id is not None:
            args.append(user_id)
            sql += f" AND user_id = ${len(args)}"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
        return self._collection_from_row(row) if row is not None else None

    async def delete(self, collection_id: UUID, user_id: UUID | None, can_see_all: bool) -> bool:
        args: list[Any] = [collection_id]
        sql = DELETE_COLLECTION_SQL
        if not can_see_all and user_id is not None:
            args.append(user_id)
            sql += f" AND user_id = ${len(args)}"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
        return row is not None

    async def exists(self, collection_id: UUID, user_id: UUID | None, can_see_all: bool) -> bool:
        args: list[Any] = [collection_id]
        sql = EXISTS_COLLECTION_SQL + self._owner_scope(args, user_id, can_see_all)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
        return row is not None

    async def active_collection(self, user_id: UUID | None, can_see_all: bool) -> Collection | None:
        args: list[Any] = []
        sql = GET_ACTIVE_SQL + self._owner_scope(args, user_id, can_see_all) + " LIMIT 1"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
        return self._collection_from_row(row) if row is not None else None

    async def activate(
        self, collection_id: UUID, user_id: UUID | None, can_see_all: bool
    ) -> Collection | None:
        """Mark active, deactivating the user's other active collection (one active per user)."""
        args: list[Any] = [collection_id]
        set_sql = SET_ACTIVE_SQL
        if not can_see_all and user_id is not None:
            args.append(user_id)
            set_sql += f" AND user_id = ${len(args)}"
        # No explicit transaction (matches the rest of the DB layer, which issues
        # single auto-committed statements): deactivating siblings and setting the
        # target active are two cheap statements; the partial unique index
        # ux_collections_one_active_per_user still guarantees at most one active.
        async with self.pool.acquire() as conn:
            if not can_see_all and user_id is not None:
                await conn.execute(ACTIVATE_DEACTIVATE_SIBLINGS_SQL, user_id)
            row = await conn.fetchrow(set_sql, *args)
        return self._collection_from_row(row) if row is not None else None

    async def deactivate(
        self, collection_id: UUID, user_id: UUID | None, can_see_all: bool
    ) -> Collection | None:
        args: list[Any] = [collection_id]
        set_sql = SET_INACTIVE_SQL
        if not can_see_all and user_id is not None:
            args.append(user_id)
            set_sql += f" AND user_id = ${len(args)}"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(set_sql, *args)
        return self._collection_from_row(row) if row is not None else None

    async def assign(self, collection_id: UUID, receipt_id: UUID) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(ASSIGN_SQL, receipt_id, collection_id)

    async def unassign(self, collection_id: UUID, receipt_id: UUID) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(UNASSIGN_SQL, receipt_id, collection_id)
        return row is not None

    async def collection_ids_for_receipt(self, receipt_id: UUID) -> list[UUID]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(LIST_COLLECTION_IDS_FOR_RECEIPT_SQL, receipt_id)
        return [row["collection_id"] for row in rows]

    async def set_receipt_collections(self, receipt_id: UUID, collection_ids: list[UUID]) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(DELETE_RECEIPT_COLLECTIONS_SQL, receipt_id)
            for cid in collection_ids:
                await conn.execute(ASSIGN_SQL, receipt_id, cid)

    async def receipts_in_collection(
        self, collection_id: UUID, user_id: UUID | None, can_see_all: bool
    ) -> list[ReceiptRow]:
        args: list[Any] = [collection_id]
        sql = RECEIPTS_IN_COLLECTION_SQL + self._owner_scope(args, user_id, can_see_all)
        sql += " ORDER BY r.date DESC"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return [self._receipt_row(r) for r in rows]

    @staticmethod
    def _receipt_row(row: Mapping[str, Any]) -> ReceiptRow:
        from ...provider.db.receipt_db import ReceiptDB

        return ReceiptDB._receipt_row_from_record(row)

    # Convenience detail assembly used by the service.
    async def get_detail(
        self, collection_id: UUID, user_id: UUID | None, can_see_all: bool
    ) -> CollectionDetail | None:
        coll = await self.get(collection_id, user_id, can_see_all)
        if coll is None:
            return None
        async with self.pool.acquire() as conn:
            total_rows = await conn.fetch(TOTALS_PER_CURRENCY_SQL, collection_id)
        receipts = await self.receipts_in_collection(collection_id, user_id, can_see_all)
        totals = [
            CurrencyTotal(currency=r["currency"], total=Decimal(r["total"])) for r in total_rows
        ]
        return CollectionDetail(**coll.model_dump(), totals=totals, receipts=receipts)
