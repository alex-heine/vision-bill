from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vision_bill.config import Settings
from vision_bill.model.image import ImageInfo
from vision_bill.service.image_service import ImageService, UnsupportedImageTypeError


@pytest.fixture
def mock_magic_service() -> Generator[MagicMock, None, None]:
    """Mock for the magic_service singleton."""
    with patch("vision_bill.service.image_service.magic_service") as mocked:
        # The service uses magic_service.magic.from_buffer
        mocked.magic.from_buffer = MagicMock()
        yield mocked


@pytest.fixture
def image_service(settings: Settings, mock_magic_service: MagicMock) -> ImageService:
    """Provides an ImageService instance."""
    return ImageService(settings.images)


@pytest.mark.parametrize(
    "content, expected_type",
    [
        (b"fake_jpeg_bytes", "image/jpeg"),
        (b"fake_png_bytes", "image/png"),
        (b"fake_webp_bytes", "image/webp"),
    ],
)
async def test_get_media_type_success(
    image_service: ImageService,
    mock_magic_service: MagicMock,
    content: bytes,
    expected_type: str,
) -> None:
    # Arrange
    mock_magic_service.magic.from_buffer.return_value = expected_type

    # Act
    result = image_service.get_media_type(content)

    # Assert
    assert result == expected_type
    mock_magic_service.magic.from_buffer.assert_called_once()


@pytest.mark.asyncio
async def test_validate_and_inspect_success(
    image_service: ImageService,
    mock_magic_service: MagicMock,
) -> None:
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
async def test_validate_and_inspect_failure(
    image_service: ImageService,
    mock_magic_service: MagicMock,
) -> None:
    # Arrange
    content = b"fake_pdf_bytes"
    mock_magic_service.magic.from_buffer.return_value = "application/pdf"

    # Act & Assert
    with pytest.raises(UnsupportedImageTypeError) as exc_info:
        image_service.validate_and_inspect(content)

    assert "application/pdf" in str(exc_info.value)


def test_store_tmp_image(image_service: ImageService, settings: Settings) -> None:
    # Arrange
    content = b"fake-image-content"
    tmp_dir = Path(settings.images.tmp_dir)
    assert tmp_dir.exists()

    # Act
    saved_path = image_service.store_tmp_image(content)

    # Assert
    assert saved_path.is_absolute()
    assert saved_path.parent == tmp_dir
    assert saved_path.suffix == ".png"
    assert saved_path.exists()


def test_store_perm_image_moves_file(image_service: ImageService, settings: Settings) -> None:
    """store_perm_image moves the tmp file into the save dir under a stable name."""
    content = b"fake-image-content"
    tmp_path = image_service.store_tmp_image(content)
    save_dir = Path(settings.images.save_dir)

    result = image_service.store_perm_image(tmp_path, 42)

    assert result is not None
    assert result == save_dir / "receipt_42.png"
    assert result.exists()
    assert not tmp_path.exists()
    assert result.read_bytes() == content


def test_store_perm_image_missing_returns_none(
    image_service: ImageService,
    settings: Settings,
) -> None:
    """store_perm_image returns None when the tmp file no longer exists."""
    missing = Path(settings.images.tmp_dir) / "does_not_exist.png"

    result = image_service.store_perm_image(missing, 1)

    assert result is None
