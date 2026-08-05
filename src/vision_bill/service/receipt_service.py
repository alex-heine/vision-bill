import asyncio
import logging
from dataclasses import dataclass
from fastapi import UploadFile

from ..config import Settings
from ..model.receipt import Receipt
from ..provider.factory import LLMProvider, get_llm_provider
from ..provider.llm.base import ModelInfo
from pathlib import Path
from .image_service import ImageService

logger = logging.getLogger(__name__)


@dataclass
class ModelResult:
    model_id: str
    receipt: Receipt | None
    error: str | None = None


class ReceiptService:
    def __init__(self, settings: Settings):
        self._provider: LLMProvider = get_llm_provider(settings.llm)
        self._image_service = ImageService(settings)

    async def get_available_models(self) -> list[ModelInfo]:
        logger.debug("Requesting available models from provider")
        return await self._provider.get_available_models()

    async def analyse_receipt_from_model(self, model_id: str, image: bytes) -> Receipt:
        logger.info("Analysing receipt using model: %s", model_id)
        tmp_path = self._image_service.store_tmp_image(image)

        try:
            result = await self._provider.analyse_receipt_from_model(model_id, tmp_path)
            logger.info("Successfully analysed receipt with model: %s", model_id)
            return result
        except Exception as e:
            logger.error(
                "Failed to analyse receipt with model %s: %s", model_id, str(e), exc_info=True
            )
            raise
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    async def extract_receipt_all_models(self, image: UploadFile) -> list[ModelResult]:
        """Run extraction concurrently across every available model."""
        logger.info("Starting concurrent extraction across all models for uploaded file")
        models = await self.get_available_models()
        content = await image.read()
        tmp_path = self._image_service.store_tmp_image(content)

        async def run_one(model: ModelInfo) -> ModelResult:
            try:
                logger.debug("Running extraction for model: %s", model.id)
                receipt = await self._provider.analyse_receipt_from_model(model.id, tmp_path)
                return ModelResult(model_id=model.id, receipt=receipt)
            except ValueError as e:
                logger.warning("Model %s failed with expected warning: %s", model.id, e)
                return ModelResult(model_id=model.id, receipt=None, error=str(e))
            except Exception as e:
                logger.error("Unexpected failure for model %s: %s", model.id, str(e), exc_info=True)
                return ModelResult(model_id=model.id, receipt=None, error=str(e))

        try:
            results = await asyncio.gather(*(run_one(m) for m in models))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

        logger.info("Completed concurrent extraction across all models")
        return results
