import io
from datetime import date as Date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from vision_bill.config import Settings
from vision_bill.model.receipt import Receipt
from vision_bill.provider.llm.base import LLMProvider, ModelInfo
from vision_bill.service.receipt_service import ReceiptService, ModelResult


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Fixture for testing settings with temporary directories."""
    return Settings(
        api={
            "port": 8080,
            "log_level": "INFO",
            "save_dir": str(tmp_path / "uploads"),
            "tmp_dir": str(tmp_path / "uploads_tmp"),
        },
        llm={
            "provider": "ollama",
            "host": "localhost",
            "api_key": "none",
            "model_name": "llama3:vision",
            "temperature": 0.7,
        },
        pg={
            "user": "user",
            "password": "pass",
            "db": "vision_bill",
            "host": "localhost",
            "port": 5432,
        },
    )


@pytest.fixture
def mock_provider() -> MagicMock:
    """Fixture for a mocked LLM provider."""
    provider = MagicMock(spec=LLMProvider)
    provider.analyse_receipt_from_model = AsyncMock()
    provider.get_available_models = AsyncMock(return_value=[])
    return provider


@pytest.fixture
def receipt_service_context(settings: Settings, mock_provider: MagicMock, tmp_path: Path):
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
        service = ReceiptService(settings, mock_provider)
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
    receipt_service_context,
    merchant_name: str,
    subtotal: str,
    total: str,
) -> None:
    # Arrange
    service, mock_provider, _, mock_path = receipt_service_context
    mock_receipt = Receipt(
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
    receipt_service_context,
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
    receipt_service_context,
) -> None:
    # Arrange
    service, mock_provider, _, _ = receipt_service_context
    model1 = ModelInfo(id="model1")
    model2 = ModelInfo(id="model2")
    mock_provider.get_available_models.return_value = [model1, model2]

    receipt1 = Receipt(
        merchant_name="Merchant 1",
        date=Date(2023, 1, 1),
        currency="USD",
        line_items=[],
        subtotal=Decimal("10.00"),
        total=Decimal("10.00"),
    )
    receipt2 = Receipt(
        merchant_name="Merchant 2",
        date=Date(2023, 1, 1),
        currency="USD",
        line_items=[],
        subtotal=Decimal("20.00"),
        total=Decimal("20.00"),
    )

    # Use side_effect to return different values for different calls
    async def side_effect(model_id, path):
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
    receipt_service_context,
) -> None:
    # Arrange
    service, mock_provider, _, _ = receipt_service_context
    model1 = ModelInfo(id="model1")
    model2 = ModelInfo(id="model2")
    mock_provider.get_available_models.return_value = [model1, model2]

    receipt2 = Receipt(
        merchant_name="Merchant 2",
        date=Date(2023, 1, 1),
        currency="USD",
        line_items=[],
        subtotal=Decimal("20.00"),
        total=Decimal("20.00"),
    )

    async def side_effect(model_id, path):
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
    assert "Invalid receipt format" in res1.error
    assert res2.receipt == receipt2
    assert res2.error is None


@pytest.mark.asyncio
async def test_extract_receipt_all_models_exception(
    receipt_service_context,
) -> None:
    # Arrange
    service, mock_provider, _, _ = receipt_service_context
    model1 = ModelInfo(id="model1")
    model2 = ModelInfo(id="model2")
    mock_provider.get_available_models.return_value = [model1, model2]

    receipt2 = Receipt(
        merchant_name="Merchant 2",
        date=Date(2023, 1, 1),
        currency="USD",
        line_items=[],
        subtotal=Decimal("20.00"),
        total=Decimal("20.00"),
    )

    async def side_effect(model_id, path):
        if model_id == "model1":
            raise Exception("Generic failure")
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
    assert "Generic failure" in res1.error
    assert res2.receipt == receipt2
    assert res2.error is None
