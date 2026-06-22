"""LM Studio provider — local models via OpenAI-compatible API."""

from __future__ import annotations

import os
import re

from openai import OpenAI

from ..base import BaseLLMClient
from ..types import LLMResponse
from ..errors import LLMConnectionError

THINKING_MODELS = {"qwen3", "qwen3.5", "deepseek-r1", "gemma-4"}
THINKING_TOKEN_MULTIPLIER = 3


def _is_thinking_model(model: str) -> bool:
    model_lower = model.lower()
    return any(t in model_lower for t in THINKING_MODELS)


def _strip_thinking_tags(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


class LMStudioClient(BaseLLMClient):

    def __init__(
        self,
        model: str = "local-model",
        max_tokens: int = 1200,
        temperature: float = 0,
        base_url: str | None = None,
    ):
        super().__init__(model, max_tokens, temperature)
        self._base_url = base_url or os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
        self._client = OpenAI(api_key="lm-studio", base_url=self._base_url)

    @property
    def provider_name(self) -> str:
        return "lmstudio"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        user_content = user_prompt
        if json_mode:
            user_content += "\n\nRespond with valid JSON only, no extra text."

        base_max = max_tokens or self.max_tokens
        if _is_thinking_model(self.model):
            effective_max = base_max * THINKING_TOKEN_MULTIPLIER
        else:
            effective_max = base_max

        kwargs: dict = dict(
            model=self.model,
            max_tokens=effective_max,
            temperature=temperature if temperature is not None else self.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )

        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:
            raise LLMConnectionError(
                f"Cannot reach LM Studio at {self._base_url}. "
                f"Make sure LM Studio is running with a model loaded. Error: {e}"
            ) from e

        raw_text = resp.choices[0].message.content or ""
        text = _strip_thinking_tags(raw_text).strip()

        prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
        completion_tokens = resp.usage.completion_tokens if resp.usage else 0
        return LLMResponse(text=text, total_tokens=prompt_tokens + completion_tokens)
