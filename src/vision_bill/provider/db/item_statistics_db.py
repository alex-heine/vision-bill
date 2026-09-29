"""Verified line-item spending, with one snapshot for totals and reconciliation."""

from collections.abc import Mapping
from datetime import date
from typing import Any
from uuid import UUID

import asyncpg

# EXISTS avoids duplicating amounts when a receipt belongs to multiple collections.
# A single statement keeps receipt and item totals on the same database snapshot.
ITEM_STATISTICS_SQL = """
WITH scoped_receipts AS (
    SELECT r.id, r.date, r.currency, r.total
    FROM receipts r
    WHERE r.status = 'verified' AND r.verified = TRUE
      AND r.date >= $1 AND r.date <= $2
      AND ($3::boolean OR r.user_id = $4::uuid)
      AND ($5::uuid IS NULL OR EXISTS (
          SELECT 1 FROM receipt_collections rc
          WHERE rc.receipt_id = r.id AND rc.collection_id = $5
      ))
)
SELECT 'item' AS kind, date_trunc('month', r.date)::date AS month,
       li.spending_category AS category, r.currency, SUM(li.total_price) AS total
FROM scoped_receipts r JOIN line_items li ON li.receipt_id = r.id
GROUP BY month, li.spending_category, r.currency
UNION ALL
SELECT 'receipt' AS kind, NULL::date AS month, NULL::text AS category,
       currency, SUM(total) AS total
FROM scoped_receipts GROUP BY currency
"""


class ItemStatisticsDB:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_totals(
        self,
        *,
        date_from: date,
        date_to: date,
        user_id: UUID,
        can_see_all: bool = False,
        collection_id: UUID | None = None,
    ) -> list[Mapping[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                ITEM_STATISTICS_SQL, date_from, date_to, can_see_all, user_id, collection_id
            )
        return list(rows)
