"""Tests for Redis summary cache with file fallback."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cache.redis_cache import SummaryCache, compute_ehr_hash, _build_cache_key


# ---------------------------------------------------------------------------
# compute_ehr_hash
# ---------------------------------------------------------------------------


class TestComputeEhrHash:
    def test_same_data_same_hash(self):
        data = {"patient_id": "P001", "encounters": []}
        assert compute_ehr_hash(data) == compute_ehr_hash(data)

    def test_different_data_different_hash(self):
        d1 = {"patient_id": "P001"}
        d2 = {"patient_id": "P002"}
        assert compute_ehr_hash(d1) != compute_ehr_hash(d2)

    def test_hash_is_12_chars(self):
        h = compute_ehr_hash({"test": True})
        assert len(h) == 12

    def test_key_order_independent(self):
        d1 = {"a": 1, "b": 2}
        d2 = {"b": 2, "a": 1}
        assert compute_ehr_hash(d1) == compute_ehr_hash(d2)


# ---------------------------------------------------------------------------
# _build_cache_key
# ---------------------------------------------------------------------------


class TestBuildCacheKey:
    def test_key_format(self):
        key = _build_cache_key("P001", "abc123", "gpt-4o-mini")
        assert key == "summary:P001:abc123:gpt-4o-mini:poc_v4"

    def test_key_changes_with_model(self):
        k1 = _build_cache_key("P001", "abc", "gpt-4o-mini")
        k2 = _build_cache_key("P001", "abc", "gpt-4o")
        assert k1 != k2

    def test_key_changes_with_hash(self):
        k1 = _build_cache_key("P001", "aaa", "model")
        k2 = _build_cache_key("P001", "bbb", "model")
        assert k1 != k2

    def test_key_changes_with_prompt_version(self):
        k1 = _build_cache_key("P001", "abc", "model", "v1")
        k2 = _build_cache_key("P001", "abc", "model", "v2")
        assert k1 != k2


# ---------------------------------------------------------------------------
# SummaryCache — file-only (no Redis)
# ---------------------------------------------------------------------------


class TestSummaryCacheFileOnly:
    """Test file fallback when Redis is unavailable."""

    @pytest.fixture
    def cache(self, tmp_path):
        with patch("src.cache.redis_cache._get_redis_client", return_value=None):
            yield SummaryCache(cache_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_miss_returns_none(self, cache):
        result = await cache.get("P001", "hash1", "model1")
        assert result is None
        assert cache.misses == 1

    @pytest.mark.asyncio
    async def test_set_then_get_from_file(self, cache):
        data = {"patient_id": "P001", "sections": []}
        await cache.set("P001", "hash1", "model1", data)

        result = await cache.get("P001", "hash1", "model1")
        assert result is not None
        assert result["patient_id"] == "P001"
        assert result["_from_cache"] is True
        assert result["_cache_source"] == "file"

    @pytest.mark.asyncio
    async def test_invalidate_deletes_file(self, cache):
        data = {"patient_id": "P001"}
        await cache.set("P001", "hash1", "model1", data)

        deleted = await cache.invalidate("P001")
        assert deleted >= 1

        result = await cache.get("P001", "hash1", "model1")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_all(self, cache):
        await cache.set("P001", "h1", "m", {"id": "P001"})
        await cache.set("P002", "h2", "m", {"id": "P002"})

        deleted = await cache.invalidate_all()
        assert deleted >= 2

    @pytest.mark.asyncio
    async def test_redis_down_reports_not_healthy(self, cache):
        assert await cache.is_redis_healthy() is False

    @pytest.mark.asyncio
    async def test_stats_tracking(self, cache):
        await cache.get("P001", "h1", "m")  # miss
        await cache.set("P001", "h1", "m", {"x": 1})
        await cache.get("P001", "h1", "m")  # hit

        stats = cache.stats
        assert stats["misses"] == 1
        assert stats["hits"] == 1
        assert stats["errors"] == 0


# ---------------------------------------------------------------------------
# SummaryCache — with mocked Redis
# ---------------------------------------------------------------------------


class TestSummaryCacheWithRedis:
    """Test Redis cache behavior with mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        redis.delete = AsyncMock(return_value=1)
        redis.ping = AsyncMock(return_value=True)
        redis.close = AsyncMock()

        async def _scan_iter(pattern):
            return
            yield  # make it an async generator

        redis.scan_iter = _scan_iter
        return redis

    @pytest.fixture
    def cache(self, mock_redis, tmp_path):
        with patch("src.cache.redis_cache._get_redis_client", return_value=mock_redis):
            yield SummaryCache(cache_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_cache_hit_from_redis(self, cache, mock_redis):
        cached_data = json.dumps({"patient_id": "P001", "sections": []})
        mock_redis.get = AsyncMock(return_value=cached_data)

        result = await cache.get("P001", "hash1", "model1")
        assert result is not None
        assert result["_from_cache"] is True
        assert result["_cache_source"] == "redis"
        assert cache.hits == 1

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)

        result = await cache.get("P001", "hash1", "model1")
        assert result is None
        assert cache.misses == 1

    @pytest.mark.asyncio
    async def test_set_writes_to_redis_and_file(self, cache, mock_redis, tmp_path):
        data = {"patient_id": "P001"}
        await cache.set("P001", "hash1", "model1", data)

        mock_redis.set.assert_called_once()
        assert (tmp_path / "P001_latest.json").exists()

    @pytest.mark.asyncio
    async def test_redis_error_falls_back_to_file(self, cache, mock_redis, tmp_path):
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))

        file_data = {"patient_id": "P001", "cached": True}
        (tmp_path / "P001_latest.json").write_text(
            json.dumps(file_data), encoding="utf-8"
        )

        result = await cache.get("P001", "hash1", "model1")
        assert result is not None
        assert result["_cache_source"] == "file"
        assert cache.errors == 1

    @pytest.mark.asyncio
    async def test_redis_healthy(self, cache, mock_redis):
        assert await cache.is_redis_healthy() is True

    @pytest.mark.asyncio
    async def test_redis_unhealthy_on_error(self, cache, mock_redis):
        mock_redis.ping = AsyncMock(side_effect=ConnectionError())
        assert await cache.is_redis_healthy() is False

    @pytest.mark.asyncio
    async def test_cache_key_changes_when_model_changes(self, cache, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)

        await cache.get("P001", "hash1", "gpt-4o-mini")
        await cache.get("P001", "hash1", "gpt-4o")

        calls = mock_redis.get.call_args_list
        assert calls[0][0][0] != calls[1][0][0]

    @pytest.mark.asyncio
    async def test_set_uses_ttl(self, cache, mock_redis):
        await cache.set("P001", "h1", "m", {"x": 1})
        call_kwargs = mock_redis.set.call_args
        assert call_kwargs.kwargs.get("ex") == 86400 or call_kwargs[1].get("ex") == 86400

    @pytest.mark.asyncio
    async def test_close(self, cache, mock_redis):
        await cache.close()
        mock_redis.close.assert_called_once()
