import json
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ImagePart(BaseModel):
    image_path: str
    thumbnail_path: str | None = None
    original_filename: str | None = None
    media_type: str | None = None
    size_bytes: int | None = None


class ImageRow(BaseModel):
    """Represents a single row in the `images` table.

    An image owns its on-disk path and its analysis workflow
    (pending -> processing -> analyzed | failed). A successfully analyzed image is linked
    to a receipt via ``receipt_id``.
    """

    id: UUID
    original_filename: str | None = None
    media_type: str | None = None
    size_bytes: int | None = None
    image_path: str | None = None
    thumbnail_path: str | None = None
    status: str = "pending"
    error: str | None = None
    receipt_id: UUID | None = None
    bypass_review: bool = False
    user_id: UUID | None = None
    created_at: datetime | None = None
    analyzed_at: datetime | None = None
    processing_at: datetime | None = None
    additional_images: list[ImagePart] = Field(default_factory=list)
    model_id: str | None = None

    @field_validator("additional_images", mode="before")
    @classmethod
    def decode_parts(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value

    def parts(self) -> list[ImagePart]:
        """The primary image followed by additional photos, in capture order."""
        first = ImagePart(
            image_path=self.image_path or "",
            thumbnail_path=self.thumbnail_path,
            original_filename=self.original_filename,
            media_type=self.media_type,
            size_bytes=self.size_bytes,
        )
        return [first, *self.additional_images]
