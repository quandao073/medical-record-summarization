"""LM Studio provider — local models via OpenAI-compatible API."""

from __future__ import annotations

from openai import OpenAI

from ..base import BaseLLMClient
from ..types import LLMResponse
from ..errors import LLMConnectionError


class LMStudioClient(BaseLLMClient):

    def __init__(
        self,
        model: str = "local-model",
        max_tokens: int = 1200,
        temperature: float = 0,
        base_url: str = "http://localhost:1234/v1",
    ):
        super().__init__(model, max_tokens, temperature)
        self._base_url = base_url
        self._client = OpenAI(api_key="lm-studio", base_url=base_url)

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

        kwargs: dict = dict(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
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

        text = resp.choices[0].message.content.strip()
        prompt_tokens = resp.usage.prompt_tokens if resp.usage else 0
        completion_tokens = resp.usage.completion_tokens if resp.usage else 0
        return LLMResponse(text=text, total_tokens=prompt_tokens + completion_tokens)
