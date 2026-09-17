from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from PIL import Image

from vision_bill.config import Settings
from vision_bill.model.image import ImageInfo
from vision_bill.service.image_service import ImageService, UnsupportedImageTypeError

RECEIPT_ID = UUID("00000000-0000-4000-8000-000000000001")


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

    original, thumb = image_service.store_perm_image(tmp_path, RECEIPT_ID)

    assert original is not None
    assert original == save_dir / f"receipt_{RECEIPT_ID}.png"
    assert original.exists()
    assert not tmp_path.exists()
    assert original.read_bytes() == content
    assert thumb is None  # fake (undecodable) content -> no thumbnail was made


def test_store_perm_image_missing_returns_none(
    image_service: ImageService,
    settings: Settings,
) -> None:
    """store_perm_image returns (None, None) when the tmp file no longer exists."""
    missing = Path(settings.images.tmp_dir) / "does_not_exist.png"

    original, thumb = image_service.store_perm_image(missing, RECEIPT_ID)

    assert original is None
    assert thumb is None


def test_heif_opener_registered() -> None:
    """Importing image_service registers the pillow-heif opener; a real PNG opens."""
    import vision_bill.service.image_service  # noqa: F401  (registers on import)

    buf = BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="PNG")
    buf.seek(0)
    assert Image.open(buf).size == (4, 4)
    # register_heif_opener() registers 'HEIF' in Image.OPEN and extensions in Image.EXTENSION
    assert "HEIF" in Image.OPEN
    assert ".heif" in Image.EXTENSION
    assert ".heic" in Image.EXTENSION


def _write_image(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> Path:
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def test_generate_thumbnail_creates_webp_in_thumbnails_dir(
    image_service: ImageService, settings: Settings, tmp_path: Path
) -> None:
    src = _write_image(tmp_path / "photo.png", (1000, 800), (10, 20, 30))

    result = image_service.generate_thumbnail(src)

    assert result is not None
    assert result == tmp_path / "thumbnails" / "photo.thumb.webp"
    assert result.exists()
    with Image.open(result) as im:
        w, h = im.size
    assert max(w, h) <= 512  # long edge capped
    assert abs((w / h) - (1000 / 800)) < 0.02  # aspect ratio preserved


def test_generate_thumbnail_never_upscales(image_service: ImageService, tmp_path: Path) -> None:
    src = _write_image(tmp_path / "tiny.png", (10, 10), (255, 0, 0))

    result = image_service.generate_thumbnail(src)

    assert result is not None
    with Image.open(result) as im:
        w, h = im.size
    assert max(w, h) <= 10  # small image is not enlarged to 512


def test_generate_thumbnail_returns_none_on_corrupt(
    image_service: ImageService, tmp_path: Path
) -> None:
    src = tmp_path / "bad.png"
    src.write_bytes(b"this is not an image")

    assert image_service.generate_thumbnail(src) is None
    assert not (tmp_path / "thumbnails" / "bad.thumb.webp").exists()


def test_store_perm_image_moves_thumb(image_service: ImageService, settings: Settings) -> None:
    """When a thumbnail exists, store_perm_image moves it to save_dir/thumbnails/."""
    from PIL import Image as PILImage

    tmp_src = Path(settings.images.tmp_dir) / "real.png"
    PILImage.new("RGB", (80, 60), (0, 0, 255)).save(tmp_src, format="PNG")
    image_service.generate_thumbnail(tmp_src)  # creates real.thumb.webp
    save_dir = Path(settings.images.save_dir)

    original, thumb = image_service.store_perm_image(tmp_src, RECEIPT_ID)

    assert original == save_dir / f"receipt_{RECEIPT_ID}.png"
    assert thumb == save_dir / "thumbnails" / f"receipt_{RECEIPT_ID}.thumb.webp"
    assert original is not None and original.exists()
    assert thumb is not None and thumb.exists()
    assert not tmp_src.exists()
    assert not (Path(settings.images.tmp_dir) / "thumbnails" / "real.thumb.webp").exists()


def test_delete_image_removes_thumb(image_service: ImageService, tmp_path: Path) -> None:
    """delete_image removes the thumbnail (in the thumbnails/ subfolder) when present."""
    from PIL import Image as PILImage

    src = tmp_path / "gone.png"
    PILImage.new("RGB", (20, 20), (1, 1, 1)).save(src, format="PNG")
    thumb = image_service.generate_thumbnail(src)
    assert thumb is not None and thumb.exists()

    assert image_service.delete_image(src) is True
    assert not src.exists()
    assert not thumb.exists()
