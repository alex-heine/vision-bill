"""Accounting and endpoint regression tests for line-item category reports."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vision_bill.api.helper.helper import get_receipt_service
from vision_bill.api.statistics import router
from vision_bill.security.dependencies import get_current_user
from vision_bill.security.models import User
from vision_bill.service.item_statistics_service import (
    ItemStatisticsService,
    build_item_statistics,
    month_start,
)

TODAY = date(2026, 9, 27)


def item(category, amount, currency="EUR", month=date(2026, 9, 1)):
    return dict(kind="item", month=month, category=category, currency=currency, total=amount)


def receipt(amount, currency="EUR"):
    return dict(kind="receipt", month=None, category=None, currency=currency, total=amount)


def test_unknown_counts_deposits_do_not_and_adjustments_reconcile():
    report = build_item_statistics(
        [
            item("milk", "6"),
            item("unknown", "4"),
            item("deposit", "0.50"),
            item("deposit", "-0.25"),
            receipt("9.25"),
        ],
        months=3,
        today=TODAY,
    )
    categories = {r.category: r for r in report.categories}
    assert categories["milk"].share == Decimal("60.00")
    assert categories["unknown"].share == Decimal("40.00")
    assert "deposit" not in categories
    reconciliation = report.reconciliation[0]
    assert reconciliation.item_total == Decimal("10.25")
    assert reconciliation.deposit_total == Decimal("0.25")
    assert reconciliation.unallocated_total == Decimal("-1.00")
    assert (
        reconciliation.item_total + reconciliation.unallocated_total == reconciliation.receipt_total
    )
    assert report.date_from == date(2026, 7, 1)
    assert report.date_to == TODAY
    assert len(report.monthly) == 6
    july = [r for r in report.monthly if r.month == date(2026, 7, 1)]
    assert all(r.total == 0 and r.share is None for r in july)


def test_currencies_and_monthly_denominators_are_separate():
    report = build_item_statistics(
        [
            item("milk", "2", month=date(2026, 8, 1)),
            item("milk", "3"),
            item("bread_bakery", "9"),
            item("milk", "100", currency="USD"),
            receipt("14"),
            receipt("100", "USD"),
        ],
        months=2,
        today=TODAY,
    )
    categories = {(r.category, r.currency): r for r in report.categories}
    assert categories[("milk", "EUR")].share == Decimal("35.71")
    assert categories[("milk", "USD")].share == Decimal("100")
    september = next(
        r
        for r in report.monthly
        if r.month.month == 9 and r.category == "milk" and r.currency == "EUR"
    )
    assert september.share == Decimal("25")
    august = next(
        r
        for r in report.monthly
        if r.month.month == 8 and r.category == "milk" and r.currency == "EUR"
    )
    assert august.share == Decimal("100")


@pytest.mark.parametrize("amount", ["0", "-2"])
def test_nonpositive_net_spending_has_no_percentage(amount):
    report = build_item_statistics([item("milk", amount), receipt(amount)], months=1, today=TODAY)
    assert report.categories[0].share is None
    assert report.monthly[0].share is None


def test_empty_and_receipt_without_items():
    empty = build_item_statistics([], months=12, today=TODAY)
    assert empty.categories == empty.monthly == empty.reconciliation == []
    report = build_item_statistics([receipt("12")], months=1, today=TODAY)
    assert report.reconciliation[0].unallocated_total == Decimal("12")
    assert report.categories == []


def test_month_range_crosses_year_and_leap_day():
    assert month_start(date(2024, 2, 29), -2) == date(2023, 12, 1)
    assert month_start(date(2026, 1, 31), -11) == date(2025, 2, 1)


def test_endpoint_scopes_and_validates(monkeypatch):
    owner = uuid4()
    collection = uuid4()
    result = build_item_statistics([], months=6, today=TODAY)
    method = AsyncMock(return_value=result)
    monkeypatch.setattr(ItemStatisticsService, "get_statistics", method)
    app = FastAPI()
    app.include_router(router, prefix="/statistics")
    service = SimpleNamespace(db_ready=True, pool=object())
    app.dependency_overrides[get_receipt_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: User(
        id=owner,
        username="alice",
        is_admin=False,
        can_see_all=False,
    )
    with TestClient(app) as client:
        response = client.get(f"/statistics/items?months=6&collection_id={collection}")
        assert response.status_code == 200
        method.assert_awaited_once_with(
            user_id=owner,
            can_see_all=False,
            months=6,
            collection_id=collection,
        )
        for months in (0, 37):
            assert client.get(f"/statistics/items?months={months}").status_code == 422
        assert client.get("/statistics/items?collection_id=invalid").status_code == 422
        service.db_ready = False
        assert client.get("/statistics/items").status_code == 503
