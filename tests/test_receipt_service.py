import io
from collections.abc import Generator
from datetime import date as Date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

from vision_bill.config import Settings
from vision_bill.model.db.receipt import ReceiptRow
from vision_bill.model.receipt import LineItem, Receipt, TaxLine
from vision_bill.provider.llm.base import LLMProvider, ModelInfo
from vision_bill.service.receipt_service import ReceiptService

ServiceContext = tuple[ReceiptService, MagicMock, MagicMock, MagicMock]
DelegationContext = tuple[ReceiptService, MagicMock]


@pytest.fixture
def mock_provider() -> MagicMock:
    """Fixture for a mocked LLM provider."""
    provider = MagicMock(spec=LLMProvider)
    provider.analyse_receipt_from_model = AsyncMock()
    provider.get_available_models = AsyncMock(return_value=[])
    return provider


@pytest.fixture
def receipt_service_context(
    settings: Settings, mock_provider: MagicMock
) -> Generator[ServiceContext, None, None]:
    """
    Context fixture that provides a ReceiptService with mocked dependencies.
    Returns a tuple: (service, mock_provider, mock_image_service, mock_path)
    """
    with patch("vision_bill.service.receipt_service.ImageService") as mock_image_service_class:
        mock_image_service = mock_image_service_class.return_value

        # Setup mock path
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_image_service.store_tmp_image.return_value = mock_path

        # Inject mock_provider directly into ReceiptService
        service = ReceiptService(settings.images, settings.pg, mock_provider)
        yield service, mock_provider, mock_image_service, mock_path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "merchant_name, subtotal, total",
    [
        ("Test Vendor", "10.50", "10.50"),
        ("Grocery Store", "100.00", "105.50"),
    ],
)
async def test_analyse_receipt_from_model_success(
    receipt_service_context: ServiceContext,
    merchant_name: str,
    subtotal: str,
    total: str,
) -> None:
    # Arrange
    service, mock_provider, _, mock_path = receipt_service_context
    mock_receipt = Receipt(
        confidence=95,
        merchant_name=merchant_name,
        date=Date(2023, 1, 1),
        currency="USD",
        line_items=[],
        subtotal=Decimal(subtotal),
        total=Decimal(total),
    )
    mock_provider.analyse_receipt_from_model.return_value = mock_receipt

    image_bytes = b"fake-image-content"
    model_id = "test-model"

    # Act
    result = await service.analyse_receipt_from_model(model_id, image_bytes)

    # Assert
    assert result == mock_receipt
    mock_provider.analyse_receipt_from_model.assert_called_once_with(model_id, mock_path)
    mock_path.unlink.assert_called_once()


@pytest.mark.asyncio
async def test_analyse_receipt_from_model_failure(
    receipt_service_context: ServiceContext,
) -> None:
    # Arrange
    service, mock_provider, _, mock_path = receipt_service_context
    error_msg = "LLM Error"
    mock_provider.analyse_receipt_from_model.side_effect = Exception(error_msg)

    image_bytes = b"fake-image-content"
    model_id = "test-model"

    # Act & Assert
    with pytest.raises(Exception) as exc_info:
        await service.analyse_receipt_from_model(model_id, image_bytes)

    assert error_msg in str(exc_info.value)
    mock_provider.analyse_receipt_from_model.assert_called_once_with(model_id, mock_path)
    mock_path.unlink.assert_called_once()


@pytest.mark.asyncio
async def test_extract_receipt_all_models_success(
    receipt_service_context: ServiceContext,
) -> None:
    # Arrange
    service, mock_provider, _, _ = receipt_service_context
    model1 = ModelInfo(id="model1")
    model2 = ModelInfo(id="model2")
    mock_provider.get_available_models.return_value = [model1, model2]

    receipt1 = Receipt(
        confidence=95,
        merchant_name="Merchant 1",
        date=Date(2023, 1, 1),
        currency="USD",
        line_items=[],
        subtotal=Decimal("10.00"),
        total=Decimal("10.00"),
    )
    receipt2 = Receipt(
        confidence=95,
        merchant_name="Merchant 2",
        date=Date(2023, 1, 1),
        currency="USD",
        line_items=[],
        subtotal=Decimal("20.00"),
        total=Decimal("20.00"),
    )

    # Use side_effect to return different values for different calls
    async def side_effect(model_id: str, path: Path) -> Receipt:
        if model_id == "model1":
            return receipt1
        elif model_id == "model2":
            return receipt2
        raise ValueError("Unexpected model id")

    mock_provider.analyse_receipt_from_model.side_effect = side_effect

    # Mock UploadFile
    image_content = b"fake-image-content"
    upload_file = UploadFile(file=io.BytesIO(image_content))

    # Act
    results = await service.extract_receipt_all_models(upload_file)

    # Assert
    assert len(results) == 2
    # Test Case 1: Success
    res1 = next(r for r in results if r.model_id == "model1")
    res2 = next(r for r in results if r.model_id == "model2")

    assert res1.receipt == receipt1
    assert res1.error is None
    assert res2.receipt == receipt2
    assert res2.error is None


@pytest.mark.asyncio
async def test_extract_receipt_all_models_value_error(
    receipt_service_context: ServiceContext,
) -> None:
    # Arrange
    service, mock_provider, _, _ = receipt_service_context
    model1 = ModelInfo(id="model1")
    model2 = ModelInfo(id="model2")
    mock_provider.get_available_models.return_value = [model1, model2]

    receipt2 = Receipt(
        confidence=95,
        merchant_name="Merchant 2",
        date=Date(2023, 1, 1),
        currency="USD",
        line_items=[],
        subtotal=Decimal("20.00"),
        total=Decimal("20.00"),
    )

    async def side_effect(model_id: str, path: Path) -> Receipt:
        if model_id == "model1":
            raise ValueError("Invalid receipt format")
        elif model_id == "model2":
            return receipt2
        raise ValueError("Unexpected model id")

    mock_provider.analyse_receipt_from_model.side_effect = side_effect

    image_content = b"fake-image-content"
    upload_file = UploadFile(file=io.BytesIO(image_content))

    # Act
    results = await service.extract_receipt_all_models(upload_file)

    # Assert
    assert len(results) == 2
    # Test Case 2: ValueError Handling
    res1 = next(r for r in results if r.model_id == "model1")
    res2 = next(r for r in results if r.model_id == "model2")

    assert res1.receipt is None
    assert res1.error is not None
    assert "Invalid receipt format" in res1.error
    assert res2.receipt == receipt2
    assert res2.error is None


@pytest.mark.asyncio
async def test_extract_receipt_all_models_exception(
    receipt_service_context: ServiceContext,
) -> None:
    # Arrange
    service, mock_provider, _, _ = receipt_service_context
    model1 = ModelInfo(id="model1")
    model2 = ModelInfo(id="model2")
    mock_provider.get_available_models.return_value = [model1, model2]

    receipt2 = Receipt(
        confidence=95,
        merchant_name="Merchant 2",
        date=Date(2023, 1, 1),
        currency="USD",
        line_items=[],
        subtotal=Decimal("20.00"),
        total=Decimal("20.00"),
    )

    async def side_effect(model_id: str, path: Path) -> Receipt:
        if model_id == "model1":
            raise RuntimeError("Generic failure")
        elif model_id == "model2":
            return receipt2
        raise ValueError("Unexpected model id")

    mock_provider.analyse_receipt_from_model.side_effect = side_effect

    image_content = b"fake-image-content"
    upload_file = UploadFile(file=io.BytesIO(image_content))

    # Act
    results = await service.extract_receipt_all_models(upload_file)

    # Assert
    assert len(results) == 2
    # Test Case 3: Exception Handling
    res1 = next(r for r in results if r.model_id == "model1")
    res2 = next(r for r in results if r.model_id == "model2")

    assert res1.receipt is None
    assert res1.error is not None
    assert "Generic failure" in res1.error
    assert res2.receipt == receipt2
    assert res2.error is None


# ── Database delegation tests ────────────────────────────────────────


def _make_receipt() -> Receipt:
    return Receipt(
        confidence=95,
        merchant_name="Test Store",
        merchant_address="123 Main St",
        receipt_number="R-001",
        date=Date(2024, 1, 15),
        time="14:30",
        currency="USD",
        line_items=[
            LineItem(
                description="Item A",
                quantity=2,
                unit_price=Decimal("10.00"),
                total_price=Decimal("20.00"),
            )
        ],
        taxes=[TaxLine(name="VAT", rate=0.19, amount=Decimal("4.50"))],
        subtotal=Decimal("50.00"),
        discount_total=Decimal(0),
        tax_total=Decimal("4.50"),
        total=Decimal("54.50"),
        payment_method="credit_card",
    )


def _make_row(**overrides: object) -> ReceiptRow:
    base: dict[str, Any] = {
        "id": 1,
        "confidence": 95,
        "merchant_name": "Test Store",
        "merchant_address": "123 Main St",
        "receipt_number": "R-001",
        "date": Date(2024, 1, 15),
        "time": "14:30:00",
        "currency": "USD",
        "subtotal": Decimal("50.00"),
        "discount_total": Decimal(0),
        "tax_total": Decimal("4.50"),
        "tip": None,
        "total": Decimal("54.50"),
        "payment_method": "credit_card",
        "created_at": Date(2024, 1, 15),
        "status": "unverified",
        "image_path": None,
        "verified": False,
    }
    base.update(overrides)
    return ReceiptRow(**base)


@pytest.fixture
def delegation_context(settings: Settings) -> Generator[DelegationContext, None, None]:
    """ReceiptService with the ReceiptDB provider patched out."""
    with patch("vision_bill.service.receipt_service.ReceiptDB") as mock_db_class:
        mock_db = mock_db_class.return_value
        mock_db.init_db = AsyncMock()
        mock_db.destroy_db = AsyncMock()
        mock_db.persist_receipt = AsyncMock()
        mock_db.get_receipt_by_id = AsyncMock()
        mock_db.list_receipts = AsyncMock()
        mock_db.get_receipt_with_details = AsyncMock()
        mock_db.update_receipt = AsyncMock()
        mock_db.verify_receipt = AsyncMock()
        mock_db.pool = MagicMock()
        mock_db.is_ready = True

        service = ReceiptService(settings.images, settings.pg, MagicMock(spec=LLMProvider))
        yield service, mock_db


@pytest.mark.asyncio
async def test_init_db_delegates(delegation_context: DelegationContext) -> None:
    """init_db should delegate to the ReceiptDB provider."""
    service, mock_db = delegation_context

    await service.init_db()

    mock_db.init_db.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_destroy_db_delegates(delegation_context: DelegationContext) -> None:
    """destroy_db should delegate to the ReceiptDB provider."""
    service, mock_db = delegation_context

    await service.destroy_db()

    mock_db.destroy_db.assert_awaited_once_with()


def test_pool_property_delegates(delegation_context: DelegationContext) -> None:
    """pool should be the ReceiptDB pool."""
    service, mock_db = delegation_context

    assert service.pool is mock_db.pool


def test_db_ready_reflects_db_is_ready(delegation_context: DelegationContext) -> None:
    """db_ready should mirror ReceiptDB.is_ready."""
    service, mock_db = delegation_context

    mock_db.is_ready = True
    assert service.db_ready is True

    mock_db.is_ready = False
    assert service.db_ready is False


@pytest.mark.asyncio
async def test_persist_receipt_delegates(delegation_context: DelegationContext) -> None:
    """persist_receipt should delegate with image_path and status."""
    service, mock_db = delegation_context
    receipt = _make_receipt()
    row = _make_row()
    mock_db.persist_receipt.return_value = row

    result = await service.persist_receipt(receipt, image_path="x", status="unverified")

    mock_db.persist_receipt.assert_awaited_once_with(receipt, image_path="x", status="unverified")
    assert result is row


@pytest.mark.asyncio
async def test_get_receipt_by_id_delegates(delegation_context: DelegationContext) -> None:
    """get_receipt_by_id should delegate with the receipt id."""
    service, mock_db = delegation_context
    row = _make_row(id=42)
    mock_db.get_receipt_by_id.return_value = row

    result = await service.get_receipt_by_id(42)

    mock_db.get_receipt_by_id.assert_awaited_once_with(42)
    assert result is row


@pytest.mark.asyncio
async def test_list_receipts_delegates(delegation_context: DelegationContext) -> None:
    """list_receipts should delegate with limit and offset."""
    service, mock_db = delegation_context
    rows: list[ReceiptRow] = [_make_row(id=1), _make_row(id=2)]
    mock_db.list_receipts.return_value = rows

    result = await service.list_receipts(limit=10, offset=5)

    mock_db.list_receipts.assert_awaited_once_with(limit=10, offset=5)
    assert result is rows


@pytest.mark.asyncio
async def test_get_receipt_with_details_delegates(
    delegation_context: DelegationContext,
) -> None:
    """get_receipt_with_details should delegate with the receipt id."""
    service, mock_db = delegation_context
    mock_db.get_receipt_with_details.return_value = None

    result = await service.get_receipt_with_details(7)

    mock_db.get_receipt_with_details.assert_awaited_once_with(7)
    assert result is None


@pytest.mark.asyncio
async def test_update_receipt_delegates(delegation_context: DelegationContext) -> None:
    """update_receipt should delegate with id and receipt."""
    service, mock_db = delegation_context
    receipt = _make_receipt()
    row = _make_row()
    mock_db.update_receipt.return_value = row

    result = await service.update_receipt(1, receipt)

    mock_db.update_receipt.assert_awaited_once_with(1, receipt)
    assert result is row


@pytest.mark.asyncio
async def test_verify_receipt_delegates(delegation_context: DelegationContext) -> None:
    """verify_receipt should delegate with id and image path."""
    service, mock_db = delegation_context
    row = _make_row(status="verified")
    mock_db.verify_receipt.return_value = row

    result = await service.verify_receipt(1, "/save/receipt_1.png")

    mock_db.verify_receipt.assert_awaited_once_with(1, "/save/receipt_1.png")
    assert result is row
