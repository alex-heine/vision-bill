from fastapi import APIRouter

from ...config import settings

router = APIRouter(tags=["System"])


@router.get("/ui-config")
async def get_ui_config() -> dict[str, bool]:
    """Return safe runtime defaults needed by the browser UI (public, pre-auth)."""
    return {
        "bypass_review_default": settings.images.bypass_review_default,
        "registration_open": settings.auth.allow_registration,
    }


# @router.post("/compare-models")
# async def compare_models_endpoint(prompt: str, models: list[str] | None = None):
#    results = await compare_models(prompt, models)
#    return {"results": [r.__dict__ for r in results]}
