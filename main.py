"""
Polymarket HFT Bot - Main Entry Point

The Complete 5-Bot Fleet:
- Bot 1: CorrelationScanner (Rust) - DAG Monotonicity Violations
- Bot 2: NegRiskMiner (Rust) - Unity Constraint Arbitrage
- Bot 3: ResolutionSniper (Python) - UMA Oracle Liveness
- Bot 4: Vulture (Rust) - Zombie Market Maker + Rebate Farming
- Bot 5: SemanticSentinel (Python) - LLM News Latency Arbitrage
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def check_rust_module():
    """Verify that all Rust core modules are compiled and loadable."""
    try:
        import rust_core
        from rust_core import (
            # Bot 1: Correlation Scanner
            Graph, Violation,
            # Bot 2: NegRisk Miner
            NegRisk, NegRiskConfig, Opportunity,
            # Bot 4: Vulture
            Vulture, VultureConfig, MarketOpportunity,
            # Infrastructure
            PyOrderbook, PyOrderbookManager,
            PySigner,
        )
        
        print("✓ Rust core module loaded successfully")
        print("  Classes available:")
        print("    Bot 1: Graph, Violation")
        print("    Bot 2: NegRisk, NegRiskConfig, Opportunity")
        print("    Bot 4: Vulture, VultureConfig, MarketOpportunity")
        print("    Infra: PyOrderbook, PyOrderbookManager, PySigner")
        
        return True
    except ImportError as e:
        print(f"✗ Failed to import rust_core: {e}")
        print("  Run: cd rust_core && maturin develop --release")
        return False


def check_python_bots():
    """Verify Python bot modules are available."""
    try:
        from strategy_layer.bots import ResolutionSniper, SemanticSentinel
        print("✓ Python bots loaded successfully")
        print("    Bot 3: ResolutionSniper")
        print("    Bot 5: SemanticSentinel")
        return True
    except ImportError as e:
        print(f"✗ Failed to import Python bots: {e}")
        return False


def check_env_config():
    """Verify that required environment variables are set."""
    required_vars = [
        "PRIVATE_KEY",
        "WALLET_ADDRESS", 
        "POLY_API_KEY",
        "POLY_API_SECRET",
        "POLY_API_PASSPHRASE",
    ]
    
    optional_vars = [
        "ANTHROPIC_API_KEY",
        "TWITTER_BEARER_TOKEN",
    ]
    
    missing = []
    empty = []
    
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            empty.append(var)
        elif value == "REPLACE_ME":
            missing.append(var)
    
    if empty:
        print(f"⚠ Empty environment variables: {', '.join(empty)}")
        print("  Fill in .env with your credentials")
        return False
    
    if missing:
        print(f"⚠ Placeholder values detected: {', '.join(missing)}")
        return False
    
    print("✓ Environment configuration valid")
    return True


class Bot1_CorrelationScanner:
    """Bot 1: Detects monotonicity violations in correlated markets."""
    
    def __init__(self):
        from rust_core import Graph
        self.graph = Graph(min_violation_bps=50.0)
        self.name = "CorrelationScanner"
    
    def add_edge(self, parent_id: str, child_id: str, correlation: float = 1.0):
        """Add correlation: parent implies child."""
        self.graph.add_edge(parent_id, child_id, correlation)
    
    def scan(self, prices: list[tuple[str, float]]):
        """Scan for violations. Returns list if P(Child) < P(Parent)."""
        return self.graph.scan(prices)


class Bot2_NegRiskMiner:
    """Bot 2: Detects Unity Constraint violations (Mint-and-Sell / Buy-and-Merge)."""
    
    def __init__(self):
        from rust_core import NegRisk
        self.miner = NegRisk()
        self.name = "NegRiskMiner"
    
    def scan(self, condition_id: str, bids: list[float], asks: list[float]):
        """Scan for opportunities. Returns MintAndSell or BuyAndMerge."""
        return self.miner.scan(condition_id, bids, asks)
    
    def scan_binary(self, condition_id: str, yes_bid: float, yes_ask: float, no_bid: float, no_ask: float):
        """Scan a binary market."""
        return self.miner.scan_binary(condition_id, yes_bid, yes_ask, no_bid, no_ask)


class Bot3_ResolutionSniper:
    """Bot 3: Snipes markets during UMA Oracle liveness period."""
    
    def __init__(self):
        from strategy_layer.bots import ResolutionSniper
        self.sniper = ResolutionSniper()
        self.name = "ResolutionSniper"
    
    def add_pending(self, condition_id: str, question_id: str, proposed_answer: str, 
                   liveness_ends_at: int, current_price: float):
        """Add a market with pending resolution."""
        self.sniper.add_pending(condition_id, question_id, proposed_answer, 
                                liveness_ends_at, current_price)
    
    async def scan(self):
        """Scan for sniper opportunities."""
        return await self.sniper.scan()
    
    def get_pending_count(self) -> int:
        return self.sniper.get_pending_count()


class Bot4_Vulture:
    """Bot 4: Zombie Market Maker with 15-min crypto rebate farming."""
    
    def __init__(self):
        from rust_core import Vulture
        self.vulture = Vulture()
        self.name = "Vulture"
    
    def is_15min_crypto(self, market_slug: str) -> bool:
        """Check if market qualifies for maker rebates."""
        return self.vulture.is_15min_crypto(market_slug)
    
    def scan(self, market_slug: str, condition_id: str, best_bid: float, best_ask: float):
        """Scan a single market for spread opportunity."""
        return self.vulture.scan(market_slug, condition_id, best_bid, best_ask)
    
    def scan_batch(self, markets: list[tuple[str, str, float, float]]):
        """Scan multiple markets. Each tuple: (slug, cond_id, bid, ask)."""
        return self.vulture.scan_batch(markets)


class Bot5_SemanticSentinel:
    """Bot 5: LLM-powered news latency arbitrage."""
    
    def __init__(self):
        from strategy_layer.bots import SemanticSentinel
        self.sentinel = SemanticSentinel()
        self.name = "SemanticSentinel"
    
    def register_market(self, market_slug: str, keywords: list[str]):
        """Register a market with keywords to monitor."""
        self.sentinel.register_market(market_slug, keywords)
    
    async def process_headline(self, headline: str, source: str = "unknown"):
        """Process a news headline for trading signals."""
        return await self.sentinel.process_headline(headline, source)
    
    async def generate_signals(self, event):
        """Generate trade signals from a news event."""
        return await self.sentinel.generate_signals(event)
    
    def get_monitored_count(self) -> int:
        return len(self.sentinel.get_monitored_markets())


class FleetOrchestrator:
    """Orchestrates the complete 5-Bot Fleet."""
    
    def __init__(self):
        print("\n" + "="*60)
        print("INITIALIZING 5-BOT FLEET")
        print("="*60)
        
        self.bot1 = Bot1_CorrelationScanner()
        print(f"  ✓ Bot 1: {self.bot1.name} initialized")
        
        self.bot2 = Bot2_NegRiskMiner()
        print(f"  ✓ Bot 2: {self.bot2.name} initialized")
        
        self.bot3 = Bot3_ResolutionSniper()
        print(f"  ✓ Bot 3: {self.bot3.name} initialized")
        
        self.bot4 = Bot4_Vulture()
        print(f"  ✓ Bot 4: {self.bot4.name} initialized")
        
        self.bot5 = Bot5_SemanticSentinel()
        print(f"  ✓ Bot 5: {self.bot5.name} initialized")
        
        print("="*60)
        print("✓ All 5 Bots Initialized")
        print("="*60 + "\n")
    
    def status(self) -> dict:
        return {
            "bot1": self.bot1.name,
            "bot2": self.bot2.name,
            "bot3": self.bot3.name,
            "bot4": self.bot4.name,
            "bot5": self.bot5.name,
        }


async def run_dry_run():
    """Run a comprehensive dry-run test of all bots."""
    print("\n" + "="*60)
    print("POLYMARKET HFT BOT FLEET - DRY RUN MODE")
    print("="*60 + "\n")
    
    # Step 1: Check Rust module
    print("[1/5] Checking Rust core module...")
    if not check_rust_module():
        print("\n✗ Rust module check failed - compilation needed")
        return False
    
    # Step 2: Check Python bots
    print("\n[2/5] Checking Python bots...")
    if not check_python_bots():
        print("\n✗ Python bots check failed")
        return False
    
    # Step 3: Check environment  
    print("\n[3/5] Checking environment configuration...")
    env_ok = check_env_config()
    if not env_ok:
        print("  (This is expected with empty credentials)")
    
    # Step 4: Initialize fleet
    print("\n[4/5] Initializing bot fleet...")
    try:
        fleet = FleetOrchestrator()
    except Exception as e:
        print(f"✗ Failed to initialize fleet: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 5: Run simulations
    print("[5/5] Running bot simulations...\n")
    
    # === Bot 1: Correlation Scanner ===
    print("  [Bot 1: CorrelationScanner - DAG Monotonicity]")
    fleet.bot1.add_edge("trump-wins-pa", "trump-wins-election", 1.0)
    fleet.bot1.add_edge("fed-hikes-jan", "fed-hikes-q1", 1.0)
    violations = fleet.bot1.scan([
        ("trump-wins-pa", 0.70),
        ("trump-wins-election", 0.50),  # VIOLATION: child < parent
        ("fed-hikes-jan", 0.30),
        ("fed-hikes-q1", 0.60),  # Valid: child > parent
    ])
    print(f"    Found {len(violations)} monotonicity violations")
    for v in violations:
        print(f"    • {v.parent_id} ({v.parent_price:.2f}) > {v.child_id} ({v.child_price:.2f})")
        print(f"      Action: {v.action}")
    
    # === Bot 2: NegRisk Miner ===
    print("\n  [Bot 2: NegRiskMiner - Unity Constraint]")
    # Test Mint-and-Sell: ΣBids > 1.0
    opp1 = fleet.bot2.scan("market-1", [0.55, 0.55], [0.60, 0.60])
    print(f"    Market 1: {opp1.opportunity_type} (Σbids={opp1.sum_bids:.2f})")
    # Test Buy-and-Merge: ΣAsks < 1.0
    opp2 = fleet.bot2.scan("market-2", [0.40, 0.40], [0.45, 0.45])
    print(f"    Market 2: {opp2.opportunity_type} (Σasks={opp2.sum_asks:.2f})")
    
    # === Bot 3: Resolution Sniper ===
    print("\n  [Bot 3: ResolutionSniper - UMA Oracle Liveness]")
    import time
    fleet.bot3.add_pending(
        condition_id="0xabc123",
        question_id="q_fed_decision",
        proposed_answer="yes",
        liveness_ends_at=int(time.time()) + 3600,
        current_price=0.85,  # Market hasn't fully priced in YES
    )
    opportunities = await fleet.bot3.scan()
    print(f"    Tracking {fleet.bot3.get_pending_count()} pending resolutions")
    print(f"    Found {len(opportunities)} sniper opportunities")
    for opp in opportunities:
        print(f"    • {opp.side} @ {opp.current_price:.2f} → expected {opp.expected_resolution}")
    
    # === Bot 4: Vulture ===
    print("\n  [Bot 4: Vulture - Zombie Market Maker]")
    mock_markets = [
        ("btc-price-105k-15m", "0xbtc", 0.42, 0.58),  # Crypto with rebate
        ("eth-15-min-above-4k", "0xeth", 0.35, 0.45),  # Crypto with rebate
        ("trump-wins-2024", "0xtrump", 0.48, 0.53),    # Non-crypto
    ]
    vulture_opps = fleet.bot4.scan_batch(mock_markets)
    print(f"    Found {len(vulture_opps)} spread opportunities")
    for opp in vulture_opps:
        rebate = "🔥 REBATE" if opp.is_crypto_15min else ""
        post_only = "POST_ONLY" if opp.use_post_only else "GTC"
        print(f"    • {opp.market_slug}: {opp.spread_bps:.0f}bps [{post_only}] {rebate}")
    
    # === Bot 5: Semantic Sentinel ===
    print("\n  [Bot 5: SemanticSentinel - News Latency]")
    fleet.bot5.register_market("trump-resignation", ["trump", "resign", "president"])
    fleet.bot5.register_market("fed-rate-hike", ["fed", "rate", "hike", "powell"])
    
    test_headlines = [
        "BREAKING: Fed announces surprise rate hike of 50bps",
        "Trump considering resignation amid mounting pressure",
    ]
    
    for headline in test_headlines:
        event = await fleet.bot5.process_headline(headline, "test")
        if event:
            signals = await fleet.bot5.generate_signals(event)
            print(f"    • \"{headline[:50]}...\"")
            print(f"      Keywords: {event.keywords_found}, Sentiment: {event.sentiment.value}")
            for sig in signals:
                print(f"      → {sig.side} {sig.market_slug} ({sig.urgency})")
    
    print("\n" + "="*60)
    print("DRY RUN COMPLETE - ALL SYSTEMS OPERATIONAL")
    print("="*60 + "\n")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Polymarket HFT Bot - The Complete 5-Bot Fleet"
    )
    parser.add_argument(
        "--mode",
        choices=["dry-run", "live", "scan"],
        default="dry-run",
        help="Operation mode (default: dry-run)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║   🦅 POLYMARKET HFT BOT - 5-BOT FLEET                    ║
    ║                                                           ║
    ║   Bot 1: CorrelationScanner (DAG Monotonicity)           ║
    ║   Bot 2: NegRiskMiner (Mint-and-Sell / Buy-and-Merge)    ║
    ║   Bot 3: ResolutionSniper (UMA Oracle Liveness)          ║
    ║   Bot 4: Vulture (Zombie MM + Rebate Farming)            ║
    ║   Bot 5: SemanticSentinel (LLM News Arbitrage)           ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    if args.mode == "dry-run":
        success = asyncio.run(run_dry_run())
        sys.exit(0 if success else 1)
    elif args.mode == "live":
        print("⚠ Live mode not implemented yet")
        print("  Use --mode dry-run to test the system")
        sys.exit(1)
    elif args.mode == "scan":
        print("⚠ Scan mode not implemented yet")
        sys.exit(1)


if __name__ == "__main__":
    main()
