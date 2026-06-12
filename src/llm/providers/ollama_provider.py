"""Ollama provider — local models (llama3, mistral, gemma, etc.)."""

from __future__ import annotations

import json
import urllib.request
import urllib.error

from ..base import BaseLLMClient
from ..types import LLMResponse
from ..errors import LLMConnectionError


class OllamaClient(BaseLLMClient):

    def __init__(
        self,
        model: str = "llama3",
        max_tokens: int = 1200,
        temperature: float = 0,
        base_url: str = "http://localhost:11434",
    ):
        super().__init__(model, max_tokens, temperature)
        self._base_url = base_url.rstrip("/")

    @property
    def provider_name(self) -> str:
        return "ollama"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "stream": False,
            "options": {
                "num_predict": max_tokens or self.max_tokens,
                "temperature": temperature if temperature is not None else self.temperature,
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_mode:
            payload["format"] = "json"

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self._base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                body = json.loads(resp.read())
        except urllib.error.URLError as e:
            raise LLMConnectionError(
                f"Cannot reach Ollama at {self._base_url}. "
                "Make sure Ollama is running (ollama serve)."
            ) from e

        text = body.get("message", {}).get("content", "").strip()
        prompt_tokens = body.get("prompt_eval_count", 0)
        completion_tokens = body.get("eval_count", 0)
        return LLMResponse(text=text, total_tokens=prompt_tokens + completion_tokens)
