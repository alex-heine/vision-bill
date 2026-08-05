import json
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import UploadFile
from pydantic import ValidationError

from ...model.receipt import Receipt


@dataclass
class ModelInfo:
    def __init__(self, id: str, parameter_size: str | None = None):
        self.id = id
        self.parameter_size = parameter_size

    id: str
    parameter_size: str | None = None
    capabilities: list[str] | None = None


class LLMProvider(ABC):
    """Interface every LLM backend must implement."""

    @abstractmethod
    async def get_available_models(self) -> list[ModelInfo]:
        """Return the models this provider currently exposes."""

    @abstractmethod
    async def analyse_receipt_from_model(self, model_id: str, image: UploadFile) -> Receipt:
        """Send an image + prompt to the given model and return the result."""


    @abstractmethod
    async def send_message(self, model_id: str, messages: Sequence[Mapping[str, Any]]) -> str:
        """Send a message to the given model and return the response."""


    def build_prompt(self) -> str:
        """Build a prompt for the LLM to analyze an image."""
        return f"""You are an receipt analyser. You will be given an image of a receipt.
    You should analyze the receipt and provide a machine-readable JSON response based on the receipt.
    Do not add any additional text or commentary. Only provide the JSON response matching this schema:

    {Receipt.model_json_schema()}
    """


    def parse_llm_response(self, response: str) -> Receipt:
        """Parse the LLM response into a Receipt object."""
        raw_text = response.strip().removeprefix("```json").removesuffix("```").strip()
        try:
            return Receipt.model_validate_json(raw_text)
        except ValidationError as e:
            # retry logic: feed error back to the LLM, or raise
            raise ValueError(f"LLM output failed validation: {e}")
