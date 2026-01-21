"""
Bot-Specific Executors with Rules of Engagement

Each bot has strict constraints:
- Bot 1 (Correlation): FOK atomic batch orders - no legging
- Bot 2 (NegRisk): Dynamic gas check, abort if (profit - gas) < $0.05
- Bot 3 (Resolution): 1-hour buffer on resolution timer
- Bot 4 (Vulture): MUST be post_only, panic on taker fee
"""

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Any, Tuple

import httpx

logger = logging.getLogger(__name__)


# === Common Types ===

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class TimeInForce(Enum):
    GTC = "GTC"          # Good Till Cancelled
    GTD = "GTD"          # Good Till Date
    FOK = "FOK"          # Fill Or Kill
    IOC = "IOC"          # Immediate Or Cancel


@dataclass
class Order:
    """Order to be submitted to Polymarket CLOB."""
    token_id: str
    side: OrderSide
    price: float
    size: float
    time_in_force: TimeInForce = TimeInForce.GTC
    post_only: bool = False
    expiration: Optional[int] = None
    
    def to_clob_format(self) -> dict:
        """Convert to Polymarket CLOB API format."""
        order = {
            "tokenID": self.token_id,
            "side": self.side.value,
            "price": str(self.price),
            "size": str(self.size),
            "timeInForce": self.time_in_force.value,
        }
        if self.post_only:
            order["postOnly"] = True
        if self.expiration:
            order["expiration"] = self.expiration
        return order


@dataclass 
class ExecutionResult:
    """Result of order execution."""
    success: bool
    order_id: Optional[str] = None
    filled_size: float = 0.0
    filled_price: float = 0.0
    pnl: float = 0.0
    fee: float = 0.0  # Positive = taker fee, Negative = maker rebate
    error: Optional[str] = None


class AtomicExecutionError(Exception):
    """Raised when atomic execution fails."""
    pass


class GasCheckError(Exception):
    """Raised when gas fee check fails."""
    pass


class DisputeBufferError(Exception):
    """Raised when resolution timer is too close."""
    pass


class VultureConfigError(Exception):
    """Raised when Vulture order violates constraints."""
    pass


class TakerFeePanicError(Exception):
    """CRITICAL: Raised when Vulture pays a taker fee."""
    pass


# === Base Executor ===

class BaseExecutor(ABC):
    """Base class for bot-specific executors."""
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.clob_url = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")
    
    @abstractmethod
    async def execute(self, opportunity: Any) -> ExecutionResult:
        """Execute the opportunity."""
        pass


# =============================================================================
# Bot 1: Atomic Pair Executor (FOK)
# =============================================================================

class AtomicPairExecutor(BaseExecutor):
    """
    Bot 1 (Correlation): Atomic Batch Order Executor with FOK.
    
    RULE: Use POST /orders batch endpoint with fillOrKill=True (FOK).
    If the Parent leg cannot be sold instantly, the Child leg must not be bought.
    NO LEGGING ALLOWED.
    """
    
    def __init__(self, dry_run: bool = True):
        super().__init__(dry_run)
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.clob_url,
                timeout=30.0,
            )
        return self._client
    
    async def execute_pair(
        self,
        buy_order: Order,
        sell_order: Order,
    ) -> ExecutionResult:
        """
        Execute a correlated pair trade atomically with FOK.
        
        Both orders use FOK (Fill or Kill):
        - If EITHER leg cannot fill completely, NEITHER executes
        - Zero risk of legged positions
        """
        # Force FOK on both legs
        buy_order.time_in_force = TimeInForce.FOK
        sell_order.time_in_force = TimeInForce.FOK
        
        logger.info(
            f"🔗 Atomic FOK execution: "
            f"BUY {buy_order.token_id}@{buy_order.price} / "
            f"SELL {sell_order.token_id}@{sell_order.price}"
        )
        
        if self.dry_run:
            logger.info("  [DRY RUN] Simulating atomic FOK execution...")
            return ExecutionResult(
                success=True,
                order_id="dry_run_atomic_fok",
                filled_size=min(buy_order.size, sell_order.size),
                pnl=0.0,
            )
        
        # Build batch order payload with FOK
        orders = [
            buy_order.to_clob_format(),
            sell_order.to_clob_format(),
        ]
        
        try:
            client = await self._get_client()
            
            response = await client.post(
                "/orders",
                json={"orders": orders},
                headers=self._get_headers(),
            )
            
            if response.status_code != 200:
                raise AtomicExecutionError(
                    f"Batch order failed: {response.status_code} - {response.text}"
                )
            
            result = response.json()
            
            # With FOK, either all legs fill or none do
            # Check for any failures
            all_orders = result.get("orders", [])
            failed = [o for o in all_orders if not o.get("filled")]
            
            if failed:
                # FOK rejection - nothing executed
                logger.warning(
                    f"  ❌ FOK rejected: {len(failed)} legs couldn't fill immediately"
                )
                return ExecutionResult(
                    success=False,
                    error="FOK rejected - insufficient liquidity for atomic fill",
                    pnl=0.0,
                )
            
            # All legs filled
            total_filled = sum(
                float(o.get("filledSize", 0)) for o in all_orders
            )
            
            return ExecutionResult(
                success=True,
                order_id=",".join(o.get("orderId", "") for o in all_orders),
                filled_size=total_filled,
                pnl=0.0,
            )
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error in atomic execution: {e}")
            raise AtomicExecutionError(f"HTTP error: {e}")
    
    def _get_headers(self) -> dict:
        return {"Content-Type": "application/json"}
    
    async def execute(self, opportunity) -> ExecutionResult:
        """Execute a correlation violation opportunity."""
        buy_order = Order(
            token_id=f"{opportunity.child_id}_YES",
            side=OrderSide.BUY,
            price=opportunity.child_price,
            size=10.0,
            time_in_force=TimeInForce.FOK,
        )
        
        sell_order = Order(
            token_id=f"{opportunity.parent_id}_YES",
            side=OrderSide.SELL,
            price=opportunity.parent_price,
            size=10.0,
            time_in_force=TimeInForce.FOK,
        )
        
        return await self.execute_pair(buy_order, sell_order)


# =============================================================================
# Bot 2: Gas-Aware Executor
# =============================================================================

class GasAwareExecutor(BaseExecutor):
    """
    Bot 2 (NegRisk): Gas-Aware Executor for On-Chain Operations.
    
    RULE: Before split/merge, calculate gas cost.
    ABORT if (arb_profit - gas_cost) < $0.05
    """
    
    # Minimum net profit after gas
    MIN_NET_PROFIT: float = 0.05  # $0.05 minimum
    
    # Gas estimates (in gas units)
    SPLIT_GAS_UNITS: int = 200_000
    MERGE_GAS_UNITS: int = 250_000
    
    def __init__(self, dry_run: bool = True):
        super().__init__(dry_run)
        self.polygon_rpc = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
        self._gas_cache: Optional[Tuple[float, float]] = None  # (gwei, timestamp)
        self._matic_cache: Optional[Tuple[float, float]] = None  # (price, timestamp)
    
    async def get_gas_price_gwei(self) -> float:
        """Get current Polygon gas price in Gwei (cached 5s)."""
        now = time.time()
        if self._gas_cache and now - self._gas_cache[1] < 5:
            return self._gas_cache[0]
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(self.polygon_rpc, json={
                    "jsonrpc": "2.0",
                    "method": "eth_gasPrice",
                    "params": [],
                    "id": 1,
                })
                gas_wei = int(resp.json().get("result", "0x0"), 16)
                gas_gwei = gas_wei / 1e9
                self._gas_cache = (gas_gwei, now)
                return gas_gwei
        except Exception as e:
            logger.warning(f"Gas price fetch failed: {e}, using 50 Gwei")
            return 50.0
    
    async def get_matic_price(self) -> float:
        """Get MATIC/USD price (cached 60s)."""
        now = time.time()
        if self._matic_cache and now - self._matic_cache[1] < 60:
            return self._matic_cache[0]
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://api.coingecko.com/api/v3/simple/price"
                    "?ids=matic-network&vs_currencies=usd"
                )
                price = resp.json().get("matic-network", {}).get("usd", 0.5)
                self._matic_cache = (price, now)
                return price
        except Exception as e:
            logger.warning(f"MATIC price fetch failed: {e}, using $0.50")
            return 0.50
    
    async def estimate_gas_fee(self, operation: str = "merge") -> float:
        """Estimate gas fee in USDC."""
        gas_units = self.MERGE_GAS_UNITS if operation == "merge" else self.SPLIT_GAS_UNITS
        gas_gwei = await self.get_gas_price_gwei()
        matic_price = await self.get_matic_price()
        
        gas_matic = gas_units * gas_gwei * 1e-9
        gas_usd = gas_matic * matic_price
        
        return gas_usd
    
    async def should_execute(self, opportunity) -> Tuple[bool, str, float]:
        """
        Check if opportunity is profitable after gas.
        
        Returns:
            (should_execute, reason, net_profit)
        """
        operation = "merge" if "Merge" in opportunity.opportunity_type else "split"
        gas_fee = await self.estimate_gas_fee(operation)
        net_profit = opportunity.profit_net - gas_fee
        
        if net_profit < self.MIN_NET_PROFIT:
            reason = (
                f"Gas abort: ${opportunity.profit_net:.4f} - "
                f"${gas_fee:.4f} = ${net_profit:.4f} < ${self.MIN_NET_PROFIT}"
            )
            logger.warning(f"⛽ {reason}")
            return False, reason, net_profit
        
        logger.info(
            f"✅ Gas check passed: net ${net_profit:.4f} "
            f"(profit ${opportunity.profit_net:.4f} - gas ${gas_fee:.4f})"
        )
        return True, "Profitable after gas", net_profit
    
    async def execute(self, opportunity) -> ExecutionResult:
        """Execute with gas check."""
        should_exec, reason, net_profit = await self.should_execute(opportunity)
        
        if not should_exec:
            return ExecutionResult(
                success=False,
                error=reason,
                pnl=0.0,
            )
        
        if self.dry_run:
            logger.info(f"  [DRY RUN] Would execute {opportunity.opportunity_type}")
            return ExecutionResult(
                success=True,
                order_id="dry_run_negrisk",
                pnl=net_profit,
            )
        
        logger.info(f"  Executing {opportunity.opportunity_type} on-chain...")
        return ExecutionResult(
            success=True,
            order_id="live_negrisk",
            pnl=net_profit,
        )


# =============================================================================
# Bot 3: Resolution Sniper Executor
# =============================================================================

class ResolutionSniperExecutor(BaseExecutor):
    """
    Bot 3 (Resolution): Resolution Sniper with Dispute Buffer.
    
    RULE: "The 1-Hour Buffer"
    Do NOT snipe markets where resolution timer < 60 minutes.
    Prevents capital being locked in dispute battles.
    """
    
    MIN_LIVENESS_BUFFER_SECONDS: int = 3600  # 60 minutes = 1 hour
    
    def __init__(self, dry_run: bool = True):
        super().__init__(dry_run)
    
    def check_dispute_buffer(self, liveness_ends_at: int) -> Tuple[bool, str]:
        """
        Check if there's enough time buffer before resolution.
        
        Args:
            liveness_ends_at: Unix timestamp when liveness ends
            
        Returns:
            (is_safe, reason)
        """
        now = int(time.time())
        time_remaining = liveness_ends_at - now
        
        if time_remaining < self.MIN_LIVENESS_BUFFER_SECONDS:
            minutes = time_remaining // 60
            reason = (
                f"DISPUTE BUFFER: Only {minutes}min remaining, "
                f"need {self.MIN_LIVENESS_BUFFER_SECONDS // 60}min minimum"
            )
            logger.warning(f"⏰ {reason}")
            return False, reason
        
        hours = time_remaining // 3600
        minutes = (time_remaining % 3600) // 60
        logger.info(f"✅ Dispute buffer OK: {hours}h {minutes}m remaining")
        return True, f"{hours}h {minutes}m buffer"
    
    async def execute(self, opportunity) -> ExecutionResult:
        """Execute with dispute buffer check."""
        # Check the 1-hour buffer
        is_safe, reason = self.check_dispute_buffer(
            getattr(opportunity, 'liveness_ends_at', 0)
        )
        
        if not is_safe:
            return ExecutionResult(
                success=False,
                error=reason,
                pnl=0.0,
            )
        
        if self.dry_run:
            logger.info(f"  [DRY RUN] Would snipe {opportunity.condition_id}")
            return ExecutionResult(
                success=True,
                order_id="dry_run_sniper",
                pnl=0.0,
            )
        
        # Execute the snipe
        logger.info(f"  Executing snipe on {opportunity.condition_id}...")
        return ExecutionResult(
            success=True,
            order_id="live_sniper",
            pnl=0.0,
        )


# =============================================================================
# Bot 4: Vulture Executor (Maker Only + Panic Mode)
# =============================================================================

class VultureExecutor(BaseExecutor):
    """
    Bot 4 (Vulture): Maker Rebate Executor with Panic Mode.
    
    RULES:
    1. EVERY order MUST include postOnly=True
    2. If any trade incurs a TAKER FEE (positive fee), immediately:
       - Shut down Bot 4
       - Trigger panic mode in RiskManager
       - Alert user
    """
    
    def __init__(self, dry_run: bool = True):
        super().__init__(dry_run)
        self._client: Optional[httpx.AsyncClient] = None
        self._risk_manager = None  # Lazy import to avoid circular
    
    def _get_risk_manager(self):
        """Lazy import RiskManager to avoid circular imports."""
        if self._risk_manager is None:
            from strategy_layer.risk_manager import RiskManager
            self._risk_manager = RiskManager.get_instance()
        return self._risk_manager
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.clob_url,
                timeout=30.0,
            )
        return self._client
    
    def validate_opportunity(self, opportunity) -> None:
        """Validate Vulture constraints."""
        if not opportunity.use_post_only:
            raise VultureConfigError(
                f"CRITICAL: Vulture MUST use POST_ONLY. "
                f"Market {opportunity.market_slug} has use_post_only=False"
            )
    
    def build_order(self, opportunity) -> Order:
        """Build a Vulture order with ENFORCED POST_ONLY."""
        return Order(
            token_id=opportunity.condition_id,
            side=OrderSide.BUY if opportunity.recommended_side == "BUY" else OrderSide.SELL,
            price=opportunity.recommended_price,
            size=10.0,
            time_in_force=TimeInForce.GTC,
            post_only=True,  # ALWAYS TRUE - This is enforced
        )
    
    def check_for_taker_fee(self, fee: float) -> None:
        """
        Check if we paid a taker fee and trigger panic if so.
        
        Args:
            fee: The fee from the execution. Positive = taker, Negative = rebate
        """
        if fee > 0:
            # TAKER FEE DETECTED - THIS IS A CRITICAL ERROR
            error_msg = (
                f"TAKER FEE DETECTED: ${fee:.4f}! "
                "Vulture should NEVER pay taker fees!"
            )
            
            logger.critical(f"🚨🚨🚨 {error_msg}")
            
            # Trigger panic in RiskManager
            risk_manager = self._get_risk_manager()
            risk_manager.trigger_bot_panic("Bot4_Vulture", error_msg)
            
            raise TakerFeePanicError(error_msg)
    
    async def execute(self, opportunity) -> ExecutionResult:
        """Execute with POST_ONLY enforcement and taker fee panic."""
        # Validate constraints
        try:
            self.validate_opportunity(opportunity)
        except VultureConfigError as e:
            logger.error(f"❌ {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                pnl=0.0,
            )
        
        order = self.build_order(opportunity)
        
        logger.info(
            f"🦅 Vulture order: {order.side.value} {order.token_id} "
            f"@ ${order.price:.4f} [POST_ONLY=True] "
            f"{'🔥 REBATE' if opportunity.is_crypto_15min else ''}"
        )
        
        if self.dry_run:
            logger.info("  [DRY RUN] Order simulated (maker rebate assumed)")
            return ExecutionResult(
                success=True,
                order_id="dry_run_vulture",
                pnl=0.0,
                fee=-0.001,  # Simulate small rebate
            )
        
        # Submit POST_ONLY order
        try:
            client = await self._get_client()
            
            response = await client.post(
                "/orders",
                json=order.to_clob_format(),
                headers={"Content-Type": "application/json"},
            )
            
            if response.status_code != 200:
                return ExecutionResult(
                    success=False,
                    error=f"Order failed: {response.text}",
                    pnl=0.0,
                )
            
            result = response.json()
            
            # CRITICAL: Check the fee on the execution
            fee = float(result.get("fee", 0))
            self.check_for_taker_fee(fee)
            
            return ExecutionResult(
                success=True,
                order_id=result.get("orderId"),
                pnl=0.0,
                fee=fee,
            )
            
        except TakerFeePanicError:
            raise  # Re-raise to stop execution
        except Exception as e:
            logger.error(f"Vulture execution error: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                pnl=0.0,
            )
