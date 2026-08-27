from pathlib import Path

import pytest

from vision_bill.config import (
    ApiSettings,
    ImageSettings,
    LLMProviderEnum,
    LLMSettings,
    PGSettings,
    Settings,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Fixture for testing settings with temporary directories."""
    return Settings(
        api=ApiSettings(
            port=8080,
            log_level="INFO",
        ),
        images=ImageSettings(
            save_dir=str(tmp_path / "uploads"),
            tmp_dir=str(tmp_path / "uploads_tmp"),
        ),
        llm=LLMSettings(
            provider=LLMProviderEnum.OLLAMA,
            host="localhost",
            api_key="none",
            model_name="llama3:vision",
            temperature=0.7,
        ),
        pg=PGSettings(
            user="user",
            password="pass",
            db="vision_bill",
            host="localhost",
            port=5432,
        ),
    )
