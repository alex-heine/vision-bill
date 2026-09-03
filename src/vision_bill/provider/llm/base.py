from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

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
    digest: str | None = None


@dataclass
class AnalysisResult:
    receipt: Receipt
    attempts: int
    elapsed_ms: float
    model_digest: str | None = None


class LLMProvider(ABC):
    """Interface every LLM backend must implement."""

    @abstractmethod
    async def get_available_models(self) -> list[ModelInfo]:
        """Return the models this provider currently exposes."""

    @abstractmethod
    async def analyse_receipt_from_model(
        self, model_id: str, image: Path, tags: Sequence[str] | None = None
    ) -> Receipt:
        """Send an image + prompt to the given model and return the result.

        ``tags`` is the allowed line-item tag vocabulary; when provided it is
        embedded in the prompt so the model only emits known tags.
        """

    @abstractmethod
    async def send_message(self, model_id: str, messages: Sequence[Mapping[str, Any]]) -> str:
        """Send a message to the given model and return the response."""

    @abstractmethod
    async def check_connection(self) -> bool:
        """Return True if the backend is reachable, False otherwise."""

    async def analyse_receipt_with_metadata(
        self, model_id: str, image: Path, tags: Sequence[str] | None = None
    ) -> AnalysisResult:
        """Compatibility wrapper for providers which do not expose attempt telemetry."""
        started = perf_counter()
        receipt = await self.analyse_receipt_from_model(model_id, image, tags=tags)
        return AnalysisResult(
            receipt=receipt, attempts=1, elapsed_ms=(perf_counter() - started) * 1000
        )

    def build_prompt(self, tags: Sequence[str] | None = None) -> str:
        """Build a prompt for the LLM to analyze an image.

        When ``tags`` is provided, the prompt gives the model the full tag
        vocabulary and lets it suggest one new tag when nothing fits; otherwise
        the model may invent short free-form tags.
        """
        if tags:
            tag_instruction = (
                "Add short tags to each line_item when useful. Prefer tags from this list: "
                f"{', '.join(tags)}. If no tag in the list fits, you may suggest a single new "
                "short tag (lowercase snake_case, at most three words); suggested tags are "
                "reviewed by a human before they become standard tags."
            )
        else:
            tag_instruction = "Add short free-form tags to each line_item when useful."
        return f"""You are an receipt analyser. You will be given an image of a receipt.
    You should analyze the receipt and provide a machine-readable JSON response based on the receipt.
    List line_items in the exact top-to-bottom order they appear on the receipt.
    Determine merchant_name from text that is actually printed on the receipt (store name in the
    header or footer, the address line, a website, or any other written hint).
    Do not guess or infer the company name from a logo, photo, or design; if no printed name exists,
    use the best available written hint.
    {tag_instruction}
    Set the top-level category to the single best category for the whole purchase.
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
