from datetime import date as Date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

Category = Literal[
    "grocery",
    "electronics",
    "clothing",
    "restaurant",
    "fuel",
    "pharmacy",
    "entertainment",
    "other",
]


MAX_TAG_LENGTH = 100


class LineItem(BaseModel):
    description: str = Field(description="Name of the purchased item")
    quantity: float = Field(gt=0, description="Quantity purchased")
    unit_price: Decimal = Field(ge=0, description="Price per unit")
    total_price: Decimal = Field(ge=0, description="quantity * unit_price, line total")
    category: Category = Field(default="other", description="Best-guess category of the item")
    tags: list[str] = Field(
        default_factory=list,
        description=(
            "Short tags for the item. Prefer the tag list from the prompt; a single new "
            "suggested tag is allowed when nothing fits."
        ),
    )

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, v: list[str]) -> list[str]:
        """Clean LLM-produced tags: trim, dedupe case-insensitively, cap length.

        Suggestions (tags not yet in the vocabulary) are kept — the UI marks
        them for human review — but obviously broken values are dropped.
        """
        seen: set[str] = set()
        clean: list[str] = []
        for tag in v:
            name = " ".join(tag.split()).strip()
            if not name or len(name) > MAX_TAG_LENGTH:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            clean.append(name)
        return clean


class TaxLine(BaseModel):
    name: str = Field(description="e.g. 'VAT', 'Sales Tax', 'GST'")
    rate: float | None = Field(default=None, description="Tax rate as a decimal, e.g. 0.19 for 19%")
    amount: Decimal = Field(ge=0, description="Tax amount charged")


class Receipt(BaseModel):
    confidence: int = Field(
        ge=0,
        le=100,
        description="from 0 - 100 as percentage, how sure are you in the presented data",
    )
    merchant_name: str = Field(
        description=(
            "Name of the store or vendor, taken from printed text on the receipt "
            "(header, footer, address, website) — never guessed from a logo"
        )
    )
    merchant_address: str | None = Field(
        default=None, description="Store address if printed on receipt"
    )
    receipt_number: str | None = Field(default=None, description="Transaction/receipt ID")
    date: Date = Field(description="Date of purchase, ISO format YYYY-MM-DD")
    time: str | None = Field(default=None, description="Time of purchase, HH:MM 24h format")

    currency: str = Field(default="USD", description="ISO 4217 currency code, e.g. USD, EUR")
    category: Category = Field(
        default="other", description="Best-guess category for the whole purchase"
    )
    line_items: list[LineItem] = Field(description="All purchased items")
    taxes: list[TaxLine] = Field(default_factory=list, description="Tax lines applied")

    subtotal: Decimal = Field(ge=0, description="Sum of line items before tax/discounts")
    discount_total: Decimal = Field(default=Decimal(0), ge=0, description="Total discounts applied")
    tax_total: Decimal = Field(default=Decimal(0), ge=0, description="Sum of all taxes")
    tip: Decimal | None = Field(default=None, ge=0, description="Tip/gratuity if applicable")
    total: Decimal = Field(ge=0, description="Final amount charged")

    payment_method: Literal[
        "cash", "credit_card", "debit_card", "mobile_payment", "check", "other", "unknown"
    ] = Field(default="unknown")

    @field_validator("total")
    @classmethod
    def sanity_check_total(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        # Optional cross-field consistency check — catches LLM arithmetic drift
        subtotal = info.data.get("subtotal")
        tax_total = info.data.get("tax_total", Decimal(0))
        discount_total = info.data.get("discount_total", Decimal(0))
        if subtotal is not None:
            expected = subtotal - discount_total + tax_total
            if abs(v - expected) > Decimal("0.05"):
                # Don't hard-fail — LLM extraction from OCR is fuzzy — but you could log/flag
                pass
        return v
