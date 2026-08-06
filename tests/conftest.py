import pytest
from pathlib import Path
from vision_bill.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Fixture for testing settings with temporary directories."""
    return Settings(
        api={
            "port": 8080,
            "log_level": "INFO",
            "save_dir": str(tmp_path / "uploads"),
            "tmp_dir": str(tmp_path / "uploads_tmp"),
        },
        llm={
            "provider": "ollama",
            "host": "localhost",
            "api_key": "none",
            "model_name": "llama3:vision",
            "temperature": 0.7,
        },
        pg={
            "user": "user",
            "password": "pass",
            "db": "vision_bill",
            "host": "localhost",
            "port": 5432,
        },
    )
