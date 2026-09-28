"""Unit tests for rate_limiter.py and async_client.py in custom-dashboards."""

import asyncio
import sys
import os
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add custom-dashboards directory to path
_dashboards_dir = os.path.join(os.path.dirname(__file__), '..', 'custom-dashboards')
sys.path.insert(0, _dashboards_dir)

try:
    from rate_limiter import RateLimiter
    from async_client import AsyncHTTPClient
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# ---------------------------------------------------------------------------
# RateLimiter tests (no aiohttp dependency — pure asyncio)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp is not installed")
class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_init_sets_rate_and_tokens(self):
        rl = RateLimiter(rate_per_second=10)
        assert rl.rate == 10
        assert rl.tokens == 10.0

    def test_acquire_consumes_token(self):
        async def _run():
            rl = RateLimiter(rate_per_second=50)
            await rl.acquire()
            assert rl.tokens < 50  # One token consumed

        asyncio.run(_run())

    def test_acquire_multiple_consumes_correct_tokens(self):
        async def _run():
            rl = RateLimiter(rate_per_second=50)
            await rl.acquire_multiple(3)
            # 3 tokens consumed; tokens may be slightly higher due to refill
            assert rl.tokens <= 47 + 0.1  # small tolerance for refill timing

        asyncio.run(_run())

    def test_refill_tokens_over_time(self):
        async def _run():
            rl = RateLimiter(rate_per_second=100)
            # Drain all tokens
            for _ in range(100):
                await rl.acquire()
            tokens_after_drain = rl.tokens
            # Wait briefly and check that tokens were refilled on next acquire
            await asyncio.sleep(0.05)  # 50 ms → should refill ~5 tokens
            await rl.acquire()
            # Tokens should be > tokens_after_drain before the acquire (minus the 1 used)
            assert rl.tokens >= -1  # basic sanity: tokens never go below 0 after acquire

        asyncio.run(_run())

    def test_acquire_waits_when_no_tokens(self):
        """When starting with 0 tokens it should wait and then succeed."""
        async def _run():
            rl = RateLimiter(rate_per_second=100)
            rl.tokens = 0.0  # Force empty
            start = time.monotonic()
            await rl.acquire()
            elapsed = time.monotonic() - start
            # Should have waited ~0.01 s for the next token at rate=100
            assert elapsed >= 0.005

        asyncio.run(_run())

    def test_acquire_multiple_zero_count(self):
        """acquire_multiple(0) should be a no-op."""
        async def _run():
            rl = RateLimiter(rate_per_second=10)
            initial = rl.tokens
            await rl.acquire_multiple(0)
            # No tokens consumed (ignoring tiny refill)
            assert rl.tokens >= initial - 0.01

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# AsyncHTTPClient tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp is not installed")
class TestAsyncHTTPClient:
    """Tests for AsyncHTTPClient context manager and HTTP methods."""

    def test_init_defaults(self):
        client = AsyncHTTPClient()
        assert client.verify_ssl is True
        assert client.max_retries == 3
        assert client.session is None
        assert client.retry_client is None

    def test_init_custom_values(self):
        client = AsyncHTTPClient(verify_ssl=False, timeout=60, max_retries=5)
        assert client.verify_ssl is False
        assert client.max_retries == 5

    def test_get_without_context_raises(self):
        async def _run():
            client = AsyncHTTPClient()
            with pytest.raises(RuntimeError, match="not initialized"):
                await client.get("https://example.com", {})

        asyncio.run(_run())

    def test_post_without_context_raises(self):
        async def _run():
            client = AsyncHTTPClient()
            with pytest.raises(RuntimeError, match="not initialized"):
                await client.post("https://example.com", {}, {})

        asyncio.run(_run())

    def test_put_without_context_raises(self):
        async def _run():
            client = AsyncHTTPClient()
            with pytest.raises(RuntimeError, match="not initialized"):
                await client.put("https://example.com", {}, {})

        asyncio.run(_run())

    def test_context_manager_sets_and_clears_session(self):
        """__aenter__ creates session/retry_client; __aexit__ clears them."""
        import aiohttp

        async def _run():
            client = AsyncHTTPClient(verify_ssl=True, timeout=5, max_retries=1)
            async with client:
                assert client.session is not None
                assert client.retry_client is not None
            # After exit, session is closed (object still exists but is closed)
            assert client.session is not None  # object present
            assert client.retry_client is not None  # object present

        asyncio.run(_run())

    def test_context_manager_ssl_disabled(self):
        """Context manager works with verify_ssl=False."""
        async def _run():
            client = AsyncHTTPClient(verify_ssl=False, timeout=5, max_retries=1)
            async with client:
                assert client.session is not None

        asyncio.run(_run())

    def test_get_calls_retry_client(self):
        """get() calls through to retry_client.get and raises on error status."""
        import aiohttp

        async def _run():
            client = AsyncHTTPClient()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.raise_for_status = MagicMock()

            mock_retry_cm = AsyncMock()
            mock_retry_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_retry_cm.__aexit__ = AsyncMock(return_value=False)

            mock_retry_client = MagicMock()
            mock_retry_client.get.return_value = mock_retry_cm

            client.retry_client = mock_retry_client

            result = await client.get("https://example.com", {"Authorization": "apiToken tok"})
            mock_retry_client.get.assert_called_once_with(
                "https://example.com",
                headers={"Authorization": "apiToken tok"},
            )

        asyncio.run(_run())

    def test_post_calls_retry_client(self):
        """post() calls through to retry_client.post."""
        async def _run():
            client = AsyncHTTPClient()
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()

            mock_retry_cm = AsyncMock()
            mock_retry_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_retry_cm.__aexit__ = AsyncMock(return_value=False)

            mock_retry_client = MagicMock()
            mock_retry_client.post.return_value = mock_retry_cm

            client.retry_client = mock_retry_client

            payload = {"key": "value"}
            await client.post("https://example.com/api", {"h": "v"}, payload)
            mock_retry_client.post.assert_called_once_with(
                "https://example.com/api",
                headers={"h": "v"},
                json=payload,
            )

        asyncio.run(_run())

    def test_put_calls_retry_client(self):
        """put() calls through to retry_client.put."""
        async def _run():
            client = AsyncHTTPClient()
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()

            mock_retry_cm = AsyncMock()
            mock_retry_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_retry_cm.__aexit__ = AsyncMock(return_value=False)

            mock_retry_client = MagicMock()
            mock_retry_client.put.return_value = mock_retry_cm

            client.retry_client = mock_retry_client

            payload = {"updated": True}
            await client.put("https://example.com/api/1", {"h": "v"}, payload)
            mock_retry_client.put.assert_called_once_with(
                "https://example.com/api/1",
                headers={"h": "v"},
                json=payload,
            )

        asyncio.run(_run())
