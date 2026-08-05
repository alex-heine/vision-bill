from fastapi import APIRouter

from ...config import Settings
from ...provider.factory import get_llm_provider

router = APIRouter(tags=["LLM", "AI", "Model Evaluation"])


@router.get("/models")
async def list_models():
    provider = get_llm_provider(Settings().llm)
    models = await provider.get_available_models()
    return [m.__dict__ for m in models]


#@router.post("/compare-models")
#async def compare_models_endpoint(prompt: str, models: list[str] | None = None):
#    results = await compare_models(prompt, models)
#    return {"results": [r.__dict__ for r in results]}
