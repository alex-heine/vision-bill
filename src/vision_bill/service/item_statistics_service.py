"""Spending categories are disjoint; deposits and unmatched amounts stay explicit."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from ..model.statistics import (
    ItemCategoryStatistics,
    ItemReconciliation,
    ItemStatistics,
    MonthlyItemStatistics,
)
from ..provider.db.item_statistics_db import ItemStatisticsDB


def month_start(value: date, offset: int = 0) -> date:
    year, month = divmod(value.year * 12 + value.month - 1 + offset, 12)
    return date(year, month + 1, 1)


def percentage(amount: Decimal, total: Decimal) -> Decimal | None:
    # Net refunds can produce negative shares. A non-positive denominator has
    # no useful spending-share interpretation, so return null rather than 0%.
    return (amount / total * 100).quantize(Decimal("0.01")) if total > 0 else None


def build_item_statistics(
    rows: Sequence[Mapping[str, Any]],
    *,
    months: int,
    today: date,
) -> ItemStatistics:
    start = month_start(today, 1 - months)
    totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    monthly: dict[tuple[date, str, str], Decimal] = defaultdict(Decimal)
    currency_totals: dict[str, Decimal] = defaultdict(Decimal)
    month_totals: dict[tuple[date, str], Decimal] = defaultdict(Decimal)
    receipt_totals: dict[str, Decimal] = defaultdict(Decimal)
    deposits: dict[str, Decimal] = defaultdict(Decimal)
    item_totals: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        currency = str(row["currency"])
        total = Decimal(str(row["total"]))
        if row["kind"] == "receipt":
            receipt_totals[currency] += total
            continue
        category = str(row["category"] or "unknown")
        item_totals[currency] += total
        if category == "deposit":
            deposits[currency] += total
            continue
        month = row["month"]
        totals[(category, currency)] += total
        monthly[(month, category, currency)] += total
        currency_totals[currency] += total
        month_totals[(month, currency)] += total

    categories = [
        ItemCategoryStatistics(
            category=category,
            currency=currency,
            total=total,
            share=percentage(total, currency_totals[currency]),
        )
        for (category, currency), total in sorted(
            totals.items(), key=lambda entry: (entry[0][1], -entry[1], entry[0][0])
        )
    ]
    history = []
    for offset in range(months):
        month = month_start(start, offset)
        for category, currency in sorted(totals):
            total = monthly[(month, category, currency)]
            history.append(
                MonthlyItemStatistics(
                    month=month,
                    category=category,
                    currency=currency,
                    total=total,
                    share=percentage(total, month_totals[(month, currency)]),
                )
            )
    reconciliation = [
        ItemReconciliation(
            currency=currency,
            receipt_total=receipt_totals[currency],
            item_total=item_totals[currency],
            deposit_total=deposits[currency],
            unallocated_total=receipt_totals[currency] - item_totals[currency],
        )
        for currency in sorted(receipt_totals.keys() | item_totals.keys())
    ]
    return ItemStatistics(
        months=months,
        date_from=start,
        date_to=today,
        categories=categories,
        monthly=history,
        reconciliation=reconciliation,
    )


class ItemStatisticsService:
    def __init__(self, pool: asyncpg.Pool):
        self._db = ItemStatisticsDB(pool)

    async def get_statistics(
        self,
        *,
        user_id: UUID,
        can_see_all: bool = False,
        months: int = 12,
        collection_id: UUID | None = None,
    ) -> ItemStatistics:
        today = datetime.now(UTC).date()
        rows = await self._db.get_totals(
            date_from=month_start(today, 1 - months),
            date_to=today,
            user_id=user_id,
            can_see_all=can_see_all,
            collection_id=collection_id,
        )
        return build_item_statistics(rows, months=months, today=today)
