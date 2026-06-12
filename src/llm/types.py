"""Shared types for the LLM module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    total_tokens: int
