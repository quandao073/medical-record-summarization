"""FastAPI dependencies — shared across routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import get_db
from src.llm import BaseLLMClient, create_llm_client, LLMError

DBSessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_llm_client(
    provider: Annotated[str | None, Query(description="LLM provider: openai | anthropic | ollama")] = None,
    model: Annotated[str | None, Query(description="Model name")] = None,
) -> BaseLLMClient:
    try:
        return create_llm_client(provider=provider, model=model)
    except LLMError as e:
        raise HTTPException(status_code=400, detail=str(e))


LLMClientDep = Annotated[BaseLLMClient, Depends(get_llm_client)]
