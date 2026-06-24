"""FastAPI application — Medical Record Summarization Demo."""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from api.routers import summary as summary_router
from api.routers import sources as sources_router
from api.routers import review as review_router
from api.routers import human_eval as human_eval_router
from api.routers import health as health_router
from api.routers import emr as emr_router
from api.errors import llm_error_handler, circuit_open_handler
from api.middleware.rate_limiter import RateLimitMiddleware
from api.middleware.timeout import TimeoutMiddleware
from src.c1_emr.pipeline import C1ProcessingError
from src.llm.circuit_breaker import CircuitOpenError
from src.llm.errors import LLMError
from src.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger("api")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: StarletteRequest, call_next: RequestResponseEndpoint
    ) -> StarletteResponse:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up")
    from src.db.engine import init_db, close_db, get_db
    await init_db()
    from src.db.repositories.emr_repo import EMRRepository
    async for session in get_db():
        repo = EMRRepository(session)
        patients = await repo.list_patients()
        if not patients:
            logger.info("Database empty — seeding from data/raw/...")
            from src.db.seed import seed_from_raw
            counts = await seed_from_raw(session)
            logger.info(f"Seeded: {counts}")
    yield
    await close_db()
    logger.info("Application shutting down")


app = FastAPI(
    title="Medical Record Summarization API",
    description="Citation-grounded clinical summary pipeline",
    version="0.6.0",
    lifespan=lifespan,
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(TimeoutMiddleware, timeout_seconds=120)
app.add_middleware(RateLimitMiddleware, requests_per_minute=30)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(summary_router.router, prefix="/api/v1", tags=["summary"])
app.include_router(sources_router.router, prefix="/api/v1", tags=["sources"])
app.include_router(review_router.router, prefix="/api/v1", tags=["review"])
app.include_router(human_eval_router.router, prefix="/api/v1", tags=["human-eval"])
app.include_router(health_router.router, prefix="/api/v1", tags=["health"])
app.include_router(emr_router.router, prefix="/api/v1", tags=["emr"])


app.add_exception_handler(LLMError, llm_error_handler)
app.add_exception_handler(CircuitOpenError, circuit_open_handler)


@app.exception_handler(C1ProcessingError)
async def c1_error_handler(request: Request, exc: C1ProcessingError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_failed",
            "message": "EHR validation failed",
            "errors": [
                {"field": e.field, "message": e.message, "severity": e.severity}
                for e in exc.errors
            ],
            "context": exc.context,
        },
    )
