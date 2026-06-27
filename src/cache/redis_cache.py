"""Redis-backed summary cache with file fallback."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 86400  # 24 hours
_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"


def compute_ehr_hash(raw_ehr: dict) -> str:
    """Compute stable hash of EHR data for cache key."""
    canonical = json.dumps(raw_ehr, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def _build_cache_key(
    patient_id: str,
    ehr_hash: str,
    model: str,
    prompt_version: str = "poc_v4",
) -> str:
    return f"summary:{patient_id}:{ehr_hash}:{model}:{prompt_version}"


def _get_redis_client():
    """Get async Redis client. Returns None if Redis unavailable."""
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis.asyncio as aioredis

        return aioredis.from_url(url, decode_responses=True)
    except Exception as exc:
        logger.warning("Redis client creation failed: %s", exc)
        return None


class SummaryCache:
    """Two-tier cache: Redis (L1) + file (L2)."""

    def __init__(self, ttl: int = _DEFAULT_TTL, cache_dir: Path | None = None):
        self.ttl = ttl
        self._redis = _get_redis_client()
        self._cache_dir = cache_dir or _CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0
        self.errors = 0

    @property
    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses, "errors": self.errors}

    async def get(
        self,
        patient_id: str,
        ehr_hash: str,
        model: str,
        prompt_version: str = "poc_v4",
    ) -> dict | None:
        key = _build_cache_key(patient_id, ehr_hash, model, prompt_version)

        # L1: Redis
        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    self.hits += 1
                    data = json.loads(raw)
                    data["_from_cache"] = True
                    data["_cache_source"] = "redis"
                    return data
            except Exception as exc:
                logger.warning("Redis GET failed for %s: %s", key, exc)
                self.errors += 1

        # L2: File fallback
        file_path = self._cache_dir / f"{patient_id}_latest.json"
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                self.hits += 1
                data["_from_cache"] = True
                data["_cache_source"] = "file"
                return data
            except Exception:
                pass

        self.misses += 1
        return None

    async def set(
        self,
        patient_id: str,
        ehr_hash: str,
        model: str,
        result: dict,
        prompt_version: str = "poc_v4",
    ) -> None:
        key = _build_cache_key(patient_id, ehr_hash, model, prompt_version)
        serialized = json.dumps(result, ensure_ascii=False)

        # L1: Redis
        if self._redis:
            try:
                await self._redis.set(key, serialized, ex=self.ttl)
            except Exception as exc:
                logger.warning("Redis SET failed for %s: %s", key, exc)
                self.errors += 1

        # L2: File backup (always)
        file_path = self._cache_dir / f"{patient_id}_latest.json"
        file_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    async def invalidate(self, patient_id: str) -> int:
        """Invalidate all cached summaries for a patient."""
        deleted = 0

        if self._redis:
            try:
                keys = []
                async for key in self._redis.scan_iter(f"summary:{patient_id}:*"):
                    keys.append(key)
                if keys:
                    deleted = await self._redis.delete(*keys)
            except Exception as exc:
                logger.warning("Redis invalidate failed for %s: %s", patient_id, exc)

        file_path = self._cache_dir / f"{patient_id}_latest.json"
        if file_path.exists():
            file_path.unlink()
            deleted += 1

        return deleted

    async def invalidate_all(self) -> int:
        """Invalidate all cached summaries."""
        deleted = 0

        if self._redis:
            try:
                keys = []
                async for key in self._redis.scan_iter("summary:*"):
                    keys.append(key)
                if keys:
                    deleted = await self._redis.delete(*keys)
            except Exception as exc:
                logger.warning("Redis invalidate_all failed: %s", exc)

        for f in self._cache_dir.glob("*_latest.json"):
            f.unlink()
            deleted += 1

        return deleted

    async def is_redis_healthy(self) -> bool:
        if not self._redis:
            return False
        try:
            return await self._redis.ping()
        except Exception:
            return False

    async def close(self):
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass
