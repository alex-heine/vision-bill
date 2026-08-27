from pydantic import BaseModel, Field


class ImageInfo(BaseModel):
    media_type: str = Field(description="The type of media (e.g., 'image/jpeg', 'image/png')")
    size_bytes: int = Field(gt=0, description="Size of the image in bytes")
    content: bytes = Field(description="Raw binary content of the image")


class TempImageInfo(BaseModel):
    image_id: str = Field(description="Unique identifier for the image")
    file_path: str = Field(description="Local filesystem path to the temporary image file")
    timestamp: str = Field(description="Timestamp of when the image was processed, ISO format")
