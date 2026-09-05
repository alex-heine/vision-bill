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


import json as _json


def _hybrid_body(models_entries, data_entries):
    """Build a realistic llama.cpp hybrid /v1/models body."""
    return _json.dumps(
        {
            "models": models_entries,
            "object": "list",
            "data": data_entries,
        }
    ).encode()


def _raw_response(body_bytes):
    """Build a stand-in for `await client.models.with_raw_response.list()`."""
    http_response = MagicMock()
    http_response.content = body_bytes
    return MagicMock(http_response=http_response)


def _ollama_entry(model, capabilities, digest="", parameter_size=""):
    return {
        "name": model,
        "model": model,
        "digest": digest,
        "tags": [],
        "capabilities": capabilities,
        "details": {"parameter_size": parameter_size, "format": "gguf", "quantization_level": ""},
    }


def _openai_entry(model_id, n_params):
    return {
        "id": model_id,
        "aliases": [model_id],
        "tags": [],
        "object": "model",
        "created": 1788563881,
        "owned_by": "llamacpp",
        "meta": {"n_params": n_params, "size": 13135396864, "ftype": "Q3_K - Large", "n_ctx": 32000},
    }


@pytest.mark.asyncio
async def test_get_available_models_filters_to_vision(mock_client):
    body = _hybrid_body(
        [
            _ollama_entry("qwen-vision:27b", ["completion", "multimodal"], digest="sha256:abc123"),
            _ollama_entry("textonly:7b", ["completion"]),
        ],
        [
            _openai_entry("qwen-vision:27b", 27320697856),
            _openai_entry("textonly:7b", 7000000000),
        ],
    )
    mock_client.models.with_raw_response.list.return_value = _raw_response(body)

    provider = OpenAIProvider(host="http://localhost:8642/v1", api_key="none")
    models = await provider.get_available_models()

    assert [m.id for m in models] == ["qwen-vision:27b"]
    assert models[0].capabilities == ["completion", "multimodal"]
    assert models[0].digest == "sha256:abc123"
    # details.parameter_size is empty on this build -> formatted from meta.n_params
    assert models[0].parameter_size == "27.3B"


@pytest.mark.asyncio
async def test_get_available_models_prefers_details_parameter_size(mock_client):
    body = _hybrid_body(
        [_ollama_entry("gemma:7b", ["completion", "vision"], digest="sha256:xyz", parameter_size="7B")],
        [_openai_entry("gemma:7b", 7000000000)],
    )
    mock_client.models.with_raw_response.list.return_value = _raw_response(body)

    provider = OpenAIProvider(host="http://localhost:8642/v1", api_key="none")
    models = await provider.get_available_models()

    assert [m.id for m in models] == ["gemma:7b"]
    assert models[0].parameter_size == "7B"
    # "vision" is an accepted capability marker too
    assert models[0].capabilities == ["completion", "vision"]


@pytest.mark.asyncio
async def test_get_available_models_falls_back_to_data_entries(mock_client):
    # Build without the ollama-style "models" array (other OpenAI-compatible
    # servers): ids come from data[].id, vision from architecture.input_modalities.
    body = _json.dumps(
        {
            "object": "list",
            "data": [
                {
                    "id": "vl-model",
                    "object": "model",
                    "created": 1,
                    "owned_by": "x",
                    "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
                },
                {
                    "id": "text-model",
                    "object": "model",
                    "created": 1,
                    "owned_by": "x",
                    "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                },
            ],
        }
    ).encode()
    mock_client.models.with_raw_response.list.return_value = _raw_response(body)

    provider = OpenAIProvider(host="http://localhost:8642/v1", api_key="none")
    models = await provider.get_available_models()

    assert [m.id for m in models] == ["vl-model"]
    assert models[0].digest is None
    assert models[0].parameter_size is None


@pytest.mark.asyncio
async def test_get_available_models_skips_empty_ids(mock_client):
    entry = _ollama_entry("", ["completion", "multimodal"])
    body = _hybrid_body([entry], [_openai_entry("", 1000000)])
    mock_client.models.with_raw_response.list.return_value = _raw_response(body)

    provider = OpenAIProvider(host="http://localhost:8642/v1", api_key="none")
    models = await provider.get_available_models()

    assert models == []
