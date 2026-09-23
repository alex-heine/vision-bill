import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from vision_bill.model.receipt import LineItem, Receipt
from vision_bill.service.tagging_service import TaggingService


@pytest.mark.asyncio
async def test_tag_line_item_returns_gpc_category():
    """TaggingService should embed the description and return the closest GPC category."""
    mock_embedding_service = Mock()
    mock_embedding_service.embed_text = AsyncMock(return_value=[0.1] * 768)

    mock_db = Mock()
    mock_db.find_gpc_suggestions = AsyncMock(
        return_value=[
            {
                "gpc_code": 30001234,
                "title": "MILK",
                "definition": "Dairy milk products",
                "similarity": 0.85,
            }
        ]
    )

    service = TaggingService(mock_embedding_service, mock_db)
    item = LineItem(
        description="organic whole milk 1L",
        quantity=1,
        unit_price=Decimal("1.50"),
        total_price=Decimal("1.50"),
    )
    tag = await service.tag_line_item(item, language="en")
    assert tag == "MILK"
    mock_embedding_service.embed_text.assert_called_once_with("organic whole milk 1L")
    mock_db.find_gpc_suggestions.assert_called_once()


@pytest.mark.asyncio
async def test_tag_line_item_returns_other_below_threshold():
    """When no GPC match is found (empty suggestions), return 'OTHER'."""
    mock_embedding_service = Mock()
    mock_embedding_service.embed_text = AsyncMock(return_value=[0.1] * 768)

    mock_db = Mock()
    mock_db.find_gpc_suggestions = AsyncMock(return_value=[])

    service = TaggingService(mock_embedding_service, mock_db)
    item = LineItem(
        description="mystery item",
        quantity=1,
        unit_price=Decimal("1.00"),
        total_price=Decimal("1.00"),
    )
    tag = await service.tag_line_item(item, language="en")
    assert tag == "OTHER"


@pytest.mark.asyncio
async def test_tag_line_item_returns_other_when_no_match():
    """When no GPC match is found, return 'OTHER'."""
    mock_embedding_service = Mock()
    mock_embedding_service.embed_text = AsyncMock(return_value=[0.1] * 768)

    mock_db = Mock()
    mock_db.find_gpc_suggestions = AsyncMock(return_value=[])

    service = TaggingService(mock_embedding_service, mock_db)
    item = LineItem(
        description="mystery item",
        quantity=1,
        unit_price=Decimal("1.00"),
        total_price=Decimal("1.00"),
    )
    tag = await service.tag_line_item(item, language="en")
    assert tag == "OTHER"


@pytest.mark.asyncio
async def test_tag_receipt_tags_all_items():
    """TaggingService should tag all line items in a receipt."""
    mock_embedding_service = Mock()
    mock_embedding_service.embed_text = AsyncMock(return_value=[0.1] * 768)

    mock_db = Mock()
    mock_db.find_gpc_suggestions = AsyncMock(
        return_value=[
            {
                "gpc_code": 30001234,
                "title": "MILK",
                "definition": "Dairy milk products",
                "similarity": 0.85,
            }
        ]
    )

    service = TaggingService(mock_embedding_service, mock_db)

    receipt = Receipt(
        confidence=95,
        merchant_name="Test Store",
        date="2026-01-01",
        currency="EUR",
        line_items=[
            LineItem(
                description="milk",
                quantity=1,
                unit_price=Decimal("1.50"),
                total_price=Decimal("1.50"),
            ),
            LineItem(
                description="bread",
                quantity=1,
                unit_price=Decimal("2.00"),
                total_price=Decimal("2.00"),
            ),
        ],
        subtotal=Decimal("3.50"),
        total=Decimal("3.50"),
        language="en",
    )

    tagged = await service.tag_receipt(receipt)
    assert tagged.line_items[0].tags == ["MILK"]
    assert tagged.line_items[1].tags == ["MILK"]
    assert mock_embedding_service.embed_text.call_count == 2
