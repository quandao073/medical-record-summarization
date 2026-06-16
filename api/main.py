"""FastAPI application — Medical Record Summarization Demo."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import summary as summary_router
from api.routers import sources as sources_router
from api.routers import review as review_router
from api.routers import human_eval as human_eval_router

app = FastAPI(
    title="Medical Record Summarization API",
    description="Citation-grounded clinical summary pipeline",
    version="0.4.0",
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


@app.get("/api/v1/health", tags=["health"])
def health():
    return {"status": "ok", "version": "0.4.0"}
