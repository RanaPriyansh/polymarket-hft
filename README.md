# 🦅 Polymarket HFT Bot Fleet

> **5 Autonomous Bots. 1 Mission. Exploit Every Edge.**

A high-frequency trading system for [Polymarket](https://polymarket.com) prediction markets, built with **Rust** (core) + **Python** (orchestration) via PyO3 FFI for microsecond-level performance.

<div align="center">

![Rust](https://img.shields.io/badge/Rust-000000?style=for-the-badge&logo=rust&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Polygon](https://img.shields.io/badge/Polygon-8247E5?style=for-the-badge&logo=polygon&logoColor=white)

</div>

---

## 🎯 The Fleet

| Bot | Name | Strategy | Language |
|-----|------|----------|----------|
| **#1** | [CorrelationScanner](#-bot-1-correlationscanner) | DAG Monotonicity Violations | Rust |
| **#2** | [NegRiskMiner](#-bot-2-negriskminer) | Unity Constraint Arbitrage | Rust |
| **#3** | [ResolutionSniper](#-bot-3-resolutionsniper) | UMA Oracle Liveness | Python |
| **#4** | [Vulture](#-bot-4-vulture) | Zombie MM + Rebate Farming | Rust |
| **#5** | [SemanticSentinel](#-bot-5-semanticsentinel) | LLM News Latency Arbitrage | Python |

---

## ⚡ Bot 1: CorrelationScanner

**Strategy: DAG Monotonicity Violations**

Markets are connected. If *"Trump wins Pennsylvania"* implies *"Trump wins Election"*, then mathematically:

```
P(Election) ≥ P(Pennsylvania)
```

When this rule is violated, free money exists.

### How It Works

```rust
// Build the correlation graph
graph.add_edge("trump-wins-pa", "trump-wins-election", 1.0);
graph.add_edge("fed-hikes-jan", "fed-hikes-q1", 1.0);

// Scan for violations
let violations = graph.scan(&prices);
// → "trump-wins-pa: 0.70 > trump-wins-election: 0.50"
// → Action: BUY election, SELL pennsylvania
```

### Edge Type
- **Parent** (subset event) priced higher than **Child** (superset event)
- **Trade**: Long the underpriced child, short the overpriced parent

---

## 💎 Bot 2: NegRiskMiner

**Strategy: Unity Constraint Arbitrage (Mint-and-Sell / Buy-and-Merge)**

In mutually exclusive markets, all outcomes MUST sum to $1.00. When they don't:

| Condition | Strategy | Action |
|-----------|----------|--------|
| `ΣBids > 1.0 + fees` | **Mint-and-Sell** | Mint shares at $1, sell to all bidders |
| `ΣAsks < 1.0 - fees` | **Buy-and-Merge** | Buy all outcomes, redeem for $1 |

### How It Works

```python
# Market with YES @ 0.55 bid, NO @ 0.55 bid
# ΣBids = 1.10 > 1.02 (threshold)
opportunity = negrisk.scan("market-1", [0.55, 0.55], [0.60, 0.60])
# → MintAndSell: profit = 800bps
```

### Edge Type
- Structural arbitrage from pricing inefficiencies
- Risk-free execution when fees are covered

---

## 🎯 Bot 3: ResolutionSniper

**Strategy: UMA Oracle Liveness Period Exploitation**

When a market enters the 2-hour UMA Optimistic Oracle dispute window, the outcome is *proposed* but not *finalized*. If external sources confirm the answer, the market is mispriced.

### How It Works

```python
# Market: "Did Fed raise rates?"
# Proposed answer: YES
# Market price: 0.85 (should be ~1.0 if YES is confirmed)

sniper.add_pending(
    condition_id="0xabc...",
    proposed_answer="yes",
    liveness_ends_at=timestamp + 3600,
    current_price=0.85,
)

opportunities = await sniper.scan()
# → BUY @ 0.85, expected payout: $1.00
# → Expected profit: 1765bps
```

### Edge Type
- Information asymmetry during liveness period
- External oracle confirmation vs market price

---

## 🦅 Bot 4: Vulture

**Strategy: Zombie Market Maker + Crypto Rebate Farming**

Two modes of operation:

### Mode 1: Spread Capture
Wide-spread markets are liquidity deserts. Vulture quotes inside the spread to extract passive income.

### Mode 2: Maker Rebate Farming (15-min Crypto)
Polymarket's killer feature: **maker rebates on 15-minute crypto markets**.

```python
# BTC 15-min market with wide spread
vulture.scan("btc-price-105k-15m", "0xbtc", bid=0.42, ask=0.58)
# → spread: 160bps
# → POST_ONLY order @ 0.46
# → EARN REBATE on fill 🔥
```

| Market Type | Order Type | Fee |
|-------------|------------|-----|
| 15-min Crypto | **POST_ONLY (Maker)** | **−REBATE** |
| Other Markets | GTC (Taker) | +Fee |

### Edge Type
- Market making in illiquid markets
- Collecting rebates as the house

---

## 🧠 Bot 5: SemanticSentinel

**Strategy: LLM-Powered News Latency Arbitrage**

News moves markets. The Sentinel uses **Google Gemini** to parse headlines faster than humans can read them.

### Target Keywords
```python
TRIGGER_KEYWORDS = {
    "resign": ["resignation", "stepping down"],
    "invade": ["invasion", "military action", "declares war"],
    "acquire": ["acquisition", "merger", "takeover"],
    "ban": ["banned", "prohibition", "outlawed"],
    # ... 20+ keyword families
}
```

### How It Works

```python
sentinel.register_market("trump-resignation", ["trump", "resign"])
sentinel.register_market("fed-rate-hike", ["fed", "rate", "powell"])

event = await sentinel.process_headline(
    "BREAKING: Fed announces surprise rate hike of 50bps"
)
# → Keywords: ["rate", "fed"]
# → Sentiment: STRONGLY_BEARISH
# → Action: SELL fed-rate-hike with HIGH urgency
```

### Edge Type
- Beating manual traders to news
- LLM sentiment analysis in <100ms

---

## 🏗️ Architecture

```
polymarket-hft/
├── rust_core/                 # High-performance Rust engine
│   └── src/
│       ├── graph.rs           # Bot 1: DAG Scanner
│       ├── negrisk.rs         # Bot 2: Unity Miner
│       ├── vulture.rs         # Bot 4: Market Maker
│       ├── orderbook.rs       # Orderbook infrastructure
│       ├── signer.rs          # EIP-712 transaction signing
│       └── lib.rs             # PyO3 FFI exports
├── strategy_layer/
│   └── bots/
│       ├── resolution_sniper.py   # Bot 3: Oracle Sniper
│       ├── semantic_sentinel.py   # Bot 5: News Arbitrage
│       └── correlation_scanner.py # Extra analysis
├── config/                    # Environment & settings
├── main.py                    # Fleet orchestrator
└── requirements.txt
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Rust (latest stable)
- Polymarket API credentials
- (Optional) Google Gemini API key for Bot 5

### Installation

```bash
# Clone
git clone https://github.com/RanaPriyansh/polymarket-hft.git
cd polymarket-hft

# Virtual environment
python -m venv venv
source venv/bin/activate

# Python dependencies
pip install -r requirements.txt

# Compile Rust core with PyO3
cd rust_core
maturin develop --release
cd ..

# Configure
cp .env.example .env
# Edit .env with your credentials
```

### Dry Run

```bash
python main.py --mode dry-run
```

```
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

[1/5] Checking Rust core module... ✓
[2/5] Checking Python bots... ✓
[3/5] Checking environment configuration... ✓
[4/5] Initializing bot fleet... ✓
[5/5] Running bot simulations... ✓

DRY RUN COMPLETE - ALL SYSTEMS OPERATIONAL
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `PRIVATE_KEY` | Wallet private key for signing | ✅ |
| `WALLET_ADDRESS` | Your wallet address | ✅ |
| `POLY_API_KEY` | Polymarket CLOB API key | ✅ |
| `POLY_API_SECRET` | Polymarket CLOB API secret | ✅ |
| `POLY_API_PASSPHRASE` | Polymarket CLOB passphrase | ✅ |
| `GEMINI_API_KEY` | Google Gemini for Bot 5 | ❌ |

---

## ⚠️ Disclaimer

This software is for **educational and research purposes only**.

- Trading prediction markets carries substantial risk
- Past performance does not guarantee future results
- The author is not responsible for any financial losses
- Always comply with local laws and Polymarket's Terms of Service

---

## 📜 License

MIT © 2026 Priyansh Rana

---

<div align="center">

**Built for speed. Designed for alpha.**

*If you found this useful, star the repo!* ⭐

</div>
