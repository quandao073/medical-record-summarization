"""OpenAI provider — gpt-4o, gpt-4o-mini, etc."""

from __future__ import annotations

import os

from openai import OpenAI

from ..base import BaseLLMClient
from ..types import LLMResponse
from ..errors import APIKeyMissingError


class OpenAIClient(BaseLLMClient):

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_tokens: int = 1200,
        temperature: float = 0,
        api_key: str | None = None,
    ):
        super().__init__(model, max_tokens, temperature)
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise APIKeyMissingError("OPENAI_API_KEY not set")
        self._client = OpenAI(api_key=key)

    @property
    def provider_name(self) -> str:
        return "openai"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        kwargs: dict = dict(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature if temperature is not None else self.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = self._client.chat.completions.create(**kwargs)
        text = resp.choices[0].message.content.strip()
        tokens = resp.usage.prompt_tokens + resp.usage.completion_tokens
        return LLMResponse(text=text, total_tokens=tokens)
