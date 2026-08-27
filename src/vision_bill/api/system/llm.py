from typing import Any

from fastapi import APIRouter

from ...config import settings
from ...provider.factory import get_llm_provider

router = APIRouter(tags=["LLM", "AI", "Model Evaluation"])


@router.get("/models")
async def list_models() -> list[dict[str, Any]]:
    provider = get_llm_provider(settings.llm)
    models = await provider.get_available_models()
    return [m.__dict__ for m in models]
