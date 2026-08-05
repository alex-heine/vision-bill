from fastapi import APIRouter

router = APIRouter(tags=["System"])

#@router.post("/compare-models")
#async def compare_models_endpoint(prompt: str, models: list[str] | None = None):
#    results = await compare_models(prompt, models)
#    return {"results": [r.__dict__ for r in results]}
