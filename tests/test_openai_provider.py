from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vision_bill.provider.llm.openai import OpenAIProvider


@pytest.fixture
def mock_client():
    """Fixture to mock the openai.AsyncOpenAI client."""
    with patch("vision_bill.provider.llm.openai.AsyncOpenAI") as mocked_client:
        client = AsyncMock()
        mocked_client.return_value = client
        yield client


@pytest.mark.asyncio
async def test_check_connection_success(mock_client):
    mock_client.models.list.return_value = MagicMock()

    provider = OpenAIProvider(host="http://localhost:8642/v1", api_key="none")
    assert await provider.check_connection() is True
    mock_client.models.list.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_connection_connection_error(mock_client):
    from openai import APIConnectionError

    mock_client.models.list.side_effect = APIConnectionError(request=MagicMock())

    provider = OpenAIProvider(host="http://localhost:8642/v1", api_key="none")
    assert await provider.check_connection() is False
    mock_client.models.list.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_connection_status_error(mock_client):
    from openai import APIStatusError

    mock_client.models.list.side_effect = APIStatusError(
        message="server error", response=MagicMock(status_code=500), body=None
    )

    provider = OpenAIProvider(host="http://localhost:8642/v1", api_key="none")
    assert await provider.check_connection() is False
    mock_client.models.list.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_connection_unexpected_error_propagates(mock_client):
    # Only openai connection/status errors map to "unreachable" (the SDK
    # wraps every transport failure into those); anything else is a bug
    # and must surface.
    mock_client.models.list.side_effect = RuntimeError("boom")

    provider = OpenAIProvider(host="http://localhost:8642/v1", api_key="none")
    with pytest.raises(RuntimeError, match="boom"):
        await provider.check_connection()
    mock_client.models.list.assert_awaited_once()


@pytest.mark.asyncio
async def test_constructor_passes_host_verbatim():
    with patch("vision_bill.provider.llm.openai.AsyncOpenAI") as mocked_client:
        OpenAIProvider(host="http://localhost:8642/v1", api_key="none")
        kwargs = mocked_client.call_args.kwargs
        assert kwargs["base_url"] == "http://localhost:8642/v1"
        assert kwargs["api_key"] == "none"
