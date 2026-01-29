"""Rate limiting utilities for API calls."""

import asyncio
import time
from typing import Optional


class RateLimiter:
    """Token bucket rate limiter for async operations."""
    
    def __init__(self, rate_per_second: int):
        """Initialize the rate limiter.
        
        Args:
            rate_per_second: Maximum number of operations per second
        """
        self.rate = rate_per_second
        self.tokens = float(rate_per_second)
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()
        
    async def _refill_tokens(self):
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_update
        
        # Add tokens based on elapsed time
        self.tokens = min(
            self.rate,
            self.tokens + elapsed * self.rate
        )
        self.last_update = now
        
    async def acquire(self):
        """Acquire a token, waiting if necessary.
        
        This method will block until a token is available.
        """
        async with self.lock:
            await self._refill_tokens()
            
            # Wait until we have at least one token
            while self.tokens < 1:
                # Calculate how long to wait for the next token
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                await self._refill_tokens()
            
            # Consume one token
            self.tokens -= 1
    
    async def acquire_multiple(self, count: int):
        """Acquire multiple tokens at once.
        
        Args:
            count: Number of tokens to acquire
        """
        for _ in range(count):
            await self.acquire()

# Made with Bob
