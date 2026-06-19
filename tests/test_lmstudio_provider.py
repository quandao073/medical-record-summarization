"""Tests for LM Studio provider (unit — no running server required)."""

from unittest.mock import patch, MagicMock

from src.llm.providers.lmstudio_provider import LMStudioClient
from src.llm.types import LLMResponse


def test_provider_name():
    with patch("src.llm.providers.lmstudio_provider.OpenAI"):
        client = LMStudioClient(model="test-model")
    assert client.provider_name == "lmstudio"


def test_default_base_url():
    with patch("src.llm.providers.lmstudio_provider.OpenAI") as mock_openai:
        LMStudioClient(model="test-model")
    mock_openai.assert_called_once_with(
        api_key="lm-studio",
        base_url="http://localhost:1234/v1",
    )


def test_custom_base_url():
    with patch("src.llm.providers.lmstudio_provider.OpenAI") as mock_openai:
        LMStudioClient(model="test-model", base_url="http://192.168.1.100:1234/v1")
    mock_openai.assert_called_once_with(
        api_key="lm-studio",
        base_url="http://192.168.1.100:1234/v1",
    )


def test_complete_calls_openai_format():
    with patch("src.llm.providers.lmstudio_provider.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = '{"content": "test"}'
        mock_resp.usage.prompt_tokens = 10
        mock_resp.usage.completion_tokens = 5
        mock_client.chat.completions.create.return_value = mock_resp

        client = LMStudioClient(model="test-model")
        result = client.complete(
            system_prompt="You are a doctor.",
            user_prompt="Summarize this.",
        )

        assert isinstance(result, LLMResponse)
        assert result.text == '{"content": "test"}'
        assert result.total_tokens == 15
