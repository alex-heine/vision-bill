from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ...config import (
    LLMProviderEnum,
    editable_setting_sources,
    runtime_restart_required,
    settings,
    write_config_file,
)
from ...security.dependencies import require_admin

router = APIRouter(tags=["System"])


class LLMSettingsUpdate(BaseModel):
    provider: LLMProviderEnum
    host: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    temperature: float


class SettingsUpdate(BaseModel):
    llm: LLMSettingsUpdate
    allow_registration: bool


class SettingsView(SettingsUpdate):
    sources: dict[str, str]
    restart_required: bool


@router.get("/ui-config")
async def get_ui_config() -> dict[str, bool]:
    """Return safe runtime defaults needed by the browser UI (public, pre-auth)."""
    return {
        "bypass_review_default": settings.images.bypass_review_default,
        "registration_open": settings.auth.allow_registration,
    }


def _settings_view() -> SettingsView:
    return SettingsView(
        llm=LLMSettingsUpdate(
            provider=settings.llm.provider,
            host=settings.llm.host,
            model_name=settings.llm.model_name,
            temperature=settings.llm.temperature,
        ),
        allow_registration=settings.auth.allow_registration,
        sources=editable_setting_sources(),
        restart_required=runtime_restart_required(settings),
    )


@router.get("/settings", response_model=SettingsView, dependencies=[Depends(require_admin)])
async def get_settings() -> SettingsView:
    """Return editable settings without exposing credentials or secrets."""
    return _settings_view()


@router.put("/settings", response_model=SettingsView, dependencies=[Depends(require_admin)])
async def update_settings(request: Request, update: SettingsUpdate) -> SettingsView:
    """Persist admin-editable settings and apply safe changes immediately."""
    sources = editable_setting_sources()
    requested = {
        "llm.provider": update.llm.provider,
        "llm.host": update.llm.host,
        "llm.model_name": update.llm.model_name,
        "llm.temperature": update.llm.temperature,
        "auth.allow_registration": update.allow_registration,
    }
    current = {
        "llm.provider": settings.llm.provider,
        "llm.host": settings.llm.host,
        "llm.model_name": settings.llm.model_name,
        "llm.temperature": settings.llm.temperature,
        "auth.allow_registration": settings.auth.allow_registration,
    }
    locked_changes = [
        field
        for field, value in requested.items()
        if sources[field] == "environment" and value != current[field]
    ]
    if locked_changes:
        raise HTTPException(
            status_code=409,
            detail=(
                "These settings are controlled by environment variables: "
                + ", ".join(locked_changes)
            ),
        )

    candidate = settings.model_copy(deep=True)
    candidate.llm.provider = update.llm.provider
    candidate.llm.host = update.llm.host
    candidate.llm.model_name = update.llm.model_name
    candidate.llm.temperature = update.llm.temperature
    candidate.auth.allow_registration = update.allow_registration
    try:
        write_config_file(candidate)
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Could not write application config") from exc

    settings.llm.provider = candidate.llm.provider
    settings.llm.host = candidate.llm.host
    settings.llm.model_name = candidate.llm.model_name
    settings.llm.temperature = candidate.llm.temperature
    settings.auth.allow_registration = candidate.auth.allow_registration
    provider = getattr(request.app.state, "llm_provider", None)
    if provider is not None:
        provider.update_runtime_settings(temperature=settings.llm.temperature)
    return _settings_view()


# @router.post("/compare-models")
# async def compare_models_endpoint(prompt: str, models: list[str] | None = None):
#    results = await compare_models(prompt, models)
#    return {"results": [r.__dict__ for r in results]}
