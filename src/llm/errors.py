"""Custom exceptions for the LLM module."""

from __future__ import annotations


class LLMError(Exception):
    """Base exception for all LLM-related errors."""


class ProviderNotFoundError(LLMError):
    """Raised when the requested provider is not registered."""


class APIKeyMissingError(LLMError):
    """Raised when the required API key is not set."""


class LLMConnectionError(LLMError):
    """Raised when the LLM provider is unreachable."""
