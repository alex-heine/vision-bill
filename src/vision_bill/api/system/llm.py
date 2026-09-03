from typing import Any

from fastapi import APIRouter, Depends

from ...config import settings
from ...provider.factory import get_llm_provider
from ...security.dependencies import get_current_user

router = APIRouter(tags=["LLM", "AI", "Model Evaluation"], dependencies=[Depends(get_current_user)])


@router.get("/models")
async def list_models() -> list[dict[str, Any]]:
    provider = get_llm_provider(settings.llm)
    models = await provider.get_available_models()
    return [m.__dict__ for m in models]
