"""Factory to create LLM clients from config or explicit parameters."""

from __future__ import annotations

from pathlib import Path

import yaml

from .base import BaseLLMClient
from .errors import ProviderNotFoundError

_CONFIG_PATH = Path(__file__).parent.parent.parent / "configs" / "config.yaml"

_PROVIDER_REGISTRY: dict[str, type[BaseLLMClient]] = {}


def _ensure_registry() -> None:
    if _PROVIDER_REGISTRY:
        return
    from .providers.openai_provider import OpenAIClient
    from .providers.anthropic_provider import AnthropicClient
    from .providers.ollama_provider import OllamaClient

    _PROVIDER_REGISTRY["openai"] = OpenAIClient
    _PROVIDER_REGISTRY["anthropic"] = AnthropicClient
    _PROVIDER_REGISTRY["ollama"] = OllamaClient


def _infer_provider(model: str) -> str | None:
    """Infer provider from model name so callers can omit provider."""
    m = model.lower()
    if m.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return "openai"
    if m.startswith("claude-"):
        return "anthropic"
    return None


def create_llm_client(
    provider: str | None = None,
    model: str | None = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client.

    Resolution order for provider:
      1. Explicit ``provider`` argument.
      2. Inferred from ``model`` name (gpt-* → openai, claude-* → anthropic).
      3. ``configs/config.yaml`` (llm.provider).
    """
    _ensure_registry()

    cfg = _load_config()
    model = model or cfg.get("model", "gpt-4o-mini")

    if provider is None:
        provider = _infer_provider(model) or cfg.get("provider", "openai")

    provider = provider.lower()
    if provider not in _PROVIDER_REGISTRY:
        raise ProviderNotFoundError(
            f"Unknown provider '{provider}'. "
            f"Available: {list(_PROVIDER_REGISTRY.keys())}"
        )

    cls = _PROVIDER_REGISTRY[provider]
    return cls(model=model, **kwargs)


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("llm", {})
