import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ...helper.logging_config import setup_logging

setup_logging()

from ...model.receipt import Receipt
from ...provider.llm.base import LLMProvider, ModelInfo

try:
    from openai import APIConnectionError, APIStatusError, AsyncOpenAI
except ImportError:
    raise ImportError(
        "The 'openai' package is required for OpenAIProvider. Please install it with 'uv add openai'."
    )


logger = logging.getLogger(__name__)

RETRY_LIMIT = 3
REASONING_EFFORT = "low"
VISION_CAPABILITY_FIELDS = ("multimodal", "vision")


class OpenAIProvider(LLMProvider):
    def __init__(self, host: str, api_key: str, temperature: float = 0.0):
        self._client = AsyncOpenAI(base_url=host, api_key=api_key)
        self._temperature = temperature

    def update_runtime_settings(self, *, temperature: float) -> None:
        self._temperature = temperature

    async def check_connection(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except (APIConnectionError, APIStatusError) as e:
            # The openai SDK wraps every transport failure into
            # APIConnectionError (incl. APITimeoutError for timeouts) once
            # retries are exhausted, and HTTP error responses into
            # APIStatusError — so these two cover all "unreachable" modes.
            logger.warning("OpenAI-compatible connection check failed: %s", e)
            return False

    # The methods below get their real implementations in follow-up tasks;
    # these typed stubs keep the class instantiable in the meantime.
    async def get_available_models(self) -> list[ModelInfo]:
        raise NotImplementedError

    async def analyse_receipt_from_model(
        self, model_id: str, image: Path, tags: Sequence[str] | None = None
    ) -> Receipt:
        raise NotImplementedError

    async def send_message(self, model_id: str, messages: Sequence[Mapping[str, Any]]) -> str:
        raise NotImplementedError
