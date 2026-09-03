import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import asyncpg
from fastapi import UploadFile

from ..config import ImageSettings, PGSettings
from ..model.db.image import ImageRow
from ..model.db.receipt import ReceiptRow, ReceiptWithDetails
from ..model.receipt import Receipt
from ..provider.db.image_db import ImageDB
from ..provider.db.receipt_db import ReceiptDB
from ..provider.db.user_db import UserDB
from ..provider.llm.base import LLMProvider, ModelInfo
from .image_service import ImageService

logger = logging.getLogger(__name__)


@dataclass
class ModelResult:
    model_id: str
    receipt: Receipt | None
    error: str | None = None


class ReceiptReferencedError(Exception):
    """Raised when a receipt cannot be deleted because a benchmark references it."""


class ReceiptService:
    """Orchestrates receipt upload → LLM extraction → persistence.

    All database access is delegated to the ``ReceiptDB`` provider.
    """

    def __init__(
        self, image_settings: ImageSettings, pg_settings: PGSettings, provider: LLMProvider
    ):
        self._provider: LLMProvider = provider
        self._image_service = ImageService(image_settings)
        self._db = ReceiptDB(pg_settings)
        self._image_db = ImageDB(pg_settings)
        self._user_db = UserDB(pg_settings)

    # ── Database delegation ──────────────────────────────────────────

    async def init_db(self) -> None:
        await self._db.init_db()
        await self._image_db.init_db()
        await self._user_db.init_db()

    async def destroy_db(self) -> None:
        await self._db.destroy_db()
        await self._image_db.destroy_db()
        await self._user_db.destroy_db()

    @property
    def pool(self) -> asyncpg.Pool:
        return self._db.pool

    @property
    def db_ready(self) -> bool:
        return self._db.is_ready

    @property
    def image_db(self) -> ImageDB:
        """The images-table provider, exposed for the scheduler and API."""
        return self._image_db

    @property
    def user_db(self) -> UserDB:
        """The users-table provider, exposed for auth and ownership backfill."""
        return self._user_db

    async def list_tags(self) -> list[str]:
        """Return the allowed line-item tag vocabulary from the database."""
        return await self._db.list_tags()

    async def create_tag(self, raw_name: str) -> tuple[str, bool]:
        """Normalize a tag name and make sure it exists in the tag vocabulary.

        Returns ``(name, created)`` where ``created`` is False when a tag with
        this (normalized) name already existed. Raises ``ValueError`` for
        names that are blank or too long.
        """
        name = " ".join(raw_name.split()).lower()
        if not name:
            raise ValueError("Tag name must not be blank")
        if len(name) > 100:
            raise ValueError("Tag name must be at most 100 characters long")
        created = await self._db.create_tag(name)
        return name, created

    async def persist_receipt(
        self,
        receipt: Receipt,
        image_id: int | None = None,
        status: str = "unverified",
        verified: bool = False,
    ) -> ReceiptRow:
        return await self._db.persist_receipt(
            receipt, image_id=image_id, status=status, verified=verified
        )

    async def get_receipt_by_id(self, receipt_id: int) -> ReceiptRow | None:
        return await self._db.get_receipt_by_id(receipt_id)

    async def list_receipts(
        self,
        limit: int = 50,
        offset: int = 0,
        status: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
    ) -> list[ReceiptRow]:
        return await self._db.list_receipts(
            limit=limit,
            offset=offset,
            status=status,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )

    async def get_receipt_with_details(self, receipt_id: int) -> ReceiptWithDetails | None:
        return await self._db.get_receipt_with_details(receipt_id)

    async def update_receipt(self, receipt_id: int, receipt: Receipt) -> ReceiptRow | None:
        return await self._db.update_receipt(receipt_id, receipt)

    async def verify_receipt(self, receipt_id: int) -> ReceiptRow | None:
        return await self._db.verify_receipt(receipt_id)

    async def delete_receipt(self, receipt_id: int) -> ReceiptRow | None:
        """Delete a receipt; raises ReceiptReferencedError if a benchmark references it."""
        try:
            return await self._db.delete_receipt(receipt_id)
        except asyncpg.ForeignKeyViolationError as exc:
            raise ReceiptReferencedError(str(exc)) from exc

    # ── Image (images table) delegation ──────────────────────────────

    async def store_image(
        self,
        image_path: str,
        original_filename: str | None = None,
        media_type: str | None = None,
        size_bytes: int | None = None,
        status: str = "pending",
        bypass_review: bool = False,
    ) -> ImageRow:
        return await self._image_db.store_image(
            image_path=image_path,
            original_filename=original_filename,
            media_type=media_type,
            size_bytes=size_bytes,
            status=status,
            bypass_review=bypass_review,
        )

    async def get_image_by_id(self, image_id: int) -> ImageRow | None:
        return await self._image_db.get_image_by_id(image_id)

    async def list_pending_images(self) -> list[ImageRow]:
        return await self._image_db.list_pending_images()

    async def list_images(
        self,
        status: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImageRow]:
        return await self._image_db.list_images(status=status, limit=limit, offset=offset)

    async def mark_image_analyzed(self, image_id: int, receipt_id: int) -> None:
        await self._image_db.mark_analyzed(image_id, receipt_id)

    async def mark_image_failed(self, image_id: int, error: str) -> None:
        await self._image_db.mark_failed(image_id, error)

    async def update_image_path(self, image_id: int, image_path: str) -> None:
        await self._image_db.update_image_path(image_id, image_path)

    async def delete_image_row(self, image_id: int) -> None:
        await self._image_db.delete_image(image_id)

    # ── Extraction methods ───────────────────────────────────────────

    async def get_available_models(self) -> list[ModelInfo]:
        logger.debug("Requesting available models from provider")
        return await self._provider.get_available_models()

    async def check_connection(self) -> bool:
        """Return True if the LLM backend is reachable, False otherwise."""
        return await self._provider.check_connection()

    async def _available_tags(self) -> list[str]:
        """The tag vocabulary for the prompt; empty when the database is unavailable."""
        return await self._db.list_tags() if self.db_ready else []

    async def analyse_receipt_from_path(self, model_id: str, image_path: Path) -> Receipt:
        """Run LLM extraction on an image file whose lifetime the caller owns."""
        logger.info("Analysing receipt using model: %s", model_id)
        tags = await self._available_tags()
        try:
            result = await self._provider.analyse_receipt_from_model(
                model_id, image_path, tags=tags
            )
            logger.info("Successfully analysed receipt with model: %s", model_id)
            return result
        except Exception:
            logger.exception("Failed to analyse receipt with model %s", model_id)
            raise

    async def analyse_receipt_from_model(self, model_id: str, image: bytes) -> Receipt:
        """Store the image temporarily, run extraction, then clean up the tmp file."""
        tmp_path = self._image_service.store_tmp_image(image)
        try:
            return await self.analyse_receipt_from_path(model_id, tmp_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    async def extract_receipt_all_models(self, image: UploadFile) -> list[ModelResult]:
        """Run extraction concurrently across every available model."""
        logger.info("Starting concurrent extraction across all models for uploaded file")
        models = await self.get_available_models()
        tags = await self._available_tags()
        content = await image.read()
        tmp_path = self._image_service.store_tmp_image(content)

        async def run_one(model: ModelInfo) -> ModelResult:
            try:
                logger.debug("Running extraction for model: %s", model.id)
                receipt = await self._provider.analyse_receipt_from_model(
                    model.id, tmp_path, tags=tags
                )
                return ModelResult(model_id=model.id, receipt=receipt)
            except ValueError as e:
                logger.warning("Model %s failed with expected warning: %s", model.id, e)
                return ModelResult(model_id=model.id, receipt=None, error=str(e))
            except Exception as e:
                logger.exception("Unexpected failure for model %s", model.id)
                return ModelResult(model_id=model.id, receipt=None, error=str(e))

        try:
            results = await asyncio.gather(*(run_one(m) for m in models))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

        logger.info("Completed concurrent extraction across all models")
        return results
