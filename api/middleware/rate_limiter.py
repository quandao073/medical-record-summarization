"""In-memory sliding-window rate limiter for the API."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

RATE_LIMITED_PREFIXES = ("/api/v1/summarize",)


class InMemoryRateLimiter:

    def __init__(self, requests_per_minute: int = 30):
        self.rpm = requests_per_minute
        self.window = 60.0
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        with self._lock:
            timestamps = self._requests[client_ip]
            cutoff = now - self.window
            self._requests[client_ip] = [t for t in timestamps if t > cutoff]
            if len(self._requests[client_ip]) >= self.rpm:
                return False
            self._requests[client_ip].append(now)
            return True


class RateLimitMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, requests_per_minute: int = 30):
        super().__init__(app)
        self.limiter = InMemoryRateLimiter(requests_per_minute)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if not any(path.startswith(p) for p in RATE_LIMITED_PREFIXES):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        if not self.limiter.is_allowed(client_ip):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit",
                    "message": f"Too many requests. Limit: {self.limiter.rpm}/min",
                },
            )
        return await call_next(request)
