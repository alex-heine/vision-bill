import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..model.db.image import ImageRow
from ..provider.db.image_db import ImageDB
from ..provider.llm.base import LLMProvider, ModelInfo
from .receipt_service import ReceiptService

logger = logging.getLogger(__name__)


@dataclass
class PendingImageResult:
    """Outcome of analysing a single queued image."""

    image_id: int
    status: str  # "analyzed" | "failed"
    receipt_id: int | None = None
    error: str | None = None


class AnalysisScheduler:
    """Drains the pending-image queue by running LLM extraction on each image.

    Runs as a background task started from the app lifespan and can also be
    triggered on demand via the ``POST /images/analyze`` endpoint. Both paths
    funnel through :meth:`process_pending`, which is guarded by an
    ``asyncio.Lock`` so a manual trigger and the periodic cycle never overlap.

    There is deliberately no terminal "unreachable" state: if the LLM provider
    is down at cycle time the images simply stay ``pending`` and are retried on
    the next cycle.
    """

    def __init__(
        self,
        settings: Settings,
        provider: LLMProvider,
        receipt_service: ReceiptService,
        image_db: ImageDB,
    ):
        self._settings = settings
        self._provider = provider
        self._receipt_service = receipt_service
        self._image_db = image_db
        self._interval = settings.worker.check_interval_seconds
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    @property
    def check_interval_seconds(self) -> int:
        return self._interval

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._task is not None:
            logger.warning("Analysis scheduler already running - skipping start")
            return
        self._task = asyncio.create_task(self._run_forever())
        logger.info("Analysis scheduler started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("Analysis scheduler stopped")

    async def _run_forever(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.process_pending()
            except Exception:
                logger.exception("Unexpected error in analysis cycle")

    # ── Core cycle ───────────────────────────────────────────────────

    async def process_pending(self) -> list[PendingImageResult]:
        """Run one analysis cycle, serialised against concurrent triggers."""
        async with self._lock:
            if not (self._receipt_service.db_ready and self._image_db.is_ready):
                logger.info("Database not ready - skipping analysis cycle")
                return []
            return await self._process_pending_unlocked()

    def _select_model(self, models: list[ModelInfo]) -> str:
        """Prefer the configured model, fall back to the first vision model."""
        preferred = self._settings.llm.model_name
        for model in models:
            if model.id == preferred:
                return model.id
        return models[0].id

    async def _process_pending_unlocked(self) -> list[PendingImageResult]:
        try:
            models = await self._provider.get_available_models()
        except Exception:  # noqa: BLE001 - worker boundary: any failure keeps images queued
            logger.warning("LLM provider unreachable - pending images stay queued")
            return []

        if not models:
            logger.warning("No vision models available - pending images stay queued")
            return []

        model_id = self._select_model(models)
        pending = await self._image_db.list_pending_images()
        logger.info("Analysis cycle: %d image(s) queued, using model %s", len(pending), model_id)
        return [await self._analyze_one(image, model_id) for image in pending]

    async def _analyze_one(self, image: ImageRow, model_id: str) -> PendingImageResult:
        image_path = Path(image.image_path) if image.image_path else None
        if image_path is None or not image_path.exists():
            error = f"Image file missing: {image.image_path}"
            logger.error(error)
            await self._image_db.mark_failed(image.id, error)
            return PendingImageResult(image_id=image.id, status="failed", error=error)

        try:
            receipt = await self._receipt_service.analyse_receipt_from_path(model_id, image_path)
        except Exception as e:  # noqa: BLE001 - worker boundary: fail the image, never the cycle
            # The provider already exhausted its self-correction retry loop.
            await self._image_db.mark_failed(image.id, str(e))
            return PendingImageResult(image_id=image.id, status="failed", error=str(e))

        try:
            row = await self._receipt_service.persist_receipt(
                receipt, image_id=image.id, status="unverified"
            )
            await self._image_db.mark_analyzed(image.id, row.id)
        except Exception as e:  # noqa: BLE001 - worker boundary: fail the image, never the cycle
            error = f"Failed to persist receipt: {e}"
            await self._image_db.mark_failed(image.id, error)
            return PendingImageResult(image_id=image.id, status="failed", error=error)

        return PendingImageResult(image_id=image.id, status="analyzed", receipt_id=row.id)
