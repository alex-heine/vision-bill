import json
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


def _format_parameter_size(n_params: int) -> str:
    """Format a raw parameter count like 27320697856 as '27.3B'."""
    for threshold, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n_params >= threshold:
            value = n_params / threshold
            return f"{value:.1f}{suffix}".replace(".0", "")
    return str(n_params)


def _is_vision_capable(entry: dict[str, Any], capabilities: list[str] | None) -> bool:
    """True when a model entry advertises image/vision input capability."""
    if capabilities and any(field in capabilities for field in VISION_CAPABILITY_FIELDS):
        return True
    architecture = entry.get("architecture")
    if isinstance(architecture, dict):
        input_modalities = architecture.get("input_modalities")
        if isinstance(input_modalities, list) and "image" in input_modalities:
            return True
    meta = entry.get("meta")
    if isinstance(meta, dict):
        for value in meta.values():
            if isinstance(value, list) and "image" in value:
                return True
    return False


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

    async def get_available_models(self) -> list[ModelInfo]:
        response = await self._client.models.with_raw_response.list()
        # llama.cpp serves a hybrid body: an Ollama-style "models" array
        # (with capabilities/details) alongside the OpenAI-style "data"
        # array. Parse the raw JSON so both are available; fall back to
        # "data" entries alone for other OpenAI-compatible servers.
        body = json.loads(response.http_response.content)
        data_entries: list[dict[str, Any]] = list(body.get("data") or [])
        ollama_entries: list[dict[str, Any]] = list(body.get("models") or [])
        data_by_id: dict[str, dict[str, Any]] = {
            str(d.get("id")): d for d in data_entries if isinstance(d, dict)
        }

        result: list[ModelInfo] = []
        for entry in ollama_entries:
            if not isinstance(entry, dict):
                continue
            model_id = str(entry.get("model") or entry.get("name") or "")
            if not model_id:
                continue
            capabilities = entry.get("capabilities")
            if not isinstance(capabilities, list):
                capabilities = []
            if not _is_vision_capable(data_by_id.get(model_id, {}), capabilities):
                continue

            details = entry.get("details")
            parameter_size = ""
            if isinstance(details, dict):
                parameter_size = str(details.get("parameter_size") or "")

            meta = (data_by_id.get(model_id) or {}).get("meta")
            if not parameter_size and isinstance(meta, dict):
                n_params = meta.get("n_params")
                if isinstance(n_params, int) and n_params > 0:
                    parameter_size = _format_parameter_size(n_params)

            mi = ModelInfo(id=model_id)
            mi.capabilities = capabilities
            digest = str(entry.get("digest") or "")
            mi.digest = digest or None
            mi.parameter_size = parameter_size or None
            result.append(mi)

        # Servers without the ollama-style array: use data entries directly.
        if not ollama_entries:
            for entry in data_entries:
                if not isinstance(entry, dict):
                    continue
                model_id = str(entry.get("id") or "")
                if not model_id:
                    continue
                if not _is_vision_capable(entry, None):
                    continue
                mi = ModelInfo(id=model_id)
                capabilities = entry.get("capabilities")
                mi.capabilities = capabilities if isinstance(capabilities, list) else []
                digest = str(entry.get("digest") or "")
                mi.digest = digest or None
                mi.parameter_size = None
                result.append(mi)

        return result

    # The methods below get their real implementations in follow-up tasks;
    # these typed stubs keep the class instantiable in the meantime.
    async def analyse_receipt_from_model(
        self, model_id: str, image: Path, tags: Sequence[str] | None = None
    ) -> Receipt:
        raise NotImplementedError

    async def send_message(self, model_id: str, messages: Sequence[Mapping[str, Any]]) -> str:
        raise NotImplementedError
