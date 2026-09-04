from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class CurrencyStatistics(BaseModel):
    currency: str
    receipt_count: int
    total: Decimal
    average: Decimal
    median: Decimal
    minimum: Decimal
    maximum: Decimal
    subtotal: Decimal
    discounts: Decimal
    taxes: Decimal
    tips: Decimal


class NamedStatistics(BaseModel):
    name: str
    currency: str
    receipt_count: int
    total: Decimal
    average: Decimal


class WeekdayStatistics(BaseModel):
    weekday: int
    currency: str
    receipt_count: int
    total: Decimal
    average: Decimal


class WeeklyStatistics(BaseModel):
    week_start: date
    currency: str
    receipt_count: int
    total: Decimal
    average: Decimal


class ReceiptStatistics(BaseModel):
    verified_receipt_count: int
    currencies: list[CurrencyStatistics]
    merchants: list[NamedStatistics]
    categories: list[NamedStatistics]
    payment_methods: list[NamedStatistics]
    weekdays: list[WeekdayStatistics]
    weekly_spending: list[WeeklyStatistics]
