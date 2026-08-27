from enum import Enum

from pydantic import BaseModel, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderEnum(str, Enum):
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class LLMSettings(BaseModel):
    provider: LLMProviderEnum = LLMProviderEnum.OLLAMA
    host: str  # Used for local LLMs
    api_key: str  # Used for external LLMs
    model_name: str
    temperature: float


class ApiSettings(BaseModel):
    port: int = 8080
    log_level: str = "INFO"


class ImageSettings(BaseModel):
    save_dir: str = "/app/uploads/"
    tmp_dir: str = "/app/uploads_tmp/"


class PGSettings(BaseModel):
    user: str
    password: str
    db: str = "vision_bill"
    host: str = "localhost"
    port: int = 5432

    @computed_field  # type: ignore[prop-decorator]
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pg_dsn(self) -> str:
        """Plain DSN suitable for asyncpg.create_pool."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_nested_delimiter="__",
        extra="ignore",
    )

    api: ApiSettings = ApiSettings()
    images: ImageSettings = ImageSettings()
    llm: LLMSettings
    pg: PGSettings


# Required fields (llm, pg) are populated from .env / environment variables
settings = Settings()  # type: ignore[call-arg]
