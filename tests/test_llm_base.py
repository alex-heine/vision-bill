import pytest

from vision_bill.provider.llm.base import LLMProvider


def test_check_connection_is_abstract():
    assert "check_connection" in LLMProvider.__abstractmethods__


def test_cannot_instantiate_llm_provider_directly():
    with pytest.raises(TypeError):
        LLMProvider()


class _IncompleteProvider(LLMProvider):
    async def get_available_models(self):
        return []

    async def analyse_receipt_from_model(self, model_id, image):
        raise NotImplementedError

    async def send_message(self, model_id, messages):
        raise NotImplementedError


def test_subclass_missing_check_connection_cannot_instantiate():
    with pytest.raises(TypeError):
        _IncompleteProvider()
