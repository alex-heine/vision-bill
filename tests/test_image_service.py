import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from vision_bill.config import Settings
from vision_bill.model.image import ImageInfo
from vision_bill.service.image_service import ImageService, UnsupportedImageTypeError, magic_service


@pytest.fixture
def mock_magic_service():
    """Mock for the magic_service singleton."""
    with patch("vision_bill.service.image_service.magic_service") as mocked:
        # The service uses magic_service.magic.from_buffer
        mocked.magic.from_buffer = MagicMock()
        yield mocked


@pytest.fixture
def image_service(settings, mock_magic_service):
    """Provides an ImageService instance."""
    return ImageService(settings)


@pytest.mark.parametrize(
    "content, expected_type",
    [
        (b"fake_jpeg_bytes", "image/jpeg"),
        (b"fake_png_bytes", "image/png"),
        (b"fake_webp_bytes", "image/webp"),
    ],
)
async def test_get_media_type_success(image_service, mock_magic_service, content, expected_type):
    # Arrange
    mock_magic_service.magic.from_buffer.return_value = expected_type

    # Act
    result = image_service.get_media_type(content)

    # Assert
    assert result == expected_type
    mock_magic_service.magic.from_buffer.assert_called_once()


@pytest.mark.asyncio
async def test_validate_and_inspect_success(image_service, mock_magic_service):
    # Arrange
    content = b"fake_png_bytes"
    mock_magic_service.magic.from_buffer.return_value = "image/png"

    # Act
    result = image_service.validate_and_inspect(content)

    # Assert
    assert isinstance(result, ImageInfo)
    assert result.media_type == "image/png"
    assert result.size_bytes == len(content)
    assert result.content == content


@pytest.mark.asyncio
async def test_validate_and_inspect_failure(image_service, mock_magic_service):
    # Arrange
    content = b"fake_pdf_bytes"
    mock_magic_service.magic.from_buffer.return_value = "application/pdf"

    # Act & Assert
    with pytest.raises(UnsupportedImageTypeError) as exc_info:
        image_service.validate_and_inspect(content)

    assert "application/pdf" in str(exc_info.value)


def test_store_tmp_image(image_service, settings):
    # Arrange
    content = b"fake-image-content"
    tmp_dir = Path(settings.api.tmp_dir)
    assert tmp_dir.exists()

    # Act
    saved_path = image_service.store_tmp_image(content)

    # Assert
    assert saved_path.is_absolute()
    assert saved_path.parent == tmp_dir
    assert saved_path.suffix == ".png"
    assert saved_path.exists()
