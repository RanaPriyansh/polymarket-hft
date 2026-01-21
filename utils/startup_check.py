#!/usr/bin/env python3
"""
Pre-Flight Startup Checks for Live Trading

Verifies all safety conditions before starting live trading:
1. Wallet balance (< $100 USDC for hot wallet safety)
2. Gas balance (> 1.0 MATIC)
3. API latency (< 300ms)
4. RiskManager status (initialized and clean)

Usage:
    from utils.startup_check import perform_safety_checks
    success, issues = await perform_safety_checks()
"""

import asyncio
import logging
import os
import time
from typing import Tuple, List

import httpx

logger = logging.getLogger(__name__)


async def check_wallet_balance() -> Tuple[bool, str, dict]:
    """
    Verify wallet has appropriate balance:
    - USDC < $100 (safety: don't keep excess in hot wallet)
    - MATIC > 1.0 (need gas for transactions)
    
    Returns:
        Tuple of (passed, message, balances)
    """
    wallet_address = os.getenv("WALLET_ADDRESS", "")
    polygon_rpc = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
    
    if not wallet_address:
        return False, "WALLET_ADDRESS not configured", {}
    
    balances = {"matic": 0.0, "usdc": 0.0}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check MATIC balance
            resp = await client.post(polygon_rpc, json={
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [wallet_address, "latest"],
                "id": 1
            })
            result = resp.json()
            if "result" in result:
                balances["matic"] = int(result["result"], 16) / 1e18
            
            # Check USDC balance
            usdc_contract = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
            data = f"0x70a08231000000000000000000000000{wallet_address[2:]}"
            
            resp = await client.post(polygon_rpc, json={
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [{"to": usdc_contract, "data": data}, "latest"],
                "id": 2
            })
            result = resp.json()
            if "result" in result and result["result"] != "0x":
                balances["usdc"] = int(result["result"], 16) / 1e6
    except Exception as e:
        return False, f"Failed to check wallet: {e}", balances
    
    # Validate balances
    issues = []
    
    if balances["matic"] < 1.0:
        issues.append(f"MATIC balance {balances['matic']:.4f} < 1.0 (need gas)")
    
    if balances["usdc"] > 100.0:
        issues.append(f"USDC balance ${balances['usdc']:.2f} > $100 (hot wallet too large)")
    
    if balances["usdc"] < 10.0:
        issues.append(f"USDC balance ${balances['usdc']:.2f} < $10 (insufficient for trading)")
    
    if issues:
        return False, "; ".join(issues), balances
    
    return True, f"Wallet OK: {balances['matic']:.2f} MATIC, ${balances['usdc']:.2f} USDC", balances


async def check_api_latency() -> Tuple[bool, str, float]:
    """
    Ping Polymarket API and verify latency < 300ms.
    
    Returns:
        Tuple of (passed, message, latency_ms)
    """
    max_latency_ms = 300.0
    
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://clob.polymarket.com/time")
            resp.raise_for_status()
        latency_ms = (time.time() - start) * 1000
        
        if latency_ms > max_latency_ms:
            return False, f"API latency {latency_ms:.0f}ms > {max_latency_ms}ms (too slow)", latency_ms
        
        return True, f"API latency: {latency_ms:.0f}ms", latency_ms
    except Exception as e:
        return False, f"API ping failed: {e}", 9999.0


def check_risk_manager() -> Tuple[bool, str]:
    """
    Verify RiskManager is initialized and in clean state.
    
    Returns:
        Tuple of (passed, message)
    """
    try:
        from strategy_layer.risk_manager import RiskManager
        
        rm = RiskManager.get_instance()
        
        # Check if it's in a clean state
        status = rm.get_status()
        
        issues = []
        
        if status["daily_pnl"] != 0:
            issues.append(f"P&L not reset: ${status['daily_pnl']:.2f}")
        
        if status["trading_state"] != "active":
            issues.append(f"Trading state: {status['trading_state']}")
        
        if status["kill_switch_active"]:
            issues.append("Kill switch is active")
        
        if status["error_count"] > 0:
            issues.append(f"Errors in window: {status['error_count']}")
        
        if issues:
            return False, "; ".join(issues)
        
        return True, "RiskManager initialized and clean"
        
    except ImportError:
        return False, "RiskManager not available"
    except Exception as e:
        return False, f"RiskManager error: {e}"


def check_environment_variables() -> Tuple[bool, str]:
    """
    Verify required environment variables are set.
    
    Returns:
        Tuple of (passed, message)
    """
    required = [
        "WALLET_ADDRESS",
        "PRIVATE_KEY",
        "POLY_API_KEY",
        "POLY_API_SECRET",
        "POLY_API_PASSPHRASE",
    ]
    
    missing = []
    for var in required:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        return False, f"Missing env vars: {', '.join(missing)}"
    
    return True, "All required environment variables set"


def check_kill_switch_file() -> Tuple[bool, str]:
    """
    Ensure KILL_SWITCH.txt does not exist at startup.
    
    Returns:
        Tuple of (passed, message)
    """
    kill_switch_file = "KILL_SWITCH.txt"
    
    if os.path.exists(kill_switch_file):
        return False, f"KILL_SWITCH.txt exists - remove it to start trading"
    
    return True, "No kill switch file found"


def check_discord_webhook() -> dict:
    """
    Check if Discord webhook is configured.
    
    This is optional - bot can run without Discord notifications.
    Returns status dict instead of pass/fail.
    """
    try:
        from utils.notifier import DiscordNotifier
        notifier = DiscordNotifier()
        return notifier.get_status()
    except ImportError:
        return {
            "enabled": False,
            "configured": False,
            "webhook_url_set": False,
            "error": "Notifier module not available"
        }
    except Exception as e:
        return {
            "enabled": False,
            "configured": False,
            "webhook_url_set": False,
            "error": str(e)
        }


async def perform_safety_checks() -> Tuple[bool, List[str]]:
    """
    Run all pre-flight safety checks.
    
    Returns:
        Tuple of (all_passed, list_of_issues)
    """
    print("\n" + "=" * 60)
    print("🔍 PRE-FLIGHT SAFETY CHECKS")
    print("=" * 60 + "\n")
    
    all_passed = True
    issues = []
    
    # Check 1: Environment Variables
    print("  [1/5] Checking environment variables...")
    passed, msg = check_environment_variables()
    if passed:
        print(f"        ✅ {msg}")
    else:
        print(f"        ❌ {msg}")
        all_passed = False
        issues.append(msg)
    
    # Check 2: Kill Switch File
    print("  [2/5] Checking kill switch file...")
    passed, msg = check_kill_switch_file()
    if passed:
        print(f"        ✅ {msg}")
    else:
        print(f"        ❌ {msg}")
        all_passed = False
        issues.append(msg)
    
    # Check 3: Wallet Balance
    print("  [3/5] Checking wallet balance...")
    passed, msg, balances = await check_wallet_balance()
    if passed:
        print(f"        ✅ {msg}")
    else:
        print(f"        ❌ {msg}")
        all_passed = False
        issues.append(msg)
    
    # Check 4: API Latency
    print("  [4/5] Checking API latency...")
    passed, msg, latency = await check_api_latency()
    if passed:
        print(f"        ✅ {msg}")
    else:
        print(f"        ❌ {msg}")
        all_passed = False
        issues.append(msg)
    
    # Check 5: RiskManager
    print("  [5/5] Checking RiskManager...")
    passed, msg = check_risk_manager()
    if passed:
        print(f"        ✅ {msg}")
    else:
        print(f"        ❌ {msg}")
        all_passed = False
        issues.append(msg)
    
    # Optional Check: Discord Notifications
    print("\n  [Optional] Checking Discord webhook...")
    discord_status = check_discord_webhook()
    if discord_status["configured"]:
        print(f"        ✅ Discord notifications enabled")
    else:
        print(f"        ⚠️  Discord not configured (notifications disabled)")
        print(f"           Add DISCORD_WEBHOOK_URL to .env to enable")
    
    print("\n" + "-" * 60)
    
    if all_passed:
        print("✅ ALL CHECKS PASSED - Safe to proceed with live trading")
    else:
        print("❌ CHECKS FAILED - Resolve issues before trading")
        print(f"   Issues: {len(issues)}")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
    
    print("=" * 60 + "\n")
    
    return all_passed, issues


if __name__ == "__main__":
    # Run checks directly
    import asyncio
    asyncio.run(perform_safety_checks())
