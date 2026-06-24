"""Centralized error handlers for the API."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from src.llm.errors import LLMError
from src.llm.circuit_breaker import CircuitOpenError


async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": "llm_error",
            "message": str(exc),
        },
    )


async def circuit_open_handler(request: Request, exc: CircuitOpenError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": "service_unavailable",
            "message": "LLM service temporarily unavailable. Using fallback mode.",
        },
    )


async def db_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": "database_unavailable",
            "message": "Database temporarily unavailable. Please try again.",
        },
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred.",
        },
    )
