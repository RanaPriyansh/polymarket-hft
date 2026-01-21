#!/usr/bin/env python3
"""
Shadow Engine - Paper Trading for Polymarket HFT

Intercepts all orders in Shadow Mode and logs them to CSV instead of
sending to the real Polymarket API. This allows testing strategy logic
without risking real capital.

Usage:
    python main.py --mode shadow
"""

import asyncio
import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class ShadowOrder:
    """Represents a simulated order in shadow mode."""
    timestamp: str
    bot_name: str
    market_slug: str
    condition_id: str
    side: str  # BUY or SELL
    price: float
    size: float
    expected_profit: float
    gas_cost: float
    status: str = "FILLED"  # Assume 100% fill for testing
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "bot_name": self.bot_name,
            "market_slug": self.market_slug,
            "condition_id": self.condition_id,
            "side": self.side,
            "price": self.price,
            "size": self.size,
            "expected_profit": self.expected_profit,
            "gas_cost": self.gas_cost,
            "status": self.status,
        }


@dataclass
class ShadowStats:
    """Aggregate statistics for shadow trading session."""
    total_trades: int = 0
    total_profit: float = 0.0
    total_gas_saved: float = 0.0
    total_wins: int = 0
    total_losses: int = 0
    errors: int = 0
    
    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return (self.total_wins / self.total_trades) * 100


class ShadowExchange:
    """
    Mock exchange client for Shadow (Paper Trading) mode.
    
    Intercepts all order calls and logs them to CSV without
    actually sending to the Polymarket API.
    """
    
    CSV_FILE = "logs/shadow_trades.csv"
    CSV_COLUMNS = [
        "timestamp", "bot_name", "market_slug", "condition_id",
        "side", "price", "size", "expected_profit", "gas_cost", "status"
    ]
    
    def __init__(self):
        self.orders: List[ShadowOrder] = []
        self.stats = ShadowStats()
        self._ensure_log_dir()
        self._init_csv()
        
        logger.info("👻 ShadowExchange initialized - Paper Trading Mode")
        print("\n" + "=" * 60)
        print("👻 SHADOW MODE - No Real Money Will Move")
        print(f"   Logging trades to: {self.CSV_FILE}")
        print("=" * 60 + "\n")
    
    def _ensure_log_dir(self):
        """Create logs directory if it doesn't exist."""
        Path("logs").mkdir(exist_ok=True)
    
    def _init_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if not os.path.exists(self.CSV_FILE):
            with open(self.CSV_FILE, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS)
                writer.writeheader()
    
    def _append_to_csv(self, order: ShadowOrder):
        """Append order to CSV log."""
        with open(self.CSV_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS)
            writer.writerow(order.to_dict())
    
    async def place_order(
        self,
        bot_name: str,
        market_slug: str,
        condition_id: str,
        side: str,
        price: float,
        size: float,
        expected_profit: float = 0.0,
        gas_cost: float = 0.0,
        post_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Simulate placing an order.
        
        Instead of sending to the API:
        1. Log the order details
        2. Assume 100% fill
        3. Update statistics
        
        Returns:
            Dict with simulated order response
        """
        order = ShadowOrder(
            timestamp=datetime.utcnow().isoformat(),
            bot_name=bot_name,
            market_slug=market_slug,
            condition_id=condition_id,
            side=side.upper(),
            price=price,
            size=size,
            expected_profit=expected_profit,
            gas_cost=gas_cost,
            status="FILLED",
        )
        
        # Log to CSV
        self._append_to_csv(order)
        self.orders.append(order)
        
        # Update stats
        self.stats.total_trades += 1
        net_profit = expected_profit - gas_cost
        self.stats.total_profit += net_profit
        self.stats.total_gas_saved += gas_cost  # Gas we didn't actually spend
        
        if net_profit >= 0:
            self.stats.total_wins += 1
        else:
            self.stats.total_losses += 1
        
        # Log the simulated trade
        emoji = "📈" if net_profit >= 0 else "📉"
        post_only_str = "[POST_ONLY]" if post_only else ""
        logger.info(
            f"{emoji} SHADOW {side}: {market_slug} @ ${price:.4f} x {size:.2f} "
            f"(Net: ${net_profit:.4f}) {post_only_str}"
        )
        
        # Return simulated response
        return {
            "id": f"shadow_{len(self.orders)}",
            "status": "FILLED",
            "price": price,
            "size": size,
            "side": side,
            "filled_size": size,
            "is_shadow": True,
        }
    
    async def cancel_order(self, order_id: str) -> bool:
        """Simulate canceling an order."""
        logger.info(f"👻 SHADOW: Cancelled order {order_id}")
        return True
    
    async def cancel_all_orders(self) -> int:
        """Simulate canceling all orders."""
        count = len([o for o in self.orders if o.status == "OPEN"])
        logger.info(f"👻 SHADOW: Cancelled all {count} open orders")
        return count
    
    async def get_orderbook(self, token_id: str) -> Dict:
        """
        Fetch real orderbook for price reference.
        (We still want to see real market data in shadow mode)
        """
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://clob.polymarket.com/book",
                    params={"token_id": token_id}
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning(f"Failed to fetch orderbook: {e}")
            return {"bids": [], "asks": []}
    
    def record_error(self, error: str):
        """Record an error in shadow mode."""
        self.stats.errors += 1
        logger.error(f"👻 SHADOW ERROR: {error}")
    
    def get_stats(self) -> ShadowStats:
        """Get current shadow trading statistics."""
        return self.stats
    
    def print_report(self):
        """Print performance report for shadow trading session."""
        print("\n" + "=" * 60)
        print("👻 SHADOW MODE - PERFORMANCE REPORT")
        print("=" * 60)
        print(f"\n📊 TRADING SUMMARY")
        print(f"   Total Trades:      {self.stats.total_trades}")
        print(f"   Wins:              {self.stats.total_wins}")
        print(f"   Losses:            {self.stats.total_losses}")
        print(f"   Win Rate:          {self.stats.win_rate:.1f}%")
        print(f"\n💰 PROFIT/LOSS")
        print(f"   Virtual P&L:       ${self.stats.total_profit:.2f}")
        print(f"   Gas Fees Avoided:  ${self.stats.total_gas_saved:.2f}")
        print(f"\n⚠️  ERRORS")
        print(f"   Total Errors:      {self.stats.errors}")
        print("=" * 60 + "\n")
        
        # Also write to file
        report_file = "logs/shadow_report.txt"
        with open(report_file, "w") as f:
            f.write("SHADOW MODE - PERFORMANCE REPORT\n")
            f.write("=" * 40 + "\n")
            f.write(f"Total Trades: {self.stats.total_trades}\n")
            f.write(f"Wins: {self.stats.total_wins}\n")
            f.write(f"Losses: {self.stats.total_losses}\n")
            f.write(f"Win Rate: {self.stats.win_rate:.1f}%\n")
            f.write(f"Virtual P&L: ${self.stats.total_profit:.2f}\n")
            f.write(f"Gas Saved: ${self.stats.total_gas_saved:.2f}\n")
            f.write(f"Errors: {self.stats.errors}\n")
        
        logger.info(f"Report saved to {report_file}")


def generate_performance_report(csv_file: str = "logs/shadow_trades.csv"):
    """
    Standalone function to generate performance report from CSV.
    Can be called after a shadow session ends.
    """
    if not os.path.exists(csv_file):
        print(f"No shadow trades file found at {csv_file}")
        return
    
    total_profit = 0.0
    total_gas = 0.0
    wins = 0
    losses = 0
    total_trades = 0
    errors = 0
    
    with open(csv_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_trades += 1
            profit = float(row.get("expected_profit", 0))
            gas = float(row.get("gas_cost", 0))
            net = profit - gas
            total_profit += net
            total_gas += gas
            
            if net >= 0:
                wins += 1
            else:
                losses += 1
    
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    print("\n" + "=" * 60)
    print("📊 SHADOW TRADING PERFORMANCE REPORT")
    print("=" * 60)
    print(f"\n📈 TRADES")
    print(f"   Total:         {total_trades}")
    print(f"   Wins:          {wins}")
    print(f"   Losses:        {losses}")
    print(f"   Win Rate:      {win_rate:.1f}%")
    print(f"\n💵 FINANCIALS")
    print(f"   Virtual P&L:   ${total_profit:.2f}")
    print(f"   Gas Avoided:   ${total_gas:.2f}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    # If run directly, generate report from existing CSV
    generate_performance_report()
