"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import LLMResponse


class BaseLLMClient(ABC):
    """Unified interface that every LLM provider must implement."""

    def __init__(self, model: str, max_tokens: int = 1200, temperature: float = 0):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model!r})"
