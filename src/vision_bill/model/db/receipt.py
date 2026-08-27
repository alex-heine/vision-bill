from datetime import date as Date
from decimal import Decimal

from pydantic import BaseModel


class ReceiptRow(BaseModel):
    """Represents a single row in the `receipts` table."""

    id: int
    merchant_name: str
    merchant_address: str | None = None
    receipt_number: str | None = None
    date: Date
    time: str | None = None
    currency: str = "USD"
    subtotal: Decimal
    discount_total: Decimal = Decimal(0)
    tax_total: Decimal = Decimal(0)
    tip: Decimal | None = None
    total: Decimal
    payment_method: str = "unknown"
    created_at: Date | None = None
    status: str = "unverified"
    image_path: str | None = None


class LineItemRow(BaseModel):
    """Represents a single row in the `line_items` table."""

    id: int
    receipt_id: int
    description: str
    quantity: float
    unit_price: Decimal
    total_price: Decimal
    category: str = "other"


class TaxLineRow(BaseModel):
    """Represents a single row in the `taxes` table."""

    id: int
    receipt_id: int
    name: str
    rate: float | None = None
    amount: Decimal


class ReceiptWithDetails(BaseModel):
    """A receipt row enriched with its line items and taxes."""

    receipt: ReceiptRow
    line_items: list[LineItemRow]
    taxes: list[TaxLineRow]
