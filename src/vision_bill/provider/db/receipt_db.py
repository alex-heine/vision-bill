import logging
from collections.abc import Mapping
from datetime import date as Date
from datetime import time as Time
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from ...config import PGSettings
from ...model.db.receipt import (
    LineItemRow,
    ReceiptRow,
    ReceiptWithDetails,
    TaxLineRow,
)
from ...model.receipt import Receipt
from ...model.search import ProductPurchase
from ...model.statistics import (
    CurrencyStatistics,
    NamedStatistics,
    ReceiptStatistics,
    WeekdayStatistics,
    WeeklyStatistics,
)

# ── SQL (DML; DDL lives in alembic/versions/0001_initial_schema.py) ──

INSERT_RECEIPT_SQL = """
    INSERT INTO receipts
        (confidence, merchant_name, merchant_address, receipt_number, date, time,
         currency, category, subtotal, discount_total, tax_total, tip, total,
         payment_method, status, image_id, verified, user_id)
    VALUES
        ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
    RETURNING *
"""

UPDATE_RECEIPT_BY_IMAGE_SQL = """
    UPDATE receipts SET
        confidence = $1,
        merchant_name = $2,
        merchant_address = $3,
        receipt_number = $4,
        date = $5,
        time = $6,
        currency = $7,
        category = $8,
        subtotal = $9,
        discount_total = $10,
        tax_total = $11,
        tip = $12,
        total = $13,
        payment_method = $14,
        status = $15,
        verified = $16,
        user_id = $17
    WHERE id = (
        SELECT id FROM receipts
        WHERE image_id = $18
        ORDER BY created_at ASC, id ASC
        LIMIT 1
    )
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
         total_price, tags)
    VALUES ($1, $2, $3, $4, $5, $6)
"""

INSERT_TAX_SQL = """
    INSERT INTO taxes
        (receipt_id, name, rate, amount)
    VALUES ($1, $2, $3, $4)
"""

GET_RECEIPT_SQL = "SELECT * FROM receipts WHERE id = $1"
GET_RECEIPT_BY_IMAGE_ID_SQL = (
    "SELECT * FROM receipts WHERE image_id = $1 ORDER BY created_at ASC, id ASC LIMIT 1"
)
# Join the images table so the detail response can expose the resolved
# image_path without a second round-trip.
GET_RECEIPT_WITH_IMAGE_SQL = """
    SELECT r.*, i.image_path
    FROM receipts r
    LEFT JOIN images i ON i.id = r.image_id
    WHERE r.id = $1
"""
LIST_RECEIPTS_BASE_SQL = "SELECT * FROM receipts"
SEARCH_PRODUCTS_BASE_SQL = """
    SELECT
        li.receipt_id,
        li.description,
        li.quantity,
        li.unit_price,
        r.merchant_name,
        r.date,
        r.time,
        r.currency
    FROM line_items AS li
    JOIN receipts AS r ON r.id = li.receipt_id
    WHERE r.status = 'verified'
      AND r.verified = TRUE
      AND li.description ILIKE $1
"""
STATS_CURRENCY_SQL = """
    SELECT
        currency,
        COUNT(*)::int AS receipt_count,
        SUM(total) AS total,
        AVG(total) AS average,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY total)::numeric AS median,
        MIN(total) AS minimum,
        MAX(total) AS maximum,
        SUM(subtotal) AS subtotal,
        SUM(discount_total) AS discounts,
        SUM(tax_total) AS taxes,
        SUM(COALESCE(tip, 0)) AS tips
    FROM receipts
    WHERE status = 'verified' AND verified = TRUE{scope}
    GROUP BY currency
    ORDER BY total DESC, currency
"""
STATS_NAMED_SQL = """
    SELECT
        {field} AS name,
        currency,
        COUNT(*)::int AS receipt_count,
        SUM(total) AS total,
        AVG(total) AS average
    FROM receipts
    WHERE status = 'verified' AND verified = TRUE{scope}
    GROUP BY {field}, currency
    ORDER BY total DESC, name, currency
"""
STATS_WEEKDAY_SQL = """
    SELECT
        EXTRACT(ISODOW FROM date)::int AS weekday,
        currency,
        COUNT(*)::int AS receipt_count,
        SUM(total) AS total,
        AVG(total) AS average
    FROM receipts
    WHERE status = 'verified' AND verified = TRUE{scope}
    GROUP BY weekday, currency
    ORDER BY weekday, currency
"""
STATS_WEEKLY_SQL = """
    SELECT
        date_trunc('week', date)::date AS week_start,
        currency,
        COUNT(*)::int AS receipt_count,
        SUM(total) AS total,
        AVG(total) AS average
    FROM receipts
    WHERE status = 'verified' AND verified = TRUE
      AND date >= date_trunc('week', CURRENT_DATE) - ${weeks_param} * INTERVAL '1 week'{scope}
    GROUP BY week_start, currency
    ORDER BY week_start, currency
"""
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
            tags=list(d.get("tags") or []),
        )

    @staticmethod
    def _product_purchase_from_record(row: Mapping[str, Any]) -> ProductPurchase:
        d = dict(row)
        t: Time | None = d["time"]
        return ProductPurchase(
            receipt_id=d["receipt_id"],
            description=d["description"],
            merchant_name=d["merchant_name"],
            date=d["date"],
            time=t.isoformat() if t is not None else None,
            quantity=float(d["quantity"]),
            unit_price=Decimal(d["unit_price"]),
            currency=d["currency"],
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
        self, conn: asyncpg.Connection, receipt_id: UUID, receipt: Receipt
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
        image_id: UUID | None = None,
        status: str = "unverified",
        verified: bool = False,
        user_id: UUID | None = None,
    ) -> ReceiptRow:
        """Insert a receipt (with line items and taxes) into PostgreSQL.

        ``image_id`` links the receipt to an ``images`` row (the FK swap); it
        is ``None`` for receipts created without an associated image. ``user_id``
        is the owning user (``None`` for legacy/unowned rows).
        """
        logger.info(
            "Persisting receipt for '%s' on %s",
            receipt.merchant_name,
            receipt.date,
        )

        values = (
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
        )

        async with self.pool.acquire() as conn:
            row = None
            if image_id is not None:
                row = await conn.fetchrow(
                    UPDATE_RECEIPT_BY_IMAGE_SQL,
                    *values,
                    status,
                    verified,
                    user_id,
                    image_id,
                )
            if row is None:
                row = await conn.fetchrow(
                    INSERT_RECEIPT_SQL, *values, status, image_id, verified, user_id
                )
            receipt_id: UUID = row["id"]
            await conn.execute(DELETE_LINE_ITEMS_SQL, receipt_id)
            await conn.execute(DELETE_TAXES_SQL, receipt_id)
            await self._insert_children(conn, receipt_id, receipt)

        return self._receipt_row_from_record(row)

    async def update_receipt(
        self,
        receipt_id: UUID,
        receipt: Receipt,
        user_id: UUID | None = None,
        can_see_all: bool = False,
    ) -> ReceiptRow | None:
        """Update a receipt row and replace its line items and taxes.

        Returns None when no receipt with the given id exists (or, for
        non-see-all callers, when it is not owned by ``user_id``).
        """
        logger.info("Updating receipt %s", receipt_id)

        args: list[Any] = [
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
        ]
        sql = UPDATE_RECEIPT_SQL
        if not can_see_all and user_id is not None:
            args.append(user_id)
            sql = sql.replace("RETURNING *", f"AND user_id = ${len(args)} RETURNING *", 1)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
            if row is None:
                return None

            await conn.execute(DELETE_LINE_ITEMS_SQL, receipt_id)
            await conn.execute(DELETE_TAXES_SQL, receipt_id)
            await self._insert_children(conn, receipt_id, receipt)

        return self._receipt_row_from_record(row)

    async def verify_receipt(
        self, receipt_id: UUID, user_id: UUID | None = None, can_see_all: bool = False
    ) -> ReceiptRow | None:
        """Mark a receipt as verified.

        The image path no longer lives on the receipt row — it is moved to the
        permanent location on the ``images`` row by the caller (see
        ``ImageDB.update_image_path``). Returns None when no receipt with the
        given id exists (or is not owned by a non-see-all ``user_id``).
        """
        logger.info("Verifying receipt %s", receipt_id)

        args: list[Any] = [receipt_id]
        sql = VERIFY_RECEIPT_SQL
        if not can_see_all and user_id is not None:
            args.append(user_id)
            sql = sql.replace("RETURNING *", f"AND user_id = ${len(args)} RETURNING *", 1)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
        if row is None:
            return None
        return self._receipt_row_from_record(row)

    async def delete_receipt(
        self, receipt_id: UUID, user_id: UUID | None = None, can_see_all: bool = False
    ) -> ReceiptRow | None:
        """Delete a receipt row. Line items and taxes cascade via their foreign keys.

        Returns the deleted row, or None when no receipt with the given id exists
        (or is not owned by a non-see-all ``user_id``). A ``benchmark_tasks`` row
        still referencing the receipt raises ``asyncpg.ForeignKeyViolationError``
        (that FK has no ON DELETE rule).
        """
        logger.info("Deleting receipt %s", receipt_id)

        args: list[Any] = [receipt_id]
        sql = DELETE_RECEIPT_SQL
        if not can_see_all and user_id is not None:
            args.append(user_id)
            sql = sql.replace("RETURNING *", f"AND user_id = ${len(args)} RETURNING *", 1)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
        if row is None:
            return None
        return self._receipt_row_from_record(row)

    # ── Query helpers ────────────────────────────────────────────────

    async def get_receipt_by_id(
        self, receipt_id: UUID, user_id: UUID | None = None, can_see_all: bool = False
    ) -> ReceiptRow | None:
        """Fetch a single receipt row by its primary key, scoped to its owner.

        Non-see-all callers only match their own rows (other users' receipts
        resolve to ``None`` -> 404 upstream).
        """
        args: list[Any] = [receipt_id]
        sql = GET_RECEIPT_SQL
        if not can_see_all and user_id is not None:
            args.append(user_id)
            sql += f" AND user_id = ${len(args)}"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
        if row is None:
            return None
        return self._receipt_row_from_record(row)

    async def get_receipt_by_image_id(self, image_id: UUID) -> ReceiptRow | None:
        """Return the existing receipt linked to an image, if any."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(GET_RECEIPT_BY_IMAGE_ID_SQL, image_id)
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
        user_id: UUID | None = None,
        can_see_all: bool = False,
    ) -> list[ReceiptRow]:
        """Return a paginated list of receipts ordered by date descending.

        Optional filters: ``status`` (IN list), an inclusive ``date_from`` /
        ``date_to`` range, and case-insensitive ``search`` over merchant name
        or receipt number. Non-see-all callers are restricted to their own
        rows via ``user_id``.
        """
        where: list[str] = []
        args: list[Any] = []
        if not can_see_all and user_id is not None:
            args.append(user_id)
            where.append(f"user_id = ${len(args)}")
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

    async def search_products(
        self,
        query: str,
        user_id: UUID | None = None,
        can_see_all: bool = False,
    ) -> list[ProductPurchase]:
        """Find verified line items whose descriptions contain ``query``.

        Matching is case-insensitive and is deliberately performed by
        PostgreSQL; product search must not invoke the LLM. Non-see-all callers
        are restricted to their own receipts via ``user_id``.
        """
        args: list[Any] = [f"%{query}%"]
        sql = SEARCH_PRODUCTS_BASE_SQL
        if not can_see_all and user_id is not None:
            args.append(user_id)
            sql += f" AND r.user_id = ${len(args)}"
        sql += (
            " ORDER BY r.date DESC, r.time DESC NULLS LAST, r.created_at DESC NULLS LAST, "
            "r.id DESC, li.id DESC"
        )

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return [self._product_purchase_from_record(row) for row in rows]

    async def get_statistics(
        self,
        user_id: UUID | None = None,
        can_see_all: bool = False,
        weeks: int = 12,
    ) -> ReceiptStatistics:
        """Aggregate verified receipts for the statistics and dashboard views."""
        scope = ""
        scope_args: list[Any] = []
        if not can_see_all and user_id is not None:
            scope_args.append(user_id)
            scope = f" AND user_id = ${len(scope_args)}"

        weekly_args = [*scope_args, max(weeks - 1, 0)]
        weekly_sql = STATS_WEEKLY_SQL.format(
            scope=scope,
            weeks_param=len(weekly_args),
        )

        async with self.pool.acquire() as conn:
            currency_rows = await conn.fetch(STATS_CURRENCY_SQL.format(scope=scope), *scope_args)
            merchant_rows = await conn.fetch(
                STATS_NAMED_SQL.format(
                    field="COALESCE(NULLIF(merchant_name, ''), 'Unknown merchant')",
                    scope=scope,
                ),
                *scope_args,
            )
            category_rows = await conn.fetch(
                STATS_NAMED_SQL.format(field="category", scope=scope), *scope_args
            )
            payment_rows = await conn.fetch(
                STATS_NAMED_SQL.format(field="payment_method", scope=scope), *scope_args
            )
            weekday_rows = await conn.fetch(STATS_WEEKDAY_SQL.format(scope=scope), *scope_args)
            weekly_rows = await conn.fetch(weekly_sql, *weekly_args)

        def decimal(row: Mapping[str, Any], key: str) -> Decimal:
            value = row[key]
            return value if isinstance(value, Decimal) else Decimal(str(value))

        currencies = [
            CurrencyStatistics(
                currency=row["currency"],
                receipt_count=int(row["receipt_count"]),
                total=decimal(row, "total"),
                average=decimal(row, "average"),
                median=decimal(row, "median"),
                minimum=decimal(row, "minimum"),
                maximum=decimal(row, "maximum"),
                subtotal=decimal(row, "subtotal"),
                discounts=decimal(row, "discounts"),
                taxes=decimal(row, "taxes"),
                tips=decimal(row, "tips"),
            )
            for row in currency_rows
        ]

        def named(rows: list[Mapping[str, Any]]) -> list[NamedStatistics]:
            return [
                NamedStatistics(
                    name=row["name"],
                    currency=row["currency"],
                    receipt_count=int(row["receipt_count"]),
                    total=decimal(row, "total"),
                    average=decimal(row, "average"),
                )
                for row in rows
            ]

        return ReceiptStatistics(
            verified_receipt_count=sum(item.receipt_count for item in currencies),
            currencies=currencies,
            merchants=named(merchant_rows),
            categories=named(category_rows),
            payment_methods=named(payment_rows),
            weekdays=[
                WeekdayStatistics(
                    weekday=int(row["weekday"]),
                    currency=row["currency"],
                    receipt_count=int(row["receipt_count"]),
                    total=decimal(row, "total"),
                    average=decimal(row, "average"),
                )
                for row in weekday_rows
            ],
            weekly_spending=[
                WeeklyStatistics(
                    week_start=row["week_start"],
                    currency=row["currency"],
                    receipt_count=int(row["receipt_count"]),
                    total=decimal(row, "total"),
                    average=decimal(row, "average"),
                )
                for row in weekly_rows
            ],
        )

    async def get_receipt_with_details(
        self, receipt_id: UUID, user_id: UUID | None = None, can_see_all: bool = False
    ) -> ReceiptWithDetails | None:
        """Fetch a receipt together with its line items, taxes and image path.

        The image path is resolved via a LEFT JOIN on the images table so the
        response exposes it for frontends even though the receipts row only
        stores the FK. Non-see-all callers only match their own rows.
        """
        args: list[Any] = [receipt_id]
        sql = GET_RECEIPT_WITH_IMAGE_SQL
        if not can_see_all and user_id is not None:
            args.append(user_id)
            sql += f" AND r.user_id = ${len(args)}"
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
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
