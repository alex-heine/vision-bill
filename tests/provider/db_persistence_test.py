import pytest
from unittest.mock import MagicMock
from src.vision_bill.provider.db.postgres import PostgresProvider
from src.vision_bill.model.receipt import Receipt
from src.vision_bill.config import PGSettings
from decimal import Decimal

@pytest.mark.asyncio
async def test_save_receipt():
    settings = MagicMock(spec=PGSettings)
    provider = PostgresProvider(settings)
    
    receipt = Receipt(
        merchant_name="Test Store",
        date="2026-08-05",
        line_items=[],
        taxes=[],
        subtotal=Decimal("10.00"),
        discount_total=Decimal("0.00"),
        tax_total=Decimal("1.00"),
        total=Decimal("11.00")
    )
    await provider.save_receipt(receipt)
    saved = await provider.get_receipt_by_id("any-id")
    assert saved is not None
