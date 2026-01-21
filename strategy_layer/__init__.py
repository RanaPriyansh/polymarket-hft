"""
Polymarket HFT Strategy Layer - Zero-Trust Safety Module

Core Components:
- RiskManager: The Gatekeeper - fat finger, latency, P&L, wallet verification
- RateLimiter: Dual-bucket rate limiter (Market Data + Orders)
- Executors: Bot-specific with Rules of Engagement
"""

from strategy_layer.risk_manager import RiskManager, TradingState, RiskMetrics
from strategy_layer.rate_limiter import RateLimiter, BucketType, RateLimitedClient
from strategy_layer.executors import (
    AtomicPairExecutor,
    GasAwareExecutor,
    ResolutionSniperExecutor,
    VultureExecutor,
    Order,
    OrderSide,
    TimeInForce,
    ExecutionResult,
    TakerFeePanicError,
)

__all__ = [
    # Risk Manager
    "RiskManager",
    "TradingState",
    "RiskMetrics",
    # Rate Limiter
    "RateLimiter", 
    "BucketType",
    "RateLimitedClient",
    # Executors
    "AtomicPairExecutor",
    "GasAwareExecutor",
    "ResolutionSniperExecutor",
    "VultureExecutor",
    "Order",
    "OrderSide",
    "TimeInForce",
    "ExecutionResult",
    "TakerFeePanicError",
]
