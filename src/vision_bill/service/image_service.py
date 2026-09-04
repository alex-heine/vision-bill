import logging
import shutil
import uuid
from pathlib import Path
from uuid import UUID

import magic

from ..config import ImageSettings
from ..model.image import ImageInfo

logger = logging.getLogger(__name__)


ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "image/gif",
}


class UnsupportedImageTypeError(Exception):
    """Raised when uploaded file is not an accepted image type."""

    def __init__(self, detected_type: str):
        self.detected_type = detected_type
        super().__init__(f"Unsupported image type: {detected_type}")


class MagicService:
    """Wrapper for magic to only be loaded once"""

    def __init__(self) -> None:
        self.magic = magic.Magic(mime=True)


# Singleton instance — reuse across requests instead of
# reconstructing magic.Magic() every call
magic_service = MagicService()


class ImageService:
    """Handles image inspection and validation."""

    def __init__(self, settings: ImageSettings, sniff_chunk_size: int = 4096):
        self._sniff_chunk_size = sniff_chunk_size
        self._tmp_dir = Path(settings.tmp_dir)
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._save_dir = Path(settings.save_dir)
        self._save_dir.mkdir(parents=True, exist_ok=True)

    def get_media_type(self, content: bytes) -> str:
        """
        Detect MIME type from raw bytes. Only needs a small chunk,
        so this is cheap even for large files.
        """
        chunk = content[: self._sniff_chunk_size]
        media_type = magic_service.magic.from_buffer(chunk)
        logger.debug("Detected media type: %s", media_type)
        return media_type

    def validate_and_inspect(self, content: bytes) -> ImageInfo:
        """
        Detects the media type and raises if it's not an accepted image type.
        Returns an ImageInfo with the detected type and byte size.
        """
        logger.info("Validating image content")
        media_type = self.get_media_type(content)

        if media_type not in ALLOWED_IMAGE_TYPES:
            logger.warning("Unsupported media type detected: %s", media_type)
            raise UnsupportedImageTypeError(media_type)

        logger.info("Image successfully validated as %s", media_type)
        return ImageInfo(
            media_type=media_type,
            size_bytes=len(content),
            content=content,
        )

    def store_tmp_image(self, content: bytes) -> Path:
        """Writes content to a unique temporary file and returns the path."""
        file_id = str(uuid.uuid4())
        # Use a consistent extension or derive it if needed; .png is safe for vision models
        tmp_path = self._tmp_dir / f"temp_{file_id}.png"

        with open(tmp_path, "wb") as f:
            f.write(content)

        return tmp_path

    def store_perm_image(self, tmp_path: Path, receipt_id: UUID) -> Path | None:
        """Move a tmp image to the permanent save dir under a stable name.

        Returns the destination path, or None if the tmp file no longer exists.
        """
        if not tmp_path.exists():
            logger.warning("Tmp image %s does not exist - nothing to store", tmp_path)
            return None

        destination = self._save_dir / f"receipt_{receipt_id}{tmp_path.suffix}"
        if destination.exists():
            destination = (
                self._save_dir / f"{uuid.uuid4().hex}_receipt_{receipt_id}{tmp_path.suffix}"
            )

        shutil.move(str(tmp_path), str(destination))
        return destination

    def delete_image(self, image_path: Path | None) -> bool:
        """Remove an image file from disk.

        Best-effort: returns True if a file was deleted, False if the path was
        missing or falsy. Never raises for a missing file.
        """
        if not image_path:
            return False
        if not image_path.exists():
            logger.warning("Image file %s does not exist - nothing to delete", image_path)
            return False
        image_path.unlink()
        logger.info("Deleted image file %s", image_path)
        return True
