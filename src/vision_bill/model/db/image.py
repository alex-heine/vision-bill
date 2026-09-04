from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ImageRow(BaseModel):
    """Represents a single row in the `images` table.

    An image owns its on-disk path and its analysis workflow
    (pending -> analyzed | failed). A successfully analyzed image is linked
    to a receipt via ``receipt_id``.
    """

    id: UUID
    original_filename: str | None = None
    media_type: str | None = None
    size_bytes: int | None = None
    image_path: str | None = None
    status: str = "pending"
    error: str | None = None
    receipt_id: UUID | None = None
    bypass_review: bool = False
    user_id: UUID | None = None
    created_at: datetime | None = None
    analyzed_at: datetime | None = None
