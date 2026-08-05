from enum import Enum

from pydantic import (
    BaseModel,
    PostgresDsn,
    computed_field,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderEnum(str, Enum):
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class LLMSettings(BaseModel):
    provider: LLMProviderEnum = LLMProviderEnum.OLLAMA
    host: str # Used for local LLMs
    api_key: str # Used for external LLMs
    model_name: str
    temperature: float


class ApiSettings(BaseModel):
    port: int = 8080
    log_level: str = 'INFO'
    save_dir: str = "/app/uploads/"
    tmp_dir: str = "/app/uploads_tmp/"


class PGSettings(BaseModel):
    user: str
    password: str
    db: str = "vision_bill"
    host: str = "localhost"
    port: int = 5432

    @computed_field
    @property
    def database_url(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            path=self.db,
        )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        extra="ignore",
    )

    api: ApiSettings
    llm: LLMSettings
    pg: PGSettings
