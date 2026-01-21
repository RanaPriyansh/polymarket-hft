"""
Dual-Bucket Token Rate Limiter for Polymarket API

Implements separate buckets for different API endpoints:
- Bucket A (Market Data): 80 req/10s (20% below limit of 100)
- Bucket B (Orders): 40 req/10s (20% below limit of 50)

Stays 20% below official limits for safety margin.
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class BucketType(Enum):
    """Rate limit bucket types."""
    MARKET_DATA = "market_data"  # Reading orderbooks, prices, etc.
    ORDERS = "orders"            # Placing, canceling, modifying orders


@dataclass
class BucketConfig:
    """Configuration for a single bucket."""
    capacity: int           # Max tokens
    refill_rate: float      # Tokens per second
    official_limit: int     # The actual API limit
    safety_margin: float    # How much below limit we stay (0.2 = 20%)


class TokenBucket:
    """A single token bucket rate limiter."""
    
    def __init__(self, config: BucketConfig, name: str):
        self.name = name
        self.capacity = config.capacity
        self.refill_rate = config.refill_rate
        self.tokens = float(config.capacity)
        self.last_refill = time.time()
        self.lock = threading.Lock()
        
        # Stats
        self.total_requests = 0
        self.total_throttled = 0
        
        logger.debug(
            f"TokenBucket '{name}' initialized: "
            f"capacity={self.capacity}, rate={self.refill_rate}/s"
        )
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens (non-blocking).
        
        Returns:
            True if tokens acquired, False if rate limited
        """
        with self.lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                self.total_requests += 1
                return True
            else:
                self.total_throttled += 1
                return False
    
    async def wait_for_token(self, tokens: int = 1) -> None:
        """Wait until tokens are available (async blocking)."""
        while True:
            if self.acquire(tokens):
                return
            
            # Calculate wait time
            with self.lock:
                tokens_needed = tokens - self.tokens
                wait_time = max(0.1, tokens_needed / self.refill_rate)
            
            await asyncio.sleep(wait_time)
    
    def get_available(self) -> float:
        """Get current available tokens."""
        with self.lock:
            self._refill()
            return self.tokens
    
    def get_stats(self) -> dict:
        """Get bucket statistics."""
        return {
            "name": self.name,
            "available": round(self.get_available(), 1),
            "capacity": self.capacity,
            "refill_rate": self.refill_rate,
            "total_requests": self.total_requests,
            "total_throttled": self.total_throttled,
        }


class RateLimiter:
    """
    Dual-Bucket Rate Limiter for Polymarket API.
    
    Stays 20% below official limits:
    - Market Data: 100 req/10s → 80 req/10s (8/s)
    - Orders: 50 req/10s → 40 req/10s (4/s)
    
    Features:
    - Separate buckets for different endpoint types
    - Exponential backoff on 429 errors
    - Global backoff that affects all buckets
    """
    
    _instance: Optional["RateLimiter"] = None
    _lock = threading.Lock()
    
    # Official limits with 20% safety margin
    BUCKET_CONFIGS: Dict[BucketType, BucketConfig] = {
        BucketType.MARKET_DATA: BucketConfig(
            capacity=80,           # 80 tokens max (20% below 100)
            refill_rate=8.0,       # 8 tokens/second (80/10s)
            official_limit=100,
            safety_margin=0.2,
        ),
        BucketType.ORDERS: BucketConfig(
            capacity=40,           # 40 tokens max (20% below 50)
            refill_rate=4.0,       # 4 tokens/second (40/10s)
            official_limit=50,
            safety_margin=0.2,
        ),
    }
    
    # Backoff configuration
    INITIAL_BACKOFF: float = 30.0
    MAX_BACKOFF: float = 300.0
    BACKOFF_MULTIPLIER: float = 2.0
    
    def __new__(cls) -> "RateLimiter":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # Create buckets
        self._buckets: Dict[BucketType, TokenBucket] = {
            bucket_type: TokenBucket(config, bucket_type.value)
            for bucket_type, config in self.BUCKET_CONFIGS.items()
        }
        
        # Global backoff state (affects all buckets)
        self._backoff_until: float = 0.0
        self._current_backoff: float = 0.0
        self._consecutive_429s: int = 0
        
        logger.info(
            f"🚦 RateLimiter (Dual-Bucket) initialized:\n"
            f"   • Market Data: {self.BUCKET_CONFIGS[BucketType.MARKET_DATA].capacity}/10s "
            f"(official: {self.BUCKET_CONFIGS[BucketType.MARKET_DATA].official_limit})\n"
            f"   • Orders: {self.BUCKET_CONFIGS[BucketType.ORDERS].capacity}/10s "
            f"(official: {self.BUCKET_CONFIGS[BucketType.ORDERS].official_limit})"
        )
    
    @classmethod
    def get_instance(cls) -> "RateLimiter":
        """Get the singleton instance."""
        return cls()
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing only)."""
        with cls._lock:
            cls._instance = None
    
    # =========================================================================
    # BACKOFF MANAGEMENT
    # =========================================================================
    
    def is_in_backoff(self) -> bool:
        """Check if we're in global backoff mode."""
        return time.time() < self._backoff_until
    
    def get_backoff_remaining(self) -> float:
        """Get remaining backoff time in seconds."""
        return max(0, self._backoff_until - time.time())
    
    def handle_429(self, retry_after: Optional[int] = None) -> float:
        """
        Handle a 429 Too Many Requests response.
        
        Args:
            retry_after: Seconds from Retry-After header (if provided)
            
        Returns:
            The duration to wait in seconds
        """
        self._consecutive_429s += 1
        
        # Use Retry-After if provided, otherwise exponential backoff
        if retry_after:
            wait_time = float(retry_after)
        else:
            if self._current_backoff == 0:
                self._current_backoff = self.INITIAL_BACKOFF
            else:
                self._current_backoff = min(
                    self._current_backoff * self.BACKOFF_MULTIPLIER,
                    self.MAX_BACKOFF
                )
            wait_time = self._current_backoff
        
        self._backoff_until = time.time() + wait_time
        
        logger.warning(
            f"🚦 429 Rate Limit (#{self._consecutive_429s}): "
            f"backing off {wait_time:.0f}s"
        )
        
        return wait_time
    
    def reset_backoff(self) -> None:
        """Reset backoff after successful requests."""
        if self._current_backoff > 0 or self._consecutive_429s > 0:
            logger.debug("Backoff reset after successful request")
            self._current_backoff = 0.0
            self._consecutive_429s = 0
    
    # =========================================================================
    # TOKEN ACQUISITION
    # =========================================================================
    
    def acquire(self, bucket_type: BucketType = BucketType.MARKET_DATA, tokens: int = 1) -> bool:
        """
        Try to acquire tokens from a specific bucket (non-blocking).
        
        Args:
            bucket_type: Which bucket to use
            tokens: Number of tokens to acquire
            
        Returns:
            True if acquired, False if rate limited or in backoff
        """
        # Check global backoff first
        if self.is_in_backoff():
            remaining = self.get_backoff_remaining()
            logger.debug(f"In backoff: {remaining:.1f}s remaining")
            return False
        
        return self._buckets[bucket_type].acquire(tokens)
    
    async def wait_for_token(
        self, 
        bucket_type: BucketType = BucketType.MARKET_DATA, 
        tokens: int = 1
    ) -> None:
        """
        Wait until tokens are available (async blocking).
        
        Args:
            bucket_type: Which bucket to use
            tokens: Number of tokens to acquire
        """
        # Wait for backoff to expire
        while self.is_in_backoff():
            wait_time = self.get_backoff_remaining()
            logger.info(f"⏳ Waiting {wait_time:.1f}s for backoff to expire")
            await asyncio.sleep(min(wait_time, 1.0))  # Check every second
        
        # Wait for bucket
        await self._buckets[bucket_type].wait_for_token(tokens)
    
    # Convenience methods
    async def wait_for_market_data(self, tokens: int = 1) -> None:
        """Wait for market data rate limit."""
        await self.wait_for_token(BucketType.MARKET_DATA, tokens)
    
    async def wait_for_order(self, tokens: int = 1) -> None:
        """Wait for order rate limit."""
        await self.wait_for_token(BucketType.ORDERS, tokens)
    
    def acquire_market_data(self, tokens: int = 1) -> bool:
        """Try to acquire market data tokens."""
        return self.acquire(BucketType.MARKET_DATA, tokens)
    
    def acquire_order(self, tokens: int = 1) -> bool:
        """Try to acquire order tokens."""
        return self.acquire(BucketType.ORDERS, tokens)
    
    # =========================================================================
    # STATUS
    # =========================================================================
    
    def get_status(self) -> dict:
        """Get rate limiter status."""
        return {
            "in_backoff": self.is_in_backoff(),
            "backoff_remaining": round(self.get_backoff_remaining(), 1),
            "consecutive_429s": self._consecutive_429s,
            "buckets": {
                bucket_type.value: bucket.get_stats()
                for bucket_type, bucket in self._buckets.items()
            },
        }
    
    def get_total_requests(self) -> int:
        """Get total requests across all buckets."""
        return sum(b.total_requests for b in self._buckets.values())
    
    def get_total_throttled(self) -> int:
        """Get total throttled requests across all buckets."""
        return sum(b.total_throttled for b in self._buckets.values())
    
    def __repr__(self) -> str:
        md = self._buckets[BucketType.MARKET_DATA]
        orders = self._buckets[BucketType.ORDERS]
        return (
            f"RateLimiter("
            f"data={md.get_available():.0f}/{md.capacity}, "
            f"orders={orders.get_available():.0f}/{orders.capacity}, "
            f"backoff={self.get_backoff_remaining():.0f}s)"
        )


class RateLimitedClient:
    """
    Wrapper to add rate limiting to any async HTTP client.
    
    Automatically routes requests to appropriate buckets based on endpoint.
    """
    
    ORDER_ENDPOINTS = ["/orders", "/cancel", "/trade"]
    
    def __init__(self, client, rate_limiter: Optional[RateLimiter] = None):
        self._client = client
        self._rate_limiter = rate_limiter or RateLimiter.get_instance()
    
    def _get_bucket_type(self, url: str) -> BucketType:
        """Determine bucket type based on URL."""
        for endpoint in self.ORDER_ENDPOINTS:
            if endpoint in url.lower():
                return BucketType.ORDERS
        return BucketType.MARKET_DATA
    
    async def request(self, method: str, url: str, **kwargs) -> any:
        """Make a rate-limited request."""
        bucket_type = self._get_bucket_type(url)
        
        # Wait for token
        await self._rate_limiter.wait_for_token(bucket_type)
        
        try:
            response = await self._client.request(method, url, **kwargs)
            
            # Handle 429 responses
            if hasattr(response, 'status_code') and response.status_code == 429:
                # Check for Retry-After header
                retry_after = response.headers.get('Retry-After')
                wait_time = self._rate_limiter.handle_429(
                    int(retry_after) if retry_after else None
                )
                await asyncio.sleep(wait_time)
                return await self.request(method, url, **kwargs)
            
            # Success - reset backoff
            self._rate_limiter.reset_backoff()
            return response
            
        except Exception as e:
            if "429" in str(e):
                wait_time = self._rate_limiter.handle_429()
                await asyncio.sleep(wait_time)
                return await self.request(method, url, **kwargs)
            raise
    
    async def get(self, url: str, **kwargs) -> any:
        return await self.request("GET", url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> any:
        return await self.request("POST", url, **kwargs)
    
    async def delete(self, url: str, **kwargs) -> any:
        return await self.request("DELETE", url, **kwargs)
