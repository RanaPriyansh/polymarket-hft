"""
Alpha Trading Configuration - Training Wheels Mode

Strict micro-limits for initial live trading to minimize risk.
These settings OVERRIDE the defaults in config/settings.py.

Usage:
    export POLYMARKET_MODE=alpha
    python main.py --mode live
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AlphaConfig:
    """
    Alpha Phase Configuration - Strict "Training Wheels"
    
    These limits are intentionally conservative for the first phase
    of live trading. They can be loosened as confidence grows.
    """
    
    # === MODE ===
    MODE: str = "LIVE"  # Real Polygon Mainnet
    PHASE: str = "ALPHA"
    
    # === POSITION LIMITS ===
    MAX_POSITION_SIZE: float = 5.00      # $5.00 max per trade
    MAX_OPEN_POSITIONS: int = 3          # Max 3 simultaneous trades
    MAX_TOTAL_EXPOSURE: float = 15.00    # Max $15 total at risk
    
    # === DAILY LIMITS ===
    DAILY_STOP_LOSS: float = 15.00       # Stop if we lose $15
    DAILY_PROFIT_TARGET: float = 50.00   # Optional: take profits at $50
    
    # === GAS LIMITS ===
    MAX_GAS_PER_TRADE: float = 0.10      # $0.10 max gas per trade
    MIN_NET_PROFIT: float = 0.05         # $0.05 min net profit after gas
    
    # === WALLET SAFETY ===
    MAX_HOT_WALLET_BALANCE: float = 100.00  # Never keep >$100 in hot wallet
    MIN_MATIC_BALANCE: float = 1.0          # Need at least 1 MATIC for gas
    
    # === API LIMITS ===
    MAX_API_LATENCY_MS: float = 300.0   # Abort if ping > 300ms
    
    # === KILL SWITCH ===
    KILL_SWITCH_FILE: str = "KILL_SWITCH.txt"
    KILL_SWITCH_CHECK_INTERVAL: float = 1.0  # Check every second
    
    def __repr__(self) -> str:
        return (
            f"AlphaConfig(MODE={self.MODE}, "
            f"MAX_POSITION=${self.MAX_POSITION_SIZE}, "
            f"DAILY_STOP=${self.DAILY_STOP_LOSS})"
        )


# Global instance
ALPHA_CONFIG = AlphaConfig()


def print_alpha_config():
    """Print the Alpha configuration at startup."""
    config = ALPHA_CONFIG
    print("\n" + "=" * 60)
    print("🎓 ALPHA TRADING MODE - Training Wheels Active")
    print("=" * 60)
    print(f"\n📦 POSITION LIMITS")
    print(f"   Max Position Size:    ${config.MAX_POSITION_SIZE:.2f}")
    print(f"   Max Open Positions:   {config.MAX_OPEN_POSITIONS}")
    print(f"   Max Total Exposure:   ${config.MAX_TOTAL_EXPOSURE:.2f}")
    print(f"\n📉 DAILY LIMITS")
    print(f"   Daily Stop Loss:      ${config.DAILY_STOP_LOSS:.2f}")
    print(f"   Profit Target:        ${config.DAILY_PROFIT_TARGET:.2f}")
    print(f"\n⛽ GAS LIMITS")
    print(f"   Max Gas/Trade:        ${config.MAX_GAS_PER_TRADE:.2f}")
    print(f"   Min Net Profit:       ${config.MIN_NET_PROFIT:.2f}")
    print(f"\n🔐 SAFETY")
    print(f"   Max Hot Wallet:       ${config.MAX_HOT_WALLET_BALANCE:.2f}")
    print(f"   Kill Switch File:    {config.KILL_SWITCH_FILE}")
    print("=" * 60 + "\n")


def apply_alpha_limits(risk_manager):
    """
    Apply Alpha limits to the RiskManager.
    
    Call this at startup to override default limits.
    """
    config = ALPHA_CONFIG
    
    # Override RiskManager limits
    risk_manager.MAX_DAILY_LOSS = config.DAILY_STOP_LOSS
    risk_manager.MAX_ORDER_SIZE = config.MAX_POSITION_SIZE
    risk_manager.MIN_NET_PROFIT_THRESHOLD = config.MIN_NET_PROFIT
    
    print(f"✅ Applied Alpha limits to RiskManager")
    print(f"   MAX_DAILY_LOSS: ${risk_manager.MAX_DAILY_LOSS:.2f}")
    print(f"   MAX_ORDER_SIZE: ${risk_manager.MAX_ORDER_SIZE:.2f}")
