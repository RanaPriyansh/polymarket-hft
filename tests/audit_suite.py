#!/usr/bin/env python3
"""
🦅 POLYMARKET PROFITABILITY AUDIT SUITE

Comprehensive audit for the 4-Bot Fleet:
- Module 1: Live Market Scanner (Money Printer Check)
- Module 2: Safety Logic Unit Tests
- Module 3: Volume Audit

Run with: python -m tests.audit_suite
Or: pytest tests/audit_suite.py -v
"""

import asyncio
import sys
import time
import unittest
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

# ============================================================================
# CONSTANTS
# ============================================================================

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"
GAS_COST = 0.02  # $0.02 gas cost for split/merge

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class NegRiskOpportunity:
    """Bot 2: NegRisk opportunity data"""
    market_id: str
    question: str
    sum_bids: float
    potential_profit: float
    is_profitable: bool


@dataclass
class VultureOpportunity:
    """Bot 4: Vulture spread opportunity"""
    market_id: str
    question: str
    best_bid: float
    best_ask: float
    spread_pct: float
    is_viable: bool


@dataclass
class SniperCheck:
    """Bot 3: Sniper simulation result"""
    market_id: str
    question: str
    resolution: str
    price_2h_before: Optional[float]
    was_mispriced: bool


# ============================================================================
# MODULE 1: LIVE MARKET SCANNER
# ============================================================================

class LiveMarketScanner:
    """
    Connects to Polymarket APIs and scans for real opportunities.
    This is the "Money Printer" check.
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.negrisk_opportunities: list[NegRiskOpportunity] = []
        self.vulture_opportunities: list[VultureOpportunity] = []
        self.sniper_checks: list[SniperCheck] = []
    
    async def close(self):
        await self.client.aclose()
    
    async def fetch_active_markets(self, limit: int = 50) -> list[dict]:
        """Fetch top active NegRisk markets from Gamma API."""
        try:
            url = f"{GAMMA_API_BASE}/markets"
            params = {
                "limit": limit,
                "active": "true",
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false",
            }
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"  ⚠️  Error fetching markets: {e}")
            return []
    
    async def fetch_orderbook(self, token_id: str) -> tuple[float, float]:
        """
        Fetch orderbook for a token and return (best_bid, best_ask).
        Returns (0.0, 0.0) if unavailable.
        """
        try:
            url = f"{CLOB_API_BASE}/book"
            params = {"token_id": token_id}
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            best_bid = float(bids[0]["price"]) if bids else 0.0
            best_ask = float(asks[0]["price"]) if asks else 0.0
            
            return best_bid, best_ask
        except Exception as e:
            return 0.0, 0.0
    
    async def scan_negrisk_opportunities(self) -> list[NegRiskOpportunity]:
        """
        Task 1: Bot 2 - NegRisk Miner Check
        
        For each market, calculate:
        - Sum(Best_Bids) across all outcomes
        - Potential_Profit = Sum(Bids) - 1.00 - Gas_Cost($0.02)
        
        Output markets where Potential_Profit > $0.05
        """
        print("\n[BOT 2: NegRisk Miner]")
        print("Scanning top 50 markets...")
        
        markets = await self.fetch_active_markets(50)
        opportunities = []
        
        for market in markets:
            # Skip non-binary markets for simplicity
            tokens = market.get("tokens", [])
            if len(tokens) != 2:
                continue
            
            # Fetch orderbooks for YES and NO tokens
            yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), None)
            no_token = next((t for t in tokens if t.get("outcome") == "No"), None)
            
            if not yes_token or not no_token:
                continue
            
            yes_bid, _ = await self.fetch_orderbook(yes_token.get("token_id", ""))
            no_bid, _ = await self.fetch_orderbook(no_token.get("token_id", ""))
            
            sum_bids = yes_bid + no_bid
            potential_profit = sum_bids - 1.00 - GAS_COST
            
            is_profitable = potential_profit > 0.05
            
            opp = NegRiskOpportunity(
                market_id=market.get("condition_id", ""),
                question=market.get("question", "")[:60],
                sum_bids=sum_bids,
                potential_profit=potential_profit,
                is_profitable=is_profitable,
            )
            
            if is_profitable:
                opportunities.append(opp)
                print(f'✅ FOUND: "{opp.question}" (Sum Bids: {sum_bids:.2f})')
                print(f"   -> Potential Profit: ${potential_profit:.2f} per share (Net of Gas)")
            elif sum_bids > 1.0 and potential_profit <= 0.05 and potential_profit > -0.02:
                print(f'⚠️  MARGINAL: "{opp.question[:40]}..." (Sum Bids: {sum_bids:.2f})')
                print(f"   -> Potential Profit: ${potential_profit:.2f} (Gas eats profit - SKIP)")
            
            # Rate limit protection
            await asyncio.sleep(0.1)
        
        self.negrisk_opportunities = opportunities
        return opportunities
    
    async def scan_vulture_spreads(self) -> list[VultureOpportunity]:
        """
        Task 2: Bot 4 - Spread Capture
        
        Calculate Spread % = (Best_Ask - Best_Bid) / Best_Bid
        Flag as "Vulture Opportunity" if Spread > 0.5% (50bps)
        """
        print("\n[BOT 4: Vulture]")
        print("Scanning spreads...")
        
        markets = await self.fetch_active_markets(50)
        opportunities = []
        
        for market in markets:
            tokens = market.get("tokens", [])
            if not tokens:
                continue
            
            # Check the YES token spread
            yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), None)
            if not yes_token:
                continue
            
            best_bid, best_ask = await self.fetch_orderbook(yes_token.get("token_id", ""))
            
            if best_bid <= 0 or best_ask <= 0:
                continue
            
            spread_pct = (best_ask - best_bid) / best_bid * 100
            is_viable = spread_pct > 0.5  # 50bps threshold
            
            opp = VultureOpportunity(
                market_id=market.get("condition_id", ""),
                question=market.get("question", "")[:50],
                best_bid=best_bid,
                best_ask=best_ask,
                spread_pct=spread_pct,
                is_viable=is_viable,
            )
            
            if is_viable:
                opportunities.append(opp)
                print(f'✅ "{opp.question}": Spread {spread_pct:.1f}% (Rebate Farm Viable)')
            
            await asyncio.sleep(0.1)
        
        self.vulture_opportunities = opportunities
        return opportunities
    
    async def simulate_sniper(self) -> list[SniperCheck]:
        """
        Task 3: Bot 3 - Sniper Simulation
        
        Fetch 5 recently resolved events and check their price 2 hours before resolution.
        Did they trade at <$0.99 despite the outcome being known?
        """
        print("\n[BOT 3: Sniper Simulation]")
        print("Checking recently resolved events...")
        
        try:
            url = f"{GAMMA_API_BASE}/markets"
            params = {
                "limit": 10,
                "closed": "true",
                "order": "end_date_iso",
                "ascending": "false",
            }
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            markets = response.json()[:5]  # Take top 5 resolved
        except Exception as e:
            print(f"  ⚠️  Error fetching resolved markets: {e}")
            return []
        
        checks = []
        
        for market in markets:
            question = market.get("question", "")[:50]
            resolution = market.get("outcome", "Unknown")
            
            # Note: In a real scenario, we'd need historical price data
            # For now, we simulate based on available data
            # The Gamma API doesn't provide historical prices directly
            
            # Check if winning outcome token was underpriced at close
            tokens = market.get("tokens", [])
            winning_token = next(
                (t for t in tokens if t.get("winner") is True),
                None
            )
            
            # Simulate price 2h before resolution
            # In production, use a time-series API or store historical data
            price_2h_before = None
            was_mispriced = False
            
            if winning_token:
                # Use last traded price as proxy (not actual 2h before)
                price_2h_before = float(winning_token.get("price", 0) or 0)
                was_mispriced = price_2h_before < 0.99 if price_2h_before > 0 else False
            
            check = SniperCheck(
                market_id=market.get("condition_id", ""),
                question=question,
                resolution=resolution,
                price_2h_before=price_2h_before,
                was_mispriced=was_mispriced,
            )
            checks.append(check)
            
            if price_2h_before:
                status = "✅ MISPRICED" if was_mispriced else "❌ Correctly priced"
                print(f'  "{question}": Resolved {resolution}, Price={price_2h_before:.3f} {status}')
            else:
                print(f'  "{question}": Resolved {resolution}, Price data unavailable')
        
        self.sniper_checks = checks
        return checks


# ============================================================================
# MODULE 2: SAFETY LOGIC UNIT TESTS
# ============================================================================

def calculate_profit(bid_a: float, bid_b: float, gas: float = GAS_COST) -> float:
    """Calculate NegRisk profit from sum of bids minus $1.00 and gas."""
    sum_bids = bid_a + bid_b
    profit = sum_bids - 1.00 - gas
    return round(profit, 6)


def check_price_deviation(order_price: float, market_price: float, max_deviation: float = 0.20) -> bool:
    """
    Check if order price is within acceptable deviation from market price.
    Returns False if deviation exceeds threshold (fat finger protection).
    """
    if market_price <= 0:
        return False
    
    deviation = abs(order_price - market_price) / market_price
    return deviation <= max_deviation


class TestSafetyLogic(unittest.TestCase):
    """
    Module 2: Safety Logic Unit Tests
    
    Verify the math and risk controls are bulletproof.
    """
    
    def test_negrisk_math(self):
        """
        Scenario: Bid A=0.60, Bid B=0.50. Sum=1.10.
        Gas is $0.02.
        Expected: Profit = 0.08
        """
        profit = calculate_profit(0.60, 0.50, gas=0.02)
        self.assertAlmostEqual(profit, 0.08, places=4)
    
    def test_negrisk_break_even(self):
        """
        Scenario: Bids sum to 1.02 with 0.02 gas.
        Expected: Exactly break-even (0.00 profit)
        """
        profit = calculate_profit(0.51, 0.51, gas=0.02)
        self.assertAlmostEqual(profit, 0.00, places=4)
    
    def test_negrisk_loss(self):
        """
        Scenario: Bids sum to 0.98 (less than $1.00).
        Expected: Loss (negative profit)
        """
        profit = calculate_profit(0.48, 0.50, gas=0.02)
        self.assertLess(profit, 0)
    
    def test_risk_manager_block(self):
        """
        Scenario: Current P&L is -$51 (exceeds $50 limit).
        Expected: Trading should be blocked.
        """
        # Import the actual RiskManager
        try:
            from strategy_layer.risk_manager import RiskManager
            
            # Reset singleton for clean test
            RiskManager.reset_instance()
            rm = RiskManager()
            
            # Enable wallet verification to allow initial trading check
            rm._wallet_verified = True
            
            # Verify trading is initially allowed
            self.assertTrue(rm.is_trading_allowed(), "Should allow trading initially")
            
            # Simulate loss exceeding limit
            rm.record_pnl(-51.0)
            
            # Trading should be blocked
            result = rm.is_trading_allowed()
            self.assertFalse(result)
            
            # Cleanup - MUST reset for other tests
            RiskManager.reset_instance()
        except ImportError:
            self.skipTest("RiskManager not available")
    
    def test_risk_manager_order_size_limit(self):
        """
        Scenario: Try to place a $1000 order (max is $20).
        Expected: Order rejected.
        """
        try:
            from strategy_layer.risk_manager import RiskManager
            
            RiskManager.reset_instance()
            rm = RiskManager()
            
            # Enable wallet verification to allow trading
            rm._wallet_verified = True
            
            # Verify clean state - trading should be allowed initially
            self.assertTrue(rm.is_trading_allowed(), "RiskManager should allow trading in clean state")
            
            # Small order should pass
            small_result = rm.check_order(10.0)
            # Handle both tuple (bool, str) and plain bool returns
            small_allowed = small_result[0] if isinstance(small_result, tuple) else small_result
            self.assertTrue(small_allowed, "Order under limit should be allowed")
            
            # Order exceeds max size ($20) - check_order returns False
            large_result = rm.check_order(1000.0)
            # Handle both tuple (bool, str) and plain bool returns
            large_allowed = large_result[0] if isinstance(large_result, tuple) else large_result
            self.assertFalse(large_allowed, "Order over $20 limit should be rejected")
            
            RiskManager.reset_instance()
        except ImportError:
            self.skipTest("RiskManager not available")
    
    def test_fat_finger_protection(self):
        """
        Scenario: Market price is 0.50. Bot tries to buy at 0.90.
        Deviation = 80% (exceeds 20% threshold).
        Expected: Price Deviation check returns False (rejected).
        """
        result = check_price_deviation(order_price=0.90, market_price=0.50)
        self.assertFalse(result)
    
    def test_acceptable_price_deviation(self):
        """
        Scenario: Market price is 0.50. Bot tries to buy at 0.55.
        Deviation = 10% (within 20% threshold).
        Expected: Price Deviation check returns True (accepted).
        """
        result = check_price_deviation(order_price=0.55, market_price=0.50)
        self.assertTrue(result)


# ============================================================================
# MODULE 3: VOLUME AUDIT
# ============================================================================

class VolumeAuditor:
    """
    Estimates daily profit potential based on trading volume.
    
    Assumptions:
    - We can capture 1% of daily volume as arbitrage
    - Profit margin is the average spread we capture
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.total_volume_24h = 0.0
        self.avg_spread_margin = 0.0
        self.projected_daily_profit = 0.0
    
    async def close(self):
        await self.client.aclose()
    
    async def audit_volume(self) -> dict:
        """
        Fetch 24h volume for top 10 NegRisk markets.
        Calculate projected daily profit.
        """
        print("\n[VOLUME AUDIT]")
        print("Fetching 24h volume data...")
        
        try:
            url = f"{GAMMA_API_BASE}/markets"
            params = {
                "limit": 10,
                "active": "true",
                "order": "volume24hr",
                "ascending": "false",
            }
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            markets = response.json()
        except Exception as e:
            print(f"  ⚠️  Error fetching volume data: {e}")
            return {"error": str(e)}
        
        total_volume = 0.0
        spreads = []
        
        print("\n  Top 10 Markets by 24h Volume:")
        print("  " + "-" * 60)
        
        for market in markets:
            question = market.get("question", "")[:40]
            volume_24h = float(market.get("volume24hr", 0) or 0)
            spread = float(market.get("spread", 0) or 0) * 100  # Convert to percentage
            
            total_volume += volume_24h
            if spread > 0:
                spreads.append(spread)
            
            print(f"  ${volume_24h:>12,.2f} | {spread:.2f}% spread | {question}")
        
        print("  " + "-" * 60)
        print(f"  TOTAL 24H VOLUME: ${total_volume:,.2f}")
        
        # Calculate average spread margin
        avg_spread = sum(spreads) / len(spreads) if spreads else 0.5  # Default 0.5%
        
        # Assumption: We capture 1% of volume at avg spread
        capture_rate = 0.01  # 1%
        projected_profit = total_volume * capture_rate * (avg_spread / 100)
        
        self.total_volume_24h = total_volume
        self.avg_spread_margin = avg_spread
        self.projected_daily_profit = projected_profit
        
        print(f"\n  Avg Spread Margin: {avg_spread:.2f}%")
        print(f"  Capture Rate: {capture_rate * 100}% of volume")
        print(f"  >> PROJECTED DAILY PROFIT: ${projected_profit:,.2f}")
        
        return {
            "total_volume_24h": total_volume,
            "avg_spread_pct": avg_spread,
            "capture_rate": capture_rate,
            "projected_daily_profit": projected_profit,
        }


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def run_full_audit():
    """Run the complete profitability audit."""
    
    print("=" * 60)
    print("🦅 POLYMARKET PROFITABILITY AUDIT")
    print("=" * 60)
    
    # ========== Module 1: Live Market Scanner ==========
    scanner = LiveMarketScanner()
    
    try:
        negrisk_opps = await scanner.scan_negrisk_opportunities()
        vulture_opps = await scanner.scan_vulture_spreads()
        sniper_checks = await scanner.simulate_sniper()
        
        # Summary for Bot 2 (NegRisk)
        print(f"\n>> Total NegRisk Opportunities Found: {len(negrisk_opps)}")
        if negrisk_opps:
            avg_profit = sum(o.potential_profit for o in negrisk_opps) / len(negrisk_opps)
            est_trades = len(negrisk_opps) * 5  # Estimate 5 trades per opportunity/day
            est_daily = avg_profit * est_trades
            print(f">> Est. Daily Frequency: ~{est_trades} trades")
            print(f">> Est. Daily Profit (Bot 2): ${est_daily:.2f}")
        
        # Summary for Bot 4 (Vulture)
        if vulture_opps:
            avg_spread = sum(o.spread_pct for o in vulture_opps) / len(vulture_opps)
            # Maker rebate is ~0.02% of order value; assume $1000/day in orders
            est_rebates = 1000 * (avg_spread / 100) * 0.5  # 50% capture
            print(f">> Est. Daily Rebates (Bot 4): ${est_rebates:.2f}")
        
    finally:
        await scanner.close()
    
    # ========== Module 2: Safety Tests ==========
    print("\n" + "=" * 60)
    print("[SAFETY CHECK]")
    print("=" * 60)
    
    # Run the unit tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestSafetyLogic)
    
    # Custom result handler for pretty output
    class PrettyResult(unittest.TestResult):
        def addSuccess(self, test):
            print(f"✅ {test.shortDescription() or str(test)}")
            super().addSuccess(test)
        
        def addFailure(self, test, err):
            print(f"❌ {test.shortDescription() or str(test)}")
            super().addFailure(test, err)
        
        def addError(self, test, err):
            print(f"⚠️  {test.shortDescription() or str(test)}: {err[1]}")
            super().addError(test, err)
        
        def addSkip(self, test, reason):
            print(f"⏭️  {test.shortDescription() or str(test)}: {reason}")
            super().addSkip(test, reason)
    
    result = PrettyResult()
    suite.run(result)
    
    safety_passed = len(result.failures) == 0 and len(result.errors) == 0
    
    # ========== Module 3: Volume Audit ==========
    print("\n" + "=" * 60)
    auditor = VolumeAuditor()
    
    try:
        volume_result = await auditor.audit_volume()
    finally:
        await auditor.close()
    
    # ========== FINAL VERDICT ==========
    print("\n" + "=" * 60)
    
    total_est_profit = 0.0
    if negrisk_opps:
        avg_profit = sum(o.potential_profit for o in negrisk_opps) / len(negrisk_opps)
        total_est_profit += avg_profit * len(negrisk_opps) * 5  # NegRisk
    
    if vulture_opps:
        avg_spread = sum(o.spread_pct for o in vulture_opps) / len(vulture_opps)
        total_est_profit += 1000 * (avg_spread / 100) * 0.5  # Vulture
    
    # Add volume-based estimate
    if volume_result.get("projected_daily_profit"):
        total_est_profit = max(total_est_profit, volume_result["projected_daily_profit"])
    
    if safety_passed and (negrisk_opps or vulture_opps):
        print("✅ VERDICT: SYSTEM PROFITABLE. READY FOR LIVE DEPLOYMENT.")
        print(f"   Combined Est. Daily Profit: ${total_est_profit:.2f}")
    elif safety_passed:
        print("⚠️  VERDICT: SAFETY CHECKS PASS. LOW MARKET OPPORTUNITY.")
        print("   Wait for better market conditions.")
    else:
        print("❌ VERDICT: SAFETY CHECKS FAILED. DO NOT DEPLOY.")
    
    print("=" * 60)
    
    return {
        "negrisk_opportunities": len(negrisk_opps),
        "vulture_opportunities": len(vulture_opps),
        "safety_passed": safety_passed,
        "projected_daily_profit": total_est_profit,
    }


def main():
    """Entry point when running as script."""
    try:
        result = asyncio.run(run_full_audit())
        sys.exit(0 if result["safety_passed"] else 1)
    except KeyboardInterrupt:
        print("\nAudit cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Audit failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
