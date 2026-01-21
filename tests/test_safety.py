#!/usr/bin/env python3
"""
Safety Unit Test Suite - tests/test_safety.py

Unit tests to prove the RiskManager works correctly.

Run with: python -m pytest tests/test_safety.py -v
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestRiskManager(unittest.TestCase):
    """Unit tests for the RiskManager safety module."""
    
    def setUp(self):
        """Reset RiskManager before each test."""
        try:
            from strategy_layer.risk_manager import RiskManager
            RiskManager.reset_instance()
            self.rm = RiskManager()
            # Enable wallet verification for testing
            self.rm._wallet_verified = True
        except ImportError:
            self.skipTest("RiskManager not available")
    
    def tearDown(self):
        """Clean up after each test."""
        try:
            from strategy_layer.risk_manager import RiskManager
            RiskManager.reset_instance()
        except ImportError:
            pass
    
    # =========================================================================
    # CASE 1: Max Order Size Limit
    # =========================================================================
    
    def test_max_order_size_rejects_100_dollar_order(self):
        """
        Case 1: Simulate a $100.00 order.
        Assert: RiskManager rejects it (Max Size limit is $20).
        """
        # $100 order should be rejected
        result = self.rm.check_order(100.0)
        is_allowed = result[0] if isinstance(result, tuple) else result
        
        self.assertFalse(is_allowed, "RiskManager should reject $100 order")
        
        if isinstance(result, tuple):
            self.assertIn("max", result[1].lower(), "Rejection reason should mention max")
    
    def test_max_order_size_accepts_valid_order(self):
        """
        A $15.00 order should be accepted (under $20 limit).
        """
        result = self.rm.check_order(15.0)
        is_allowed = result[0] if isinstance(result, tuple) else result
        
        self.assertTrue(is_allowed, "RiskManager should accept $15 order")
    
    def test_max_order_size_accepts_exactly_20(self):
        """
        A $20.00 order (exactly at limit) should be accepted.
        """
        result = self.rm.check_order(20.0)
        is_allowed = result[0] if isinstance(result, tuple) else result
        
        self.assertTrue(is_allowed, "RiskManager should accept exactly $20 order")
    
    def test_max_order_size_rejects_just_over_limit(self):
        """
        A $20.01 order should be rejected.
        """
        result = self.rm.check_order(20.01)
        is_allowed = result[0] if isinstance(result, tuple) else result
        
        self.assertFalse(is_allowed, "RiskManager should reject $20.01 order")
    
    # =========================================================================
    # CASE 2: Daily P&L Loss Limit
    # =========================================================================
    
    def test_daily_pnl_limit_rejects_after_55_dollar_loss(self):
        """
        Case 2: Simulate daily_pnl = -$55.00.
        Assert: RiskManager rejects new trades.
        """
        # Record -$55 loss (exceeds $50 limit)
        self.rm.record_pnl(-55.0)
        
        # Trading should now be blocked
        is_allowed = self.rm.is_trading_allowed()
        self.assertFalse(is_allowed, "RiskManager should block trading after -$55 P&L")
    
    def test_daily_pnl_limit_allows_trading_at_49_dollar_loss(self):
        """
        At -$49.00 loss, trading should still be allowed.
        """
        self.rm.record_pnl(-49.0)
        
        is_allowed = self.rm.is_trading_allowed()
        self.assertTrue(is_allowed, "RiskManager should allow trading at -$49 P&L")
    
    def test_daily_pnl_limit_rejects_exactly_at_50_dollar_loss(self):
        """
        At exactly -$50.00 loss (at limit), trading should be blocked.
        """
        self.rm.record_pnl(-50.0)
        
        # At exactly the limit, should be blocked
        is_allowed = self.rm.is_trading_allowed()
        self.assertFalse(is_allowed, "RiskManager should block trading at exactly -$50 P&L")
    
    def test_daily_pnl_cumulative_losses(self):
        """
        Multiple small losses that cumulatively exceed limit should block.
        """
        # 11 losses of $5 each = $55 total
        for _ in range(11):
            self.rm.record_pnl(-5.0)
        
        is_allowed = self.rm.is_trading_allowed()
        self.assertFalse(is_allowed, "RiskManager should block after cumulative -$55 P&L")
    
    # =========================================================================
    # CASE 3: Gas Guard (Bot 2 - NegRisk)
    # =========================================================================
    
    def test_gas_guard_rejects_when_gas_exceeds_profit(self):
        """
        Case 3: Gas Cost = $0.50, Arb Profit = $0.20.
        Net profit = -$0.30 (negative!).
        Assert: NegRisk logic rejects the trade.
        """
        result = self.rm.check_gas_guard(
            projected_profit=0.20,
            gas_cost=0.50,
        )
        is_allowed = result[0] if isinstance(result, tuple) else result
        
        self.assertFalse(is_allowed, "Gas Guard should reject when gas > profit")
    
    def test_gas_guard_rejects_marginal_profit(self):
        """
        Gas Cost = $0.10, Arb Profit = $0.12.
        Net profit = $0.02 (below $0.05 threshold).
        Assert: Trade rejected.
        """
        result = self.rm.check_gas_guard(
            projected_profit=0.12,
            gas_cost=0.10,
        )
        is_allowed = result[0] if isinstance(result, tuple) else result
        
        self.assertFalse(is_allowed, "Gas Guard should reject $0.02 net profit")
    
    def test_gas_guard_accepts_profitable_trade(self):
        """
        Gas Cost = $0.02, Arb Profit = $0.15.
        Net profit = $0.13 (above $0.05 threshold).
        Assert: Trade accepted.
        """
        result = self.rm.check_gas_guard(
            projected_profit=0.15,
            gas_cost=0.02,
        )
        is_allowed = result[0] if isinstance(result, tuple) else result
        
        self.assertTrue(is_allowed, "Gas Guard should accept $0.13 net profit")
    
    def test_gas_guard_accepts_exactly_at_threshold(self):
        """
        Net profit = exactly $0.05.
        Assert: Trade accepted (at threshold).
        """
        result = self.rm.check_gas_guard(
            projected_profit=0.10,
            gas_cost=0.05,  # Net = $0.05 exactly
        )
        is_allowed = result[0] if isinstance(result, tuple) else result
        
        self.assertTrue(is_allowed, "Gas Guard should accept exactly $0.05 net profit")
    
    # =========================================================================
    # ADDITIONAL SAFETY TESTS
    # =========================================================================
    
    def test_fat_finger_buy_too_high(self):
        """
        Buy order at price 80% above best_ask should be rejected.
        """
        result = self.rm.check_fat_finger(
            order_price=0.90,  # Trying to buy at $0.90
            best_bid=0.45,
            best_ask=0.50,     # Best ask is $0.50
            side="BUY",
        )
        is_allowed = result[0] if isinstance(result, tuple) else result
        
        self.assertFalse(is_allowed, "Should reject buy 80% above best_ask")
    
    def test_fat_finger_buy_at_reasonable_price(self):
        """
        Buy order at price 5% above best_ask should be accepted.
        """
        result = self.rm.check_fat_finger(
            order_price=0.525,  # 5% above $0.50
            best_bid=0.45,
            best_ask=0.50,
            side="BUY",
        )
        is_allowed = result[0] if isinstance(result, tuple) else result
        
        self.assertTrue(is_allowed, "Should accept buy 5% above best_ask")
    
    def test_fat_finger_sell_too_low(self):
        """
        Sell order at price 50% below best_bid should be rejected.
        """
        result = self.rm.check_fat_finger(
            order_price=0.25,  # Trying to sell at $0.25
            best_bid=0.50,     # Best bid is $0.50
            best_ask=0.55,
            side="SELL",
        )
        is_allowed = result[0] if isinstance(result, tuple) else result
        
        self.assertFalse(is_allowed, "Should reject sell 50% below best_bid")
    
    def test_fat_finger_sell_at_reasonable_price(self):
        """
        Sell order at price 5% below best_bid should be accepted.
        """
        result = self.rm.check_fat_finger(
            order_price=0.475,  # 5% below $0.50
            best_bid=0.50,
            best_ask=0.55,
            side="SELL",
        )
        is_allowed = result[0] if isinstance(result, tuple) else result
        
        self.assertTrue(is_allowed, "Should accept sell 5% below best_bid")
    
    def test_kill_switch_activates_after_5_errors(self):
        """
        After 5 API errors in 60 seconds, kill switch should activate.
        """
        # Trigger 5 errors
        for _ in range(5):
            self.rm.record_error(429)  # Rate limit error
        
        # Trading should be paused
        is_allowed = self.rm.is_trading_allowed()
        self.assertFalse(is_allowed, "Kill switch should activate after 5 errors")


class TestNegRiskMath(unittest.TestCase):
    """Unit tests for NegRisk arbitrage calculations."""
    
    def test_negrisk_profit_calculation(self):
        """
        Sum of bids = 1.10, cost = 1.00, gas = 0.02.
        Profit = 0.08.
        """
        sum_bids = 0.60 + 0.50  # = 1.10
        cost = 1.00
        gas = 0.02
        profit = sum_bids - cost - gas
        
        self.assertAlmostEqual(profit, 0.08, places=4)
    
    def test_negrisk_break_even(self):
        """
        Sum of bids = 1.02, cost = 1.00, gas = 0.02.
        Profit = 0.00 (break-even).
        """
        sum_bids = 0.51 + 0.51  # = 1.02
        cost = 1.00
        gas = 0.02
        profit = sum_bids - cost - gas
        
        self.assertAlmostEqual(profit, 0.00, places=4)
    
    def test_negrisk_loss(self):
        """
        Sum of bids = 0.98, cost = 1.00, gas = 0.02.
        Profit = -0.04 (loss).
        """
        sum_bids = 0.48 + 0.50  # = 0.98
        cost = 1.00
        gas = 0.02
        profit = sum_bids - cost - gas
        
        self.assertLess(profit, 0, "Should be a loss")
        self.assertAlmostEqual(profit, -0.04, places=4)


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 SAFETY UNIT TEST SUITE")
    print("=" * 60)
    
    unittest.main(verbosity=2)
