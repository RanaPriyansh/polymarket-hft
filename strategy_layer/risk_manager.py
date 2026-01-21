"""
Zero-Trust Safety Module - Global Risk Manager

The Gatekeeper: No bot can execute a trade without passing through here.

Enforces:
- Daily Drawdown Limit: Hard stop if loss > $50.00 in 24h
- Max Position Size: Cap any single order at $20.00
- Fat Finger Protection: Reject orders >10% from best bid/ask
- API Error Kill Switch: 5 errors (429/500/502) in 60s → 10-min pause
- Latency Guard: Pause HFT bots if API latency > 500ms
"""

import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Tuple

import httpx

logger = logging.getLogger(__name__)


class TradingState(Enum):
    """Trading state enumeration."""
    ACTIVE = "active"
    PAUSED_ERROR_RATE = "paused_error_rate"
    PAUSED_LATENCY = "paused_latency"
    PAUSED_WALLET = "paused_wallet"
    STOPPED_PNL_LIMIT = "stopped_pnl_limit"
    STOPPED_MANUAL = "stopped_manual"
    STOPPED_BOT_PANIC = "stopped_bot_panic"


class ErrorType(Enum):
    """HTTP error types that trigger kill switch."""
    RATE_LIMIT = 429
    SERVER_ERROR = 500
    BAD_GATEWAY = 502
    FORBIDDEN = 403


@dataclass
class RiskMetrics:
    """Current risk metrics snapshot."""
    daily_pnl: float = 0.0
    error_count_last_60s: int = 0
    total_orders_today: int = 0
    total_volume_today: float = 0.0
    trading_state: TradingState = TradingState.ACTIVE
    kill_switch_ends_at: Optional[float] = None
    api_latency_ms: float = 0.0
    wallet_matic: float = 0.0
    wallet_usdc: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "daily_pnl": round(self.daily_pnl, 4),
            "error_count_last_60s": self.error_count_last_60s,
            "total_orders_today": self.total_orders_today,
            "total_volume_today": round(self.total_volume_today, 2),
            "trading_state": self.trading_state.value,
            "kill_switch_ends_at": self.kill_switch_ends_at,
            "api_latency_ms": round(self.api_latency_ms, 1),
            "wallet_matic": round(self.wallet_matic, 4),
            "wallet_usdc": round(self.wallet_usdc, 2),
        }


class RiskManager:
    """
    Zero-Trust Safety Module - The Gatekeeper.
    
    Singleton Risk Manager for Pre-Production Trading.
    Every trade MUST pass through this gatekeeper.
    
    Hard Limits:
    - MAX_DAILY_LOSS: Hard stop trading if cumulative loss > $50.00
    - MAX_ORDER_SIZE: Cap any single order at $20.00 USDC
    - FAT_FINGER_THRESHOLD: Reject orders >10% from best bid/ask
    - MAX_LATENCY_MS: Pause HFT bots if API latency > 500ms
    - ERROR_THRESHOLD: If >5 API errors (429/500/502) in 60s, trigger 10-min kill switch
    """
    
    _instance: Optional["RiskManager"] = None
    _lock = threading.Lock()
    
    # === HARD LIMITS (Pre-Production) ===
    MAX_DAILY_LOSS: float = 50.0           # Hard stop at $50 loss
    MAX_ORDER_SIZE: float = 20.0           # Cap single orders at $20 USDC
    FAT_FINGER_THRESHOLD: float = 0.10     # 10% deviation from market
    MAX_LATENCY_MS: float = 500.0          # Max acceptable API latency
    LATENCY_CHECK_INTERVAL: int = 30       # Ping API every 30 seconds
    ERROR_WINDOW_SECONDS: int = 60         # Error window for rate limiting
    MAX_ERRORS_PER_WINDOW: int = 5         # Max errors before kill switch
    KILL_SWITCH_DURATION: int = 600        # 10 minutes (600 seconds)
    
    # Wallet minimums for trading
    MIN_MATIC_BALANCE: float = 1.0         # Minimum 1.0 MATIC for gas
    MIN_USDC_BALANCE: float = 50.0         # Minimum $50 USDC for trading
    
    def __new__(cls) -> "RiskManager":
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
        self._daily_pnl: float = 0.0
        self._error_timestamps: list[Tuple[float, int]] = []  # (timestamp, error_code)
        self._total_orders: int = 0
        self._total_volume: float = 0.0
        self._trading_state: TradingState = TradingState.ACTIVE
        self._kill_switch_ends_at: Optional[float] = None
        self._manual_stop: bool = False
        self._pnl_lock = threading.Lock()
        self._error_lock = threading.Lock()
        
        # Latency monitoring
        self._api_latency_ms: float = 0.0
        self._latency_healthy: bool = True
        self._last_latency_check: float = 0.0
        
        # Wallet balances
        self._wallet_matic: float = 0.0
        self._wallet_usdc: float = 0.0
        self._wallet_verified: bool = False
        
        # Bot-specific panic states
        self._bot_panic_states: Dict[str, bool] = {}
        
        # API endpoints
        self._clob_url = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")
        self._polygon_rpc = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
        
        logger.info(
            f"🔒 RiskManager (Zero-Trust) initialized:\n"
            f"   • MAX_DAILY_LOSS: ${self.MAX_DAILY_LOSS}\n"
            f"   • MAX_ORDER_SIZE: ${self.MAX_ORDER_SIZE}\n"
            f"   • FAT_FINGER_THRESHOLD: {self.FAT_FINGER_THRESHOLD*100}%\n"
            f"   • MAX_LATENCY_MS: {self.MAX_LATENCY_MS}ms\n"
            f"   • KILL_SWITCH: {self.KILL_SWITCH_DURATION//60}min"
        )
    
    @classmethod
    def get_instance(cls) -> "RiskManager":
        """Get the singleton instance."""
        return cls()
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing only)."""
        with cls._lock:
            cls._instance = None
    
    # =========================================================================
    # WALLET VERIFICATION
    # =========================================================================
    
    async def verify_wallet(self) -> Tuple[bool, str]:
        """
        Verify wallet has sufficient balances to trade.
        
        Requirements:
        - MATIC balance > 1.0 (for gas)
        - USDC balance > $50.00 (for trading)
        
        Returns:
            Tuple of (success, message)
        """
        wallet_address = os.getenv("WALLET_ADDRESS", "")
        if not wallet_address:
            return False, "WALLET_ADDRESS not configured"
        
        logger.info(f"🔍 Verifying wallet {wallet_address[:10]}...")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Check MATIC balance
                resp = await client.post(self._polygon_rpc, json={
                    "jsonrpc": "2.0",
                    "method": "eth_getBalance",
                    "params": [wallet_address, "latest"],
                    "id": 1
                })
                result = resp.json()
                if "result" in result:
                    matic_wei = int(result["result"], 16)
                    self._wallet_matic = matic_wei / 1e18
                else:
                    self._wallet_matic = 0.0
                
                # Check USDC balance (Polygon USDC contract)
                usdc_contract = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
                # balanceOf(address) selector: 0x70a08231
                data = f"0x70a08231000000000000000000000000{wallet_address[2:]}"
                
                resp = await client.post(self._polygon_rpc, json={
                    "jsonrpc": "2.0",
                    "method": "eth_call",
                    "params": [{"to": usdc_contract, "data": data}, "latest"],
                    "id": 2
                })
                result = resp.json()
                if "result" in result and result["result"] != "0x":
                    usdc_raw = int(result["result"], 16)
                    self._wallet_usdc = usdc_raw / 1e6  # USDC has 6 decimals
                else:
                    self._wallet_usdc = 0.0
            
            logger.info(f"   • MATIC: {self._wallet_matic:.4f}")
            logger.info(f"   • USDC: ${self._wallet_usdc:.2f}")
            
            # Validate minimums
            issues = []
            if self._wallet_matic < self.MIN_MATIC_BALANCE:
                issues.append(f"MATIC {self._wallet_matic:.4f} < {self.MIN_MATIC_BALANCE}")
            if self._wallet_usdc < self.MIN_USDC_BALANCE:
                issues.append(f"USDC ${self._wallet_usdc:.2f} < ${self.MIN_USDC_BALANCE}")
            
            if issues:
                self._wallet_verified = False
                self._trading_state = TradingState.PAUSED_WALLET
                msg = f"Wallet insufficient: {', '.join(issues)}"
                logger.error(f"❌ {msg}")
                return False, msg
            
            self._wallet_verified = True
            logger.info("✅ Wallet verification passed")
            return True, "Wallet verified"
            
        except Exception as e:
            logger.error(f"❌ Wallet verification failed: {e}")
            return False, str(e)
    
    # =========================================================================
    # LATENCY GUARD
    # =========================================================================
    
    async def check_api_latency(self) -> Tuple[float, bool]:
        """
        Ping Polymarket API and measure latency.
        
        Returns:
            Tuple of (latency_ms, is_healthy)
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                start = time.time()
                resp = await client.get(f"{self._clob_url}/")
                latency_ms = (time.time() - start) * 1000
                
                self._api_latency_ms = latency_ms
                self._last_latency_check = time.time()
                
                if latency_ms > self.MAX_LATENCY_MS:
                    if self._latency_healthy:  # Was healthy, now degraded
                        logger.warning(
                            f"⚠️ API latency degraded: {latency_ms:.0f}ms > "
                            f"{self.MAX_LATENCY_MS}ms threshold"
                        )
                    self._latency_healthy = False
                else:
                    if not self._latency_healthy:  # Was degraded, now healthy
                        logger.info(f"✅ API latency recovered: {latency_ms:.0f}ms")
                    self._latency_healthy = True
                
                return latency_ms, self._latency_healthy
                
        except Exception as e:
            logger.error(f"❌ API latency check failed: {e}")
            self._latency_healthy = False
            return 9999.0, False
    
    def is_latency_healthy(self) -> bool:
        """Check if API latency is acceptable for HFT bots."""
        return self._latency_healthy
    
    def should_check_latency(self) -> bool:
        """Check if it's time to ping the API."""
        return time.time() - self._last_latency_check > self.LATENCY_CHECK_INTERVAL
    
    # =========================================================================
    # FAT FINGER PROTECTION
    # =========================================================================
    
    def check_fat_finger(
        self, 
        order_price: float, 
        best_bid: float, 
        best_ask: float, 
        side: str
    ) -> Tuple[bool, str]:
        """
        Fat Finger Protection: Reject orders too far from market.
        
        - BUY orders: Reject if price > best_ask * (1 + threshold)
        - SELL orders: Reject if price < best_bid * (1 - threshold)
        
        Args:
            order_price: The order price
            best_bid: Current best bid
            best_ask: Current best ask
            side: "BUY" or "SELL"
            
        Returns:
            Tuple of (is_valid, reason)
        """
        if side.upper() == "BUY":
            max_price = best_ask * (1 + self.FAT_FINGER_THRESHOLD)
            if order_price > max_price:
                reason = (
                    f"FAT FINGER: BUY @ ${order_price:.4f} > "
                    f"10% above ask ${best_ask:.4f} (max: ${max_price:.4f})"
                )
                logger.warning(f"🖐️ {reason}")
                return False, reason
                
        elif side.upper() == "SELL":
            min_price = best_bid * (1 - self.FAT_FINGER_THRESHOLD)
            if order_price < min_price:
                reason = (
                    f"FAT FINGER: SELL @ ${order_price:.4f} < "
                    f"10% below bid ${best_bid:.4f} (min: ${min_price:.4f})"
                )
                logger.warning(f"🖐️ {reason}")
                return False, reason
        
        return True, "Price within acceptable range"
    
    # =========================================================================
    # CORE TRADING CHECKS
    # =========================================================================
    
    def is_trading_allowed(self) -> bool:
        """
        Master check: Is trading currently allowed?
        
        Returns False if:
        - Wallet not verified or insufficient funds
        - Daily P&L loss exceeds MAX_DAILY_LOSS
        - Kill switch is active (error rate exceeded)
        - Manual stop has been triggered
        - Any bot is in panic mode
        """
        # Check wallet verification
        if not self._wallet_verified:
            self._trading_state = TradingState.PAUSED_WALLET
            return False
        
        # Check manual stop
        if self._manual_stop:
            self._trading_state = TradingState.STOPPED_MANUAL
            return False
        
        # Check bot panic states
        if any(self._bot_panic_states.values()):
            self._trading_state = TradingState.STOPPED_BOT_PANIC
            panicked = [b for b, p in self._bot_panic_states.items() if p]
            logger.critical(f"🚨 Bots in panic mode: {panicked}")
            return False
        
        # Check P&L limit
        if self._daily_pnl <= -self.MAX_DAILY_LOSS:
            self._trading_state = TradingState.STOPPED_PNL_LIMIT
            logger.critical(
                f"🛑 TRADING HALTED: Daily loss ${abs(self._daily_pnl):.2f} "
                f"exceeds limit ${self.MAX_DAILY_LOSS:.2f}"
            )
            return False
        
        # Check kill switch
        if self._kill_switch_ends_at is not None:
            if time.time() < self._kill_switch_ends_at:
                self._trading_state = TradingState.PAUSED_ERROR_RATE
                remaining = int(self._kill_switch_ends_at - time.time())
                logger.warning(f"⏸️ Kill switch active: {remaining}s remaining")
                return False
            else:
                # Kill switch expired, resume trading
                self._kill_switch_ends_at = None
                logger.info("✅ Kill switch expired, resuming trading")
        
        self._trading_state = TradingState.ACTIVE
        return True
    
    def is_hft_allowed(self) -> bool:
        """
        Check if HFT bots (Bot 1 & 4) should be active.
        
        HFT bots require low latency. If latency is degraded,
        they should pause while other bots can continue.
        """
        if not self.is_trading_allowed():
            return False
        
        if not self._latency_healthy:
            logger.warning(
                f"⏸️ HFT paused: latency {self._api_latency_ms:.0f}ms > "
                f"{self.MAX_LATENCY_MS}ms"
            )
            return False
        
        return True
    
    def check_order(
        self, 
        size_usdc: float,
        order_price: Optional[float] = None,
        best_bid: Optional[float] = None,
        best_ask: Optional[float] = None,
        side: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Validate an order before execution.
        
        Checks:
        1. Trading is allowed
        2. Order size within limits
        3. Fat finger protection (if market data provided)
        
        Returns:
            Tuple of (is_valid, reason)
        """
        if not self.is_trading_allowed():
            return False, f"Trading not allowed: {self._trading_state.value}"
        
        if size_usdc > self.MAX_ORDER_SIZE:
            reason = f"Order ${size_usdc:.2f} > max ${self.MAX_ORDER_SIZE:.2f}"
            logger.warning(f"❌ {reason}")
            return False, reason
        
        if size_usdc <= 0:
            return False, f"Invalid order size: ${size_usdc:.2f}"
        
        # Fat finger check if market data provided
        if all([order_price, best_bid, best_ask, side]):
            valid, reason = self.check_fat_finger(order_price, best_bid, best_ask, side)
            if not valid:
                return False, reason
        
        return True, "Order validated"
    
    # =========================================================================
    # GAS GUARD (Bot 2 - NegRisk Specific)
    # =========================================================================
    
    MIN_NET_PROFIT_THRESHOLD: float = 0.05  # $0.05 minimum net profit
    
    def check_gas_guard(
        self,
        projected_profit: float,
        gas_cost: float,
        min_profit: float = 0.05,
    ) -> Tuple[bool, str]:
        """
        Gas Guard for Bot 2 (NegRisk) trades.
        
        Before executing a NegRisk arbitrage:
        1. Calculate net profit = projected_profit - gas_cost
        2. Reject if net profit < min_profit threshold
        
        Args:
            projected_profit: Expected profit from the arbitrage in USDC
            gas_cost: Current gas cost in USDC for the operation
            min_profit: Minimum acceptable net profit (default $0.05)
            
        Returns:
            Tuple of (is_approved, reason)
        """
        net_profit = projected_profit - gas_cost
        
        if net_profit < min_profit:
            reason = (
                f"Gas Guard REJECT: Net profit ${net_profit:.3f} < "
                f"min ${min_profit:.2f} (Profit ${projected_profit:.3f} - Gas ${gas_cost:.3f})"
            )
            logger.warning(f"⛽ {reason}")
            return False, reason
        
        logger.debug(
            f"⛽ Gas Guard PASS: Net ${net_profit:.3f} "
            f"(Profit ${projected_profit:.3f} - Gas ${gas_cost:.3f})"
        )
        return True, f"Net profit ${net_profit:.3f} meets threshold"
    
    # =========================================================================
    # P&L TRACKING
    # =========================================================================
    
    def record_pnl(self, amount: float) -> None:
        """Record a P&L event (profit or loss)."""
        with self._pnl_lock:
            self._daily_pnl += amount
            
            if amount >= 0:
                logger.info(f"💰 P&L: +${amount:.4f} (Daily: ${self._daily_pnl:.2f})")
            else:
                logger.warning(f"📉 P&L: -${abs(amount):.4f} (Daily: ${self._daily_pnl:.2f})")
            
            if self._daily_pnl <= -self.MAX_DAILY_LOSS:
                logger.critical(
                    f"🛑 DAILY LOSS LIMIT HIT: ${abs(self._daily_pnl):.2f} - "
                    f"ALL TRADING STOPPED"
                )
    
    def record_order(self, size_usdc: float) -> None:
        """Record an executed order for tracking."""
        with self._pnl_lock:
            self._total_orders += 1
            self._total_volume += size_usdc
    
    def get_daily_pnl(self) -> float:
        """Get current daily P&L."""
        return self._daily_pnl
    
    def reset_daily_pnl(self) -> None:
        """Reset daily P&L (call at start of each trading day)."""
        with self._pnl_lock:
            old_pnl = self._daily_pnl
            self._daily_pnl = 0.0
            self._total_orders = 0
            self._total_volume = 0.0
            logger.info(f"📊 Daily P&L reset. Previous: ${old_pnl:.2f}")
            
            if self._trading_state == TradingState.STOPPED_PNL_LIMIT:
                self._trading_state = TradingState.ACTIVE
    
    # =========================================================================
    # ERROR HANDLING - SPECIFIC 429/500/502/403
    # =========================================================================
    
    def record_error(self, status_code: int = 500) -> None:
        """
        Record an API error with specific handling.
        
        - 429 (Rate Limit): Counts toward kill switch
        - 500/502 (Server Error): Counts toward kill switch
        - 403 (Forbidden): May indicate API key issues, immediate alert
        """
        current_time = time.time()
        
        with self._error_lock:
            # Handle 403 specially - this is a critical auth issue
            if status_code == 403:
                logger.critical(
                    "🚨 403 FORBIDDEN: API key may be invalid or revoked! "
                    "Check POLY_API_KEY, POLY_API_SECRET, POLY_API_PASSPHRASE"
                )
                self._manual_stop = True
                self._trading_state = TradingState.STOPPED_MANUAL
                return
            
            # Record error for kill switch calculation (429, 500, 502)
            if status_code in [429, 500, 502]:
                self._error_timestamps.append((current_time, status_code))
                
                # Remove errors outside the window
                cutoff = current_time - self.ERROR_WINDOW_SECONDS
                self._error_timestamps = [
                    (ts, code) for ts, code in self._error_timestamps if ts > cutoff
                ]
                
                error_count = len(self._error_timestamps)
                error_codes = [code for _, code in self._error_timestamps]
                
                logger.warning(
                    f"⚠️ API error {status_code}: {error_count}/{self.MAX_ERRORS_PER_WINDOW} "
                    f"in {self.ERROR_WINDOW_SECONDS}s (codes: {error_codes})"
                )
                
                if error_count >= self.MAX_ERRORS_PER_WINDOW:
                    self._trigger_kill_switch()
    
    def handle_rate_limit(self, retry_after: Optional[int] = None) -> float:
        """
        Handle 429 Rate Limit response.
        
        Args:
            retry_after: Seconds from Retry-After header (if provided)
            
        Returns:
            Recommended wait time in seconds
        """
        self.record_error(429)
        
        # Use Retry-After header if provided, otherwise default
        wait_time = retry_after if retry_after else 30.0
        
        logger.warning(
            f"🚦 Rate limit hit (429): waiting {wait_time}s "
            f"(Retry-After: {retry_after})"
        )
        
        return wait_time
    
    def _trigger_kill_switch(self) -> None:
        """Activate the kill switch for KILL_SWITCH_DURATION seconds."""
        self._kill_switch_ends_at = time.time() + self.KILL_SWITCH_DURATION
        self._trading_state = TradingState.PAUSED_ERROR_RATE
        
        logger.critical(
            f"🚨 KILL SWITCH ACTIVATED: Too many API errors! "
            f"Trading paused for {self.KILL_SWITCH_DURATION // 60} minutes."
        )
    
    def get_error_count(self) -> int:
        """Get current error count in the window."""
        current_time = time.time()
        cutoff = current_time - self.ERROR_WINDOW_SECONDS
        
        with self._error_lock:
            return len([ts for ts, _ in self._error_timestamps if ts > cutoff])
    
    # =========================================================================
    # BOT PANIC MODE
    # =========================================================================
    
    def trigger_bot_panic(self, bot_name: str, reason: str) -> None:
        """
        Trigger panic mode for a specific bot.
        
        This immediately stops ALL trading and requires manual intervention.
        Used for critical safety violations (e.g., Vulture paying taker fees).
        """
        self._bot_panic_states[bot_name] = True
        self._trading_state = TradingState.STOPPED_BOT_PANIC
        
        logger.critical(
            f"🚨🚨🚨 BOT PANIC: {bot_name}\n"
            f"   Reason: {reason}\n"
            f"   ALL TRADING STOPPED - Manual intervention required!"
        )
    
    def clear_bot_panic(self, bot_name: str) -> None:
        """Clear panic state for a bot after manual review."""
        if bot_name in self._bot_panic_states:
            self._bot_panic_states[bot_name] = False
            logger.info(f"✅ Panic cleared for {bot_name}")
    
    def clear_all_panics(self) -> None:
        """Clear all bot panic states."""
        self._bot_panic_states = {}
        logger.info("✅ All bot panics cleared")
    
    # =========================================================================
    # MANUAL CONTROLS
    # =========================================================================
    
    def stop_trading(self) -> None:
        """Manually stop all trading."""
        self._manual_stop = True
        self._trading_state = TradingState.STOPPED_MANUAL
        logger.critical("🛑 MANUAL STOP: Trading halted by operator")
    
    def resume_trading(self) -> None:
        """Resume trading after manual stop."""
        self._manual_stop = False
        self._kill_switch_ends_at = None
        self.clear_all_panics()
        logger.info("✅ Trading resumed by operator")
    
    # =========================================================================
    # STATUS & METRICS
    # =========================================================================
    
    def get_status(self) -> dict:
        """Get complete risk manager status."""
        return {
            "trading_allowed": self.is_trading_allowed(),
            "hft_allowed": self.is_hft_allowed(),
            "trading_state": self._trading_state.value,
            "daily_pnl": round(self._daily_pnl, 2),
            "pnl_limit": self.MAX_DAILY_LOSS,
            "pnl_remaining": round(self.MAX_DAILY_LOSS + self._daily_pnl, 2),
            "error_count": self.get_error_count(),
            "error_threshold": self.MAX_ERRORS_PER_WINDOW,
            "kill_switch_active": self._kill_switch_ends_at is not None,
            "kill_switch_ends_at": self._kill_switch_ends_at,
            "total_orders_today": self._total_orders,
            "total_volume_today": round(self._total_volume, 2),
            "max_order_size": self.MAX_ORDER_SIZE,
            "api_latency_ms": round(self._api_latency_ms, 1),
            "latency_healthy": self._latency_healthy,
            "wallet_verified": self._wallet_verified,
            "wallet_matic": round(self._wallet_matic, 4),
            "wallet_usdc": round(self._wallet_usdc, 2),
            "bot_panics": self._bot_panic_states,
        }
    
    def get_metrics(self) -> RiskMetrics:
        """Get current risk metrics."""
        return RiskMetrics(
            daily_pnl=self._daily_pnl,
            error_count_last_60s=self.get_error_count(),
            total_orders_today=self._total_orders,
            total_volume_today=self._total_volume,
            trading_state=self._trading_state,
            kill_switch_ends_at=self._kill_switch_ends_at,
            api_latency_ms=self._api_latency_ms,
            wallet_matic=self._wallet_matic,
            wallet_usdc=self._wallet_usdc,
        )
    
    def __repr__(self) -> str:
        return (
            f"RiskManager("
            f"pnl=${self._daily_pnl:.2f}, "
            f"state={self._trading_state.value}, "
            f"errors={self.get_error_count()}/{self.MAX_ERRORS_PER_WINDOW}, "
            f"latency={self._api_latency_ms:.0f}ms)"
        )
