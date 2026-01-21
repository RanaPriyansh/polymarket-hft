"""
Polymarket HFT Bot - Main Entry Point

The Complete 5-Bot Fleet:
- Bot 1: CorrelationScanner (Rust) - DAG Monotonicity Violations
- Bot 2: NegRiskMiner (Rust) - Unity Constraint Arbitrage
- Bot 3: ResolutionSniper (Python) - UMA Oracle Liveness
- Bot 4: Vulture (Rust) - Zombie Market Maker + Rebate Farming
- Bot 5: SemanticSentinel (Python) - LLM News Latency Arbitrage

Pre-Production Mode:
- RiskManager enforces $50 daily loss limit, $20 max order size
- RateLimiter enforces 50 req/10s with exponential backoff
- Bot-specific constraints: atomic orders, gas checks, post_only
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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


async def run_pre_production(dry_run: bool = True):
    """
    Run in Pre-Production mode with Zero-Trust Safety Module.
    
    Zero-Trust guarantees:
    - Wallet verification: MATIC > 1.0, USDC > $50
    - RiskManager: P&L limits, fat finger protection, latency guard
    - RateLimiter: Dual-bucket (Market Data + Orders)
    - Bot-specific constraints: FOK atomic, gas checks, dispute buffer, post_only
    """
    from strategy_layer.risk_manager import RiskManager
    from strategy_layer.rate_limiter import RateLimiter, BucketType
    from strategy_layer.executors import (
        AtomicPairExecutor, 
        GasAwareExecutor, 
        ResolutionSniperExecutor,
        VultureExecutor,
        TakerFeePanicError,
    )
    
    print("\n" + "="*60)
    print("🔒 ZERO-TRUST SAFETY MODULE ACTIVE")
    print("="*60)
    
    # === STEP 1: Initialize RiskManager FIRST ===
    print("\n[1/6] Initializing Risk Manager (The Gatekeeper)...")
    risk_manager = RiskManager.get_instance()
    print(f"  ✓ RiskManager initialized")
    print(f"    • Max daily loss: ${risk_manager.MAX_DAILY_LOSS:.2f}")
    print(f"    • Max order size: ${risk_manager.MAX_ORDER_SIZE:.2f}")
    print(f"    • Fat finger threshold: {risk_manager.FAT_FINGER_THRESHOLD*100}%")
    print(f"    • Max latency: {risk_manager.MAX_LATENCY_MS}ms")
    print(f"    • Kill switch: {risk_manager.KILL_SWITCH_DURATION // 60} minutes")
    
    # === STEP 2: Verify Wallet Balances ===
    print("\n[2/6] Verifying wallet balances...")
    wallet_ok, wallet_msg = await risk_manager.verify_wallet()
    if not wallet_ok:
        print(f"\n❌ WALLET VERIFICATION FAILED: {wallet_msg}")
        print("   Cannot start trading without sufficient funds.")
        print(f"   Required: {risk_manager.MIN_MATIC_BALANCE} MATIC, ${risk_manager.MIN_USDC_BALANCE} USDC")
        if not dry_run:
            return False
        print("   (Continuing in dry-run mode despite wallet check)")
    else:
        print(f"  ✓ Wallet verified: {risk_manager._wallet_matic:.4f} MATIC, ${risk_manager._wallet_usdc:.2f} USDC")
    
    # === STEP 3: Check API Latency ===
    print("\n[3/6] Checking API latency...")
    latency_ms, is_healthy = await risk_manager.check_api_latency()
    if is_healthy:
        print(f"  ✓ API latency: {latency_ms:.0f}ms (healthy)")
    else:
        print(f"  ⚠️ API latency: {latency_ms:.0f}ms (degraded - HFT bots paused)")
    
    # === STEP 4: Initialize Rate Limiter ===
    print("\n[4/6] Initializing Dual-Bucket Rate Limiter...")
    rate_limiter = RateLimiter.get_instance()
    print(f"  ✓ RateLimiter initialized")
    print(f"    • Market Data: {rate_limiter.BUCKET_CONFIGS[BucketType.MARKET_DATA].capacity}/10s")
    print(f"    • Orders: {rate_limiter.BUCKET_CONFIGS[BucketType.ORDERS].capacity}/10s")
    print(f"    • Safety margin: 20% below official limits")
    
    # === STEP 5: Check Prerequisites ===
    print("\n[5/6] Checking prerequisites...")
    if not check_rust_module():
        print("\n✗ Rust module check failed")
        return False
    
    if not check_python_bots():
        print("\n✗ Python bots check failed")
        return False
    
    env_ok = check_env_config()
    if not env_ok and not dry_run:
        print("\n✗ Cannot run live without valid credentials")
        return False
    
    # === STEP 6: Initialize Fleet with Executors ===
    print("\n[6/6] Initializing bot fleet with Rules of Engagement...")
    fleet = FleetOrchestrator()
    
    # Initialize bot-specific executors with safety rules
    executors = {
        "bot1": AtomicPairExecutor(dry_run=dry_run),
        "bot2": GasAwareExecutor(dry_run=dry_run),
        "bot3": ResolutionSniperExecutor(dry_run=dry_run),
        "bot4": VultureExecutor(dry_run=dry_run),
    }
    print(f"  ✓ Bot 1: FOK Atomic Batch (no legging)")
    print(f"  ✓ Bot 2: Gas Check (min profit: ${executors['bot2'].MIN_NET_PROFIT})")
    print(f"  ✓ Bot 3: 1-Hour Dispute Buffer")
    print(f"  ✓ Bot 4: POST_ONLY + Taker Fee Panic")
    
    # Setup graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler(sig, frame):
        print("\n\n🛑 Shutdown signal received...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("\n" + "="*60)
    print("ZERO-TRUST TRADING LOOP STARTING")
    print(f"Mode: {'DRY RUN' if dry_run else '🔴 LIVE TRADING'}")
    print("Press Ctrl+C to stop")
    print("="*60 + "\n")
    
    iteration = 0
    
    try:
        while not shutdown_event.is_set():
            iteration += 1
            
            # === Periodic Latency Check (every 30s) ===
            if risk_manager.should_check_latency():
                latency_ms, is_healthy = await risk_manager.check_api_latency()
                if not is_healthy:
                    logger.warning(f"⚠️ API latency: {latency_ms:.0f}ms - HFT bots paused")
            
            # === Master Kill Switch Check ===
            if not risk_manager.is_trading_allowed():
                status = risk_manager.get_status()
                logger.warning(
                    f"⏸️ Trading paused: {status['trading_state']} "
                    f"(P&L: ${status['daily_pnl']:.2f}, Errors: {status['error_count']})"
                )
                await asyncio.sleep(60)
                continue
            
            # === Rate Limit Check (Market Data Bucket) ===
            await rate_limiter.wait_for_market_data()
            
            logger.info(f"\n--- Iteration {iteration} ---")
            logger.info(f"Risk: {risk_manager}")
            logger.info(f"Rate: {rate_limiter}")
            
            try:
                # === Bot 1: Correlation Scanner (HFT - requires low latency) ===
                if risk_manager.is_hft_allowed():
                    violations = fleet.bot1.scan([
                        ("trump-wins-pa", 0.70),
                        ("trump-wins-election", 0.50),
                    ])
                    
                    for v in violations:
                        # Rate limit: order bucket
                        await rate_limiter.wait_for_order()
                        
                        valid, reason = risk_manager.check_order(10.0)
                        if valid:
                            result = await executors["bot1"].execute(v)
                            if result.success:
                                risk_manager.record_pnl(result.pnl)
                                risk_manager.record_order(10.0)
                            else:
                                logger.warning(f"Bot 1: {result.error}")
                else:
                    logger.debug("Bot 1 (HFT) skipped - latency degraded")
                
                # === Bot 2: NegRisk Miner (non-HFT) ===
                opp = fleet.bot2.scan("market-1", [0.55, 0.55], [0.60, 0.60])
                if opp.is_profitable:
                    await rate_limiter.wait_for_order()
                    valid, reason = risk_manager.check_order(15.0)
                    if valid:
                        result = await executors["bot2"].execute(opp)
                        if result.success:
                            risk_manager.record_pnl(result.pnl)
                            risk_manager.record_order(15.0)
                        else:
                            logger.warning(f"Bot 2: {result.error}")
                
                # === Bot 4: Vulture (HFT - requires low latency) ===
                if risk_manager.is_hft_allowed():
                    vulture_opps = fleet.bot4.scan_batch([
                        ("btc-price-105k-15m", "0xbtc", 0.42, 0.58),
                    ])
                    
                    for opp in vulture_opps:
                        await rate_limiter.wait_for_order()
                        valid, reason = risk_manager.check_order(10.0)
                        if valid:
                            try:
                                result = await executors["bot4"].execute(opp)
                                if result.success:
                                    risk_manager.record_pnl(result.pnl)
                                    risk_manager.record_order(10.0)
                                else:
                                    logger.warning(f"Bot 4: {result.error}")
                            except TakerFeePanicError as e:
                                logger.critical(f"🚨 Bot 4 PANIC: {e}")
                                break  # Stop processing, panic triggered
                else:
                    logger.debug("Bot 4 (HFT) skipped - latency degraded")
                
                # Reset backoff on successful iteration
                rate_limiter.reset_backoff()
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                risk_manager.record_error()
                
                # Check if this was a rate limit error
                if "429" in str(e):
                    rate_limiter.handle_429()
            
            # Sleep between iterations (simulate real polling)
            if dry_run:
                # In dry run, just do a few iterations
                if iteration >= 3:
                    logger.info("\nDry run complete (3 iterations)")
                    break
            
            await asyncio.sleep(1)  # 1 second between iterations
    
    except asyncio.CancelledError:
        logger.info("Main loop cancelled")
    
    # === Shutdown Summary ===
    print("\n" + "="*60)
    print("PRE-PRODUCTION SESSION SUMMARY")
    print("="*60)
    
    status = risk_manager.get_status()
    print(f"  Trading State: {status['trading_state']}")
    print(f"  Daily P&L: ${status['daily_pnl']:.2f}")
    print(f"  Total Orders: {status['total_orders_today']}")
    print(f"  Total Volume: ${status['total_volume_today']:.2f}")
    print(f"  API Errors: {status['error_count']}")
    
    rate_status = rate_limiter.get_status()
    print(f"  Total Requests: {rate_status['total_requests']}")
    print(f"  Throttled: {rate_status['total_throttled']}")
    print(f"  429 Errors: {rate_status['consecutive_429s']}")
    
    print("\n" + "="*60)
    print("✓ PRE-PRODUCTION SESSION COMPLETE")
    print("="*60 + "\n")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Polymarket HFT Bot - The Complete 5-Bot Fleet"
    )
    parser.add_argument(
        "--mode",
        choices=["dry-run", "pre-production", "pre-production-live", "shadow", "live-alpha", "live", "scan"],
        default="dry-run",
        help="Operation mode: dry-run, pre-production, shadow (paper trading), live-alpha (training wheels), live, scan"
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
    elif args.mode == "pre-production":
        print("\n🧪 PRE-PRODUCTION MODE (Dry Run with Risk Management)")
        success = asyncio.run(run_pre_production(dry_run=True))
        sys.exit(0 if success else 1)
    elif args.mode == "pre-production-live":
        print("\n🔴 PRE-PRODUCTION MODE (LIVE TRADING)")
        print("\n⚠️  WARNING: This will execute REAL trades!")
        confirm = input("Type 'CONFIRM' to proceed: ")
        if confirm != "CONFIRM":
            print("Aborted.")
            sys.exit(1)
        success = asyncio.run(run_pre_production(dry_run=False))
        sys.exit(0 if success else 1)
    elif args.mode == "shadow":
        print("\n👻 SHADOW MODE (Paper Trading)")
        success = asyncio.run(run_shadow_mode())
        sys.exit(0 if success else 1)
    elif args.mode == "live-alpha":
        print("\n🎓 LIVE ALPHA MODE (Training Wheels)")
        success = asyncio.run(run_live_alpha())
        sys.exit(0 if success else 1)
    elif args.mode == "live":
        print("⚠ Legacy live mode not implemented")
        print("  Use --mode live-alpha for live trading with training wheels")
        sys.exit(1)
    elif args.mode == "scan":
        print("⚠ Scan mode not implemented yet")
        sys.exit(1)


async def run_shadow_mode():
    """Run in Shadow (Paper Trading) mode - no real money moves."""
    from strategy_layer.shadow_engine import ShadowExchange
    from utils.notifier import get_notifier
    
    # Initialize shadow exchange
    shadow = ShadowExchange()
    
    # Initialize Discord notifier and send startup message
    notifier = get_notifier()
    await notifier.on_startup(mode="shadow")
    
    print("\n👻 Shadow Mode Active - All trades will be simulated")
    print("   Trades logged to: logs/shadow_trades.csv")
    print("   Press Ctrl+C to stop and generate report\n")
    
    # Run the fleet with shadow exchange
    try:
        fleet = FleetOrchestrator()
        
        iteration = 0
        while True:
            iteration += 1
            logger.info(f"--- Shadow Iteration {iteration} ---")
            
            # Simulate Bot 2 NegRisk trade
            opp = fleet.bot2.scan("market-1", [0.55, 0.55], [0.60, 0.60])
            if opp.is_profitable:
                await shadow.place_order(
                    bot_name="NegRiskMiner",
                    market_slug="mock-market",
                    condition_id=opp.condition_id,
                    side="BUY",
                    price=0.55,
                    size=10.0,
                    expected_profit=0.08,
                    gas_cost=0.02,
                )
                
                # Send Discord notification for the trade
                await notifier.on_trade(
                    side="BUY",
                    market="mock-market [SHADOW]",
                    price=0.55,
                    size=10.0,
                    profit=0.06,  # net profit after gas
                    bot_name="NegRiskMiner",
                )
            
            await asyncio.sleep(5)  # 5 seconds between iterations
            
            # Stop after 10 iterations in demo
            if iteration >= 10:
                break
                
    except KeyboardInterrupt:
        print("\n\nShadow session interrupted.")
    finally:
        shadow.print_report()
        
        # Send daily summary to Discord
        stats = shadow.get_stats()
        await notifier.on_daily_summary(
            total_trades=stats.total_trades,
            pnl=stats.total_profit,
            wins=stats.total_wins,
            losses=stats.total_losses,
        )
        await notifier.on_shutdown(reason="Shadow session complete")
    
    return True


async def run_live_alpha():
    """Run in Live Alpha mode with strict training wheels."""
    from config.alpha_settings import print_alpha_config, apply_alpha_limits, ALPHA_CONFIG
    from utils.startup_check import perform_safety_checks
    from utils.notifier import get_notifier
    from strategy_layer.risk_manager import RiskManager
    
    # Print Alpha configuration
    print_alpha_config()
    
    # Run pre-flight checks
    success, issues = await perform_safety_checks()
    if not success:
        print("\n❌ Pre-flight checks failed. Cannot start.")
        return False
    
    # Initialize RiskManager with Alpha limits
    rm = RiskManager.get_instance()
    apply_alpha_limits(rm)
    rm._wallet_verified = True  # Mark verified after checks pass
    
    # Send startup notification
    notifier = get_notifier()
    await notifier.on_startup(mode="live-alpha")
    
    print("\n🎓 LIVE ALPHA MODE - Training Wheels Active")
    print(f"   Max Position: ${ALPHA_CONFIG.MAX_POSITION_SIZE:.2f}")
    print(f"   Daily Stop: ${ALPHA_CONFIG.DAILY_STOP_LOSS:.2f}")
    print(f"   Kill Switch File: {ALPHA_CONFIG.KILL_SWITCH_FILE}")
    print("\n   Press Ctrl+C to stop\n")
    
    # Start kill switch monitor
    kill_switch_task = asyncio.create_task(monitor_kill_switch())
    
    try:
        # Run pre-production with live=True
        await run_pre_production(dry_run=False)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        kill_switch_task.cancel()
        await notifier.on_shutdown("User stop")
    
    return True


async def monitor_kill_switch(check_interval: float = 1.0):
    """Monitor for KILL_SWITCH.txt file and trigger emergency stop."""
    from config.alpha_settings import ALPHA_CONFIG
    from utils.notifier import get_notifier
    
    kill_file = ALPHA_CONFIG.KILL_SWITCH_FILE
    
    while True:
        if os.path.exists(kill_file):
            logger.critical("🚨 KILL SWITCH FILE DETECTED!")
            
            # Notify
            notifier = get_notifier()
            await notifier.on_kill_switch()
            
            # Cancel all orders (in real implementation)
            print("\n" + "!" * 60)
            print("🚨 KILL SWITCH ACTIVATED - EMERGENCY STOP")
            print("!" * 60 + "\n")
            
            # Force exit
            os._exit(1)
        
        await asyncio.sleep(check_interval)


if __name__ == "__main__":
    main()

