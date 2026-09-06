"""Collections: per-user groups a whole receipt may belong to."""

import re
from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from .db.receipt import ReceiptRow

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def normalize_collection_name(raw: str) -> str:
    """Collapse and trim whitespace; return '' for blank input."""
    return " ".join(raw.split()).strip()


def is_valid_hex_color(value: str) -> bool:
    """True for a CSS 3- or 6-digit hex colour."""
    return _HEX_RE.match(value) is not None


def _validate_name(name: str) -> str:
    """Normalize a collection name and reject blank input."""
    normalized = normalize_collection_name(name)
    if not normalized:
        raise ValueError("name must not be blank")
    return normalized


class CollectionBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, v: str) -> str:
        return _validate_name(v)


class CollectionCreate(CollectionBase):
    active: bool = False


class CollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_name(v)


class Collection(CollectionBase):
    id: UUID
    active: bool = False
    created_at: date | None = None


class CurrencyTotal(BaseModel):
    currency: str
    total: Decimal


class CollectionSummary(Collection):
    receipt_count: int = 0
    totals: list[CurrencyTotal] = Field(default_factory=list)


class CollectionDetail(Collection):
    totals: list[CurrencyTotal] = Field(default_factory=list)
    receipts: list[ReceiptRow] = Field(default_factory=list)
