"""Anthropic provider — Claude models."""

from __future__ import annotations

import os

import anthropic

from ..base import BaseLLMClient
from ..types import LLMResponse
from ..errors import APIKeyMissingError


class AnthropicClient(BaseLLMClient):

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 1200,
        temperature: float = 0,
        api_key: str | None = None,
    ):
        super().__init__(model, max_tokens, temperature)
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise APIKeyMissingError("ANTHROPIC_API_KEY not set")
        self._client = anthropic.Anthropic(api_key=key)

    @property
    def provider_name(self) -> str:
        return "anthropic"

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

        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=temperature if temperature is not None else self.temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        text = resp.content[0].text.strip()
        tokens = resp.usage.input_tokens + resp.usage.output_tokens
        return LLMResponse(text=text, total_tokens=tokens)
