from datetime import date as Date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ReceiptRow(BaseModel):
    """Represents a single row in the `receipts` table."""

    id: UUID
    confidence: int
    merchant_name: str
    merchant_address: str | None = None
    receipt_number: str | None = None
    date: Date
    time: str | None = None
    currency: str = "USD"
    category: str = "other"
    subtotal: Decimal
    discount_total: Decimal = Decimal(0)
    tax_total: Decimal = Decimal(0)
    tip: Decimal | None = None
    total: Decimal
    payment_method: str = "unknown"
    created_at: Date | None = None
    status: str = "unverified"
    image_id: UUID | None = None
    verified: bool = False
    user_id: UUID | None = None


class LineItemRow(BaseModel):
    """Represents a single row in the `line_items` table."""

    id: UUID
    receipt_id: UUID
    description: str
    quantity: float
    unit_price: Decimal
    total_price: Decimal
    category: str = "other"
    tags: list[str] = Field(default_factory=list)


class TaxLineRow(BaseModel):
    """Represents a single row in the `taxes` table."""

    id: UUID
    receipt_id: UUID
    name: str
    rate: float | None = None
    amount: Decimal


class ReceiptWithDetails(BaseModel):
    """A receipt row enriched with its line items and taxes.

    ``image_path`` is resolved from the joined ``images`` row so frontends
    can keep displaying the image location without a second lookup.
    """

    receipt: ReceiptRow
    line_items: list[LineItemRow]
    taxes: list[TaxLineRow]
    image_path: str | None = None
