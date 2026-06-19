"""FastAPI application — Medical Record Summarization Demo."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routers import summary as summary_router
from api.routers import sources as sources_router
from api.routers import review as review_router
from api.routers import human_eval as human_eval_router
from api.routers import health as health_router
from src.c1_emr.pipeline import C1ProcessingError

app = FastAPI(
    title="Medical Record Summarization API",
    description="Citation-grounded clinical summary pipeline",
    version="0.5.0",
)

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
