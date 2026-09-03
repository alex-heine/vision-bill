import os
from pathlib import Path

import pytest

# Test-only default for the required auth secret. ``vision_bill.config`` builds
# a module-level ``settings`` on import, which needs ``AUTH__SECRET_KEY``; this
# keeps the test suite independent of an operator's ``.env``. A value already
# present in the environment (or ``.env``) wins because this uses setdefault.
TEST_AUTH_SECRET = "test-secret-key-do-not-use-in-prod"
os.environ.setdefault("AUTH__SECRET_KEY", TEST_AUTH_SECRET)

from vision_bill.config import (  # noqa: E402
    ApiSettings,
    AuthSettings,
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
        auth=AuthSettings(secret_key=TEST_AUTH_SECRET),
    )
