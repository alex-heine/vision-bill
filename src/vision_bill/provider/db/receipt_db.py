import logging
from collections.abc import Mapping
from datetime import date as Date
from datetime import time as Time
from decimal import Decimal
from typing import Any

import asyncpg

from ...config import PGSettings
from ...model.db.receipt import (
    LineItemRow,
    ReceiptRow,
    ReceiptWithDetails,
    TaxLineRow,
)
from ...model.receipt import Receipt

# ── SQL (DML; DDL lives in alembic/versions/0001_initial_schema.py) ──

INSERT_RECEIPT_SQL = """
    INSERT INTO receipts
        (confidence, merchant_name, merchant_address, receipt_number, date, time,
         currency, category, subtotal, discount_total, tax_total, tip, total,
         payment_method, status, image_id, verified)
    VALUES
        ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
    RETURNING *
"""

UPDATE_RECEIPT_SQL = """
    UPDATE receipts SET
        confidence      = $1,
        merchant_name   = $2,
        merchant_address = $3,
        receipt_number  = $4,
        date            = $5,
        time            = $6,
        currency        = $7,
        category        = $8,
        subtotal        = $9,
        discount_total  = $10,
        tax_total       = $11,
        tip             = $12,
        total           = $13,
        payment_method  = $14
    WHERE id = $15
    RETURNING *
"""

DELETE_LINE_ITEMS_SQL = "DELETE FROM line_items WHERE receipt_id = $1"
DELETE_TAXES_SQL = "DELETE FROM taxes WHERE receipt_id = $1"
DELETE_RECEIPT_SQL = "DELETE FROM receipts WHERE id = $1 RETURNING *"

INSERT_LINE_ITEM_SQL = """
    INSERT INTO line_items
        (receipt_id, description, quantity, unit_price,
         total_price, category, tags)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
"""

INSERT_TAX_SQL = """
    INSERT INTO taxes
        (receipt_id, name, rate, amount)
    VALUES ($1, $2, $3, $4)
"""

GET_RECEIPT_SQL = "SELECT * FROM receipts WHERE id = $1"
# Join the images table so the detail response can expose the resolved
# image_path without a second round-trip.
GET_RECEIPT_WITH_IMAGE_SQL = """
    SELECT r.*, i.image_path
    FROM receipts r
    LEFT JOIN images i ON i.id = r.image_id
    WHERE r.id = $1
"""
LIST_RECEIPTS_BASE_SQL = "SELECT * FROM receipts"
LIST_LINE_ITEMS_SQL = "SELECT * FROM line_items WHERE receipt_id = $1 ORDER BY id"
LIST_TAXES_SQL = "SELECT * FROM taxes WHERE receipt_id = $1 ORDER BY id"
LIST_TAGS_SQL = "SELECT name FROM tags ORDER BY name"
INSERT_TAG_SQL = "INSERT INTO tags (name) VALUES ($1) ON CONFLICT (name) DO NOTHING RETURNING name"
VERIFY_RECEIPT_SQL = (
    "UPDATE receipts SET status = 'verified', verified = TRUE WHERE id = $1 RETURNING *"
)


logger = logging.getLogger(__name__)


class ReceiptDB:
    """Owns the asyncpg pool and all SQL for receipts."""

    def __init__(self, settings: PGSettings):
        self._settings = settings
        self._pool: asyncpg.Pool | None = None

    # ── Connection pool lifecycle ────────────────────────────────────
    async def init_db(self) -> None:
        """Create the connection pool and check that the schema is migrated."""
        if self._pool is not None:
            logger.warning("Database pool already initialised - skipping")
            return

        dsn = self._settings.pg_dsn
        logger.info("Creating asyncpg connection pool (dsn=%s…)", dsn[:30])
        self._pool = await asyncpg.create_pool(dsn=dsn)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT to_regclass('receipts') IS NULL AS missing")
        if row["missing"]:
            logger.warning(
                "Schema not initialised - run 'uv run alembic upgrade head' before starting the app"
            )

    async def destroy_db(self) -> None:
        """Close the connection pool and release all resources."""
        if self._pool is not None:
            logger.info("Closing database connection pool")
            await self._pool.close()
            self._pool = None
            logger.info("Database pool closed")

    @property
    def is_ready(self) -> bool:
        """Whether the connection pool has been initialised."""
        return self._pool is not None

    # ── Helpers ──────────────────────────────────────────────────────

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool not initialised. Call init_db() first.")
        return self._pool

    @staticmethod
    def _receipt_time_value(receipt: Receipt) -> Time | None:
        """Convert the model's ISO time string ("HH:MM" / "HH:MM:SS") to a Time."""
        return Time.fromisoformat(receipt.time) if receipt.time else None

    @staticmethod
    def _receipt_row_from_record(row: Mapping[str, Any]) -> ReceiptRow:
        """Map a raw receipts row to a ReceiptRow with explicit conversions.

        Accepts either an asyncpg.Record or a plain dict. Extra keys (e.g. the
        joined ``image_path`` from the detail query) are dropped.
        """
        d = dict(row)
        d.pop("image_path", None)
        t: Time | None = d["time"]
        d["time"] = t.isoformat() if t is not None else None
        created_at: Date | None = d["created_at"].date() if d["created_at"] is not None else None
        d["created_at"] = created_at
        return ReceiptRow(**d)

    @staticmethod
    def _line_item_row_from_record(row: asyncpg.Record) -> LineItemRow:
        d = dict(row)
        return LineItemRow(
            id=d["id"],
            receipt_id=d["receipt_id"],
            description=d["description"],
            quantity=float(d["quantity"]),
            unit_price=Decimal(d["unit_price"]),
            total_price=Decimal(d["total_price"]),
            category=d["category"],
            tags=list(d.get("tags") or []),
        )

    @staticmethod
    def _tax_row_from_record(row: asyncpg.Record) -> TaxLineRow:
        d = dict(row)
        return TaxLineRow(
            id=d["id"],
            receipt_id=d["receipt_id"],
            name=d["name"],
            rate=float(d["rate"]) if d["rate"] is not None else None,
            amount=Decimal(d["amount"]),
        )

    async def _insert_children(
        self, conn: asyncpg.Connection, receipt_id: int, receipt: Receipt
    ) -> None:
        """Insert the receipt's line items and taxes (shared insert logic)."""
        if receipt.line_items:
            for item in receipt.line_items:
                await conn.execute(
                    INSERT_LINE_ITEM_SQL,
                    receipt_id,
                    item.description,
                    float(item.quantity),
                    float(item.unit_price),
                    float(item.total_price),
                    item.category,
                    list(item.tags),
                )

        if receipt.taxes:
            for tax in receipt.taxes:
                await conn.execute(
                    INSERT_TAX_SQL,
                    receipt_id,
                    tax.name,
                    tax.rate,
                    float(tax.amount),
                )

    # ── Persist extracted data ───────────────────────────────────────

    async def persist_receipt(
        self,
        receipt: Receipt,
        image_id: int | None = None,
        status: str = "unverified",
        verified: bool = False,
    ) -> ReceiptRow:
        """Insert a receipt (with line items and taxes) into PostgreSQL.

        ``image_id`` links the receipt to an ``images`` row (the FK swap); it
        is ``None`` for receipts created without an associated image.
        """
        logger.info(
            "Persisting receipt for '%s' on %s",
            receipt.merchant_name,
            receipt.date,
        )

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                INSERT_RECEIPT_SQL,
                receipt.confidence,
                receipt.merchant_name,
                receipt.merchant_address,
                receipt.receipt_number,
                receipt.date,
                self._receipt_time_value(receipt),
                receipt.currency,
                receipt.category,
                float(receipt.subtotal),
                float(receipt.discount_total),
                float(receipt.tax_total),
                float(receipt.tip) if receipt.tip is not None else None,
                float(receipt.total),
                receipt.payment_method,
                status,
                image_id,
                verified,
            )
            receipt_id: int = row["id"]
            await self._insert_children(conn, receipt_id, receipt)

        return self._receipt_row_from_record(row)

    async def update_receipt(self, receipt_id: int, receipt: Receipt) -> ReceiptRow | None:
        """Update a receipt row and replace its line items and taxes.

        Returns None when no receipt with the given id exists.
        """
        logger.info("Updating receipt %d", receipt_id)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                UPDATE_RECEIPT_SQL,
                receipt.confidence,
                receipt.merchant_name,
                receipt.merchant_address,
                receipt.receipt_number,
                receipt.date,
                self._receipt_time_value(receipt),
                receipt.currency,
                receipt.category,
                float(receipt.subtotal),
                float(receipt.discount_total),
                float(receipt.tax_total),
                float(receipt.tip) if receipt.tip is not None else None,
                float(receipt.total),
                receipt.payment_method,
                receipt_id,
            )
            if row is None:
                return None

            await conn.execute(DELETE_LINE_ITEMS_SQL, receipt_id)
            await conn.execute(DELETE_TAXES_SQL, receipt_id)
            await self._insert_children(conn, receipt_id, receipt)

        return self._receipt_row_from_record(row)

    async def verify_receipt(self, receipt_id: int) -> ReceiptRow | None:
        """Mark a receipt as verified.

        The image path no longer lives on the receipt row — it is moved to the
        permanent location on the ``images`` row by the caller (see
        ``ImageDB.update_image_path``). Returns None when no receipt with the
        given id exists.
        """
        logger.info("Verifying receipt %d", receipt_id)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(VERIFY_RECEIPT_SQL, receipt_id)
        if row is None:
            return None
        return self._receipt_row_from_record(row)

    async def delete_receipt(self, receipt_id: int) -> ReceiptRow | None:
        """Delete a receipt row. Line items and taxes cascade via their foreign keys.

        Returns the deleted row, or None when no receipt with the given id exists.
        A ``benchmark_tasks`` row still referencing the receipt raises
        ``asyncpg.ForeignKeyViolationError`` (that FK has no ON DELETE rule).
        """
        logger.info("Deleting receipt %d", receipt_id)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(DELETE_RECEIPT_SQL, receipt_id)
        if row is None:
            return None
        return self._receipt_row_from_record(row)

    # ── Query helpers ────────────────────────────────────────────────

    async def get_receipt_by_id(self, receipt_id: int) -> ReceiptRow | None:
        """Fetch a single receipt row by its primary key."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(GET_RECEIPT_SQL, receipt_id)
        if row is None:
            return None
        return self._receipt_row_from_record(row)

    async def list_receipts(
        self,
        limit: int = 50,
        offset: int = 0,
        status: list[str] | None = None,
        date_from: Date | None = None,
        date_to: Date | None = None,
        search: str | None = None,
    ) -> list[ReceiptRow]:
        """Return a paginated list of receipts ordered by date descending.

        Optional filters: ``status`` (IN list), an inclusive ``date_from`` /
        ``date_to`` range, and case-insensitive ``search`` over merchant name
        or receipt number.
        """
        where: list[str] = []
        args: list[Any] = []
        if status:
            args.append(status)
            where.append(f"status = ANY(${len(args)})")
        if date_from is not None:
            args.append(date_from)
            where.append(f"date >= ${len(args)}")
        if date_to is not None:
            args.append(date_to)
            where.append(f"date <= ${len(args)}")
        if search:
            pattern = f"%{search}%"
            args.append(pattern)
            where.append(f"(merchant_name ILIKE ${len(args)} OR receipt_number ILIKE ${len(args)})")

        sql = LIST_RECEIPTS_BASE_SQL
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY date DESC LIMIT ${len(args) + 1} OFFSET ${len(args) + 2}"
        args.extend([limit, offset])

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return [self._receipt_row_from_record(row) for row in rows]

    async def get_receipt_with_details(self, receipt_id: int) -> ReceiptWithDetails | None:
        """Fetch a receipt together with its line items, taxes and image path.

        The image path is resolved via a LEFT JOIN on the images table so the
        response exposes it for frontends even though the receipts row only
        stores the FK.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(GET_RECEIPT_WITH_IMAGE_SQL, receipt_id)
            if row is None:
                return None
            li_rows = await conn.fetch(LIST_LINE_ITEMS_SQL, receipt_id)
            tax_rows = await conn.fetch(LIST_TAXES_SQL, receipt_id)

        d = dict(row)
        image_path: str | None = d.get("image_path")
        receipt = self._receipt_row_from_record(row)

        return ReceiptWithDetails(
            receipt=receipt,
            line_items=[self._line_item_row_from_record(r) for r in li_rows],
            taxes=[self._tax_row_from_record(r) for r in tax_rows],
            image_path=image_path,
        )

    async def list_tags(self) -> list[str]:
        """Return the allowed line-item tag vocabulary, ordered by name."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(LIST_TAGS_SQL)
        return [row["name"] for row in rows]

    async def create_tag(self, name: str) -> bool:
        """Insert a tag, returning True when it was newly created.

        Returns False when a tag with this name already exists (ON CONFLICT
        makes the insert a no-op rather than an error).
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(INSERT_TAG_SQL, name)
        return row is not None
