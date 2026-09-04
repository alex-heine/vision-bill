import logging
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx

from ...helper.logging_config import setup_logging

setup_logging()

from ...model.receipt import Receipt
from ...provider.llm.base import AnalysisResult, LLMProvider, ModelInfo

try:
    from ollama import AsyncClient, ListResponse, ResponseError
except ImportError:
    raise ImportError(
        "The 'ollama' package is required for OllamaProvider. Please install it with 'uv add ollama'."
    )


logger = logging.getLogger(__name__)


VISION_CAPABILITY_FIELD = "vision"
STRUCTURED_CAPABILITY_FIELD = "structured"
RETRY_LIMIT = 3


class OllamaProvider(LLMProvider):
    def __init__(self, host: str, temperature: float = 0.0):
        self._client = AsyncClient(host=host)
        self._temperature = temperature

    def update_runtime_settings(self, *, temperature: float) -> None:
        self._temperature = temperature

    async def check_connection(self) -> bool:
        try:
            await self._client.list()
            return True
        except (ConnectionError, ResponseError, httpx.HTTPError) as e:
            # The SDK raises ConnectionError when Ollama is unreachable,
            # ResponseError on HTTP error responses, and raw httpx errors
            # (e.g. timeouts) otherwise.
            logger.warning("Ollama connection check failed: %s", e)
            return False

    async def get_available_models(self) -> list[ModelInfo]:
        models: ListResponse = await self._client.list()
        result = []
        for model in models.models:
            # model.model is the name of the model, e.g., "gemma4:e4b", we need this for all further calls.
            if not model.model:
                continue

            details = await self._client.show(model.model)
            # If the model does not support vision, we skip it.
            if not details.capabilities or VISION_CAPABILITY_FIELD not in details.capabilities:
                continue

            mi = ModelInfo(id=model.model)
            mi.digest = getattr(model, "digest", None)
            if model.details:
                mi.parameter_size = model.details.parameter_size

            mi.capabilities = details.capabilities

            result.append(mi)

        return result

    async def analyse_receipt_from_model(
        self, model_id: str, image: Path, tags: Sequence[str] | None = None
    ) -> Receipt:
        return (await self.analyse_receipt_with_metadata(model_id, image, tags=tags)).receipt

    async def analyse_receipt_with_metadata(
        self, model_id: str, image: Path, tags: Sequence[str] | None = None
    ) -> AnalysisResult:
        from time import perf_counter

        started = perf_counter()
        messages = self._build_image_messages(image, tags)

        last_error: Exception | None = None
        for attempt in range(1, RETRY_LIMIT + 1):
            content = await self.send_message(model_id, messages)

            if not content:
                logger.warning("Attempt %d/%d: model returned no content", attempt, RETRY_LIMIT)
                last_error = ValueError("Empty response from model")
                continue

            logger.warning(f"Attempt {attempt}/{RETRY_LIMIT}: model returned content: {content}")

            if bool(re.search(r"provide.*image", content, re.IGNORECASE | re.DOTALL)):
                raise ValueError(
                    f"Model '{model_id}' returned a message indicating it cannot process images. "
                    "Please ensure the model supports vision capabilities."
                )

            try:
                return AnalysisResult(
                    receipt=self.parse_llm_response(content),
                    attempts=attempt,
                    elapsed_ms=(perf_counter() - started) * 1000,
                )
            except ValueError as e:
                logger.warning(
                    "Attempt %d/%d: failed to parse LLM response: %s",
                    attempt,
                    RETRY_LIMIT,
                    e,
                )
                last_error = e
                # Feed the parse error back so the retry has a chance to self-correct
                messages = self._append_repair_message(messages, content, e)

        raise ValueError(
            f"Failed to get a valid response from model '{model_id}' after {RETRY_LIMIT} attempts"
        ) from last_error

    async def send_message(self, model_id: str, messages: Sequence[Mapping[str, Any]]) -> str:
        response = await self._client.chat(
            model=model_id,
            # format=Receipt.model_json_schema(),
            messages=messages,
            options={"temperature": self._temperature},
        )

        return response.message.content or ""

    def _build_image_messages(
        self, image: Path, tags: Sequence[str] | None = None
    ) -> list[dict[str, Any]]:
        if not image.exists():
            raise FileNotFoundError(f"Image not found at: {image}")
        return [
            {
                "role": "user",
                "content": self.build_prompt(tags),
                "images": [image],
            }
        ]

    def _append_repair_message(
        self,
        messages: list[dict[str, Any]],
        bad_output: str,
        error: ValueError,
    ) -> list[dict[str, Any]]:
        """Append the failed output + error so the model can self-correct on retry."""
        return [
            *messages,
            {"role": "assistant", "content": bad_output},
            {
                "role": "user",
                "content": (
                    "That response was not valid JSON matching the required schema. "
                    f"Error: {error}\n\nPlease respond again with ONLY corrected JSON."
                ),
            },
        ]
