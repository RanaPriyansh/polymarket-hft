# 🦅 Polymarket HFT Bot Fleet - Complete Project Documentation

> **Last Updated:** January 17, 2026  
> **Author:** Priyansh Rana  
> **Status:** Development (Dry-Run Operational)

---

## 📋 Executive Summary

A **high-frequency trading system** for [Polymarket](https://polymarket.com) prediction markets. The system consists of **5 autonomous bots**, each targeting a different market inefficiency. The architecture uses a **Rust core** for performance-critical operations with **Python orchestration** via PyO3 FFI bindings.

### Key Stats
- **Bots:** 5 autonomous strategies
- **Languages:** Rust (performance core) + Python (orchestration + LLM)
- **Target Platform:** Polymarket CLOB (Central Limit Order Book)
- **Blockchain:** Polygon (L2 Ethereum)
- **Status:** Dry-run verified, pending live deployment

---

## 🤖 The 5-Bot Fleet

### Bot 1: CorrelationScanner (Rust)
**Strategy:** DAG Monotonicity Violations

Detects when correlated markets are mispriced relative to each other. Uses a Directed Acyclic Graph (DAG) to model market correlations.

**Logic:**
- If "Trump wins Pennsylvania" → "Trump wins Election" (correlation=1.0)
- Then P(Election) ≥ P(Pennsylvania) MUST hold
- If violated: Buy the underpriced child, Sell the overpriced parent

**Implementation:** `rust_core/src/graph.rs`
```rust
// Key exports
pub struct Graph { ... }
pub struct Violation { ... }
```

**Python Usage:**
```python
from rust_core import Graph
graph = Graph(min_violation_bps=50.0)
graph.add_edge("trump-wins-pa", "trump-wins-election", 1.0)
violations = graph.scan([("trump-wins-pa", 0.70), ("trump-wins-election", 0.50)])
```

---

### Bot 2: NegRiskMiner (Rust)
**Strategy:** Unity Constraint Arbitrage

Exploits the mathematical constraint that mutually exclusive outcomes MUST sum to $1.00.

**Logic:**
- **Mint-and-Sell:** If ΣBids > 1.0 + fees → Mint shares for $1, sell to all bidders
- **Buy-and-Merge:** If ΣAsks < 1.0 - fees → Buy all outcomes, merge for $1

**Implementation:** `rust_core/src/negrisk.rs`
```rust
// Key exports
pub struct NegRisk { ... }
pub struct NegRiskConfig { ... }
pub struct Opportunity { ... }
```

**Python Usage:**
```python
from rust_core import NegRisk
miner = NegRisk()
opp = miner.scan("market-id", bids=[0.55, 0.55], asks=[0.60, 0.60])
# Returns: Opportunity(MintAndSell: Σbids=1.10 > 1.0)
```

---

### Bot 3: ResolutionSniper (Python)
**Strategy:** UMA Oracle Liveness Exploitation

Snipes markets during the 2-hour UMA Optimistic Oracle liveness period before resolution is finalized.

**Logic:**
1. Listen for `QuestionInitialized` events on CTF Adapter
2. Compare proposed answer to external oracles/news
3. If market trades at <0.99 but answer is confirmed YES → BUY
4. If market trades at >0.01 but answer is confirmed NO → SELL

**Implementation:** `strategy_layer/bots/resolution_sniper.py`
```python
class ResolutionSniper:
    ctf_adapter: str = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
    min_confidence: float = 0.90
    min_profit_bps: float = 100.0
```

**Key Methods:**
- `add_pending()` - Track markets in liveness period
- `scan()` - Find sniper opportunities
- `check_external_oracle()` - Verify resolution with external data

---

### Bot 4: Vulture (Rust)
**Strategy:** Zombie Market Maker + Rebate Farming

Makes markets in wide-spread, illiquid markets. Special focus on 15-minute crypto prediction markets to farm **maker rebates**.

**Logic:**
- Scan for markets with spreads between 50-500 bps
- Quote inside the spread (capture edge fraction)
- On 15-min crypto markets: Force POST_ONLY orders to earn rebates

**Implementation:** `rust_core/src/vulture.rs`
```rust
// Key exports
pub struct Vulture { ... }
pub struct VultureConfig { ... }
pub struct MarketOpportunity { ... }
```

**Crypto Market Detection:**
```rust
fn is_15min_crypto(&self, market_slug: &str) -> bool {
    // Detects: btc-15m, eth-15-min, etc.
}
```

**Python Usage:**
```python
from rust_core import Vulture
vulture = Vulture()
opps = vulture.scan_batch([
    ("btc-price-105k-15m", "0xbtc", 0.42, 0.58),
    ("trump-wins-2024", "0xtrump", 0.48, 0.53),
])
```

---

### Bot 5: SemanticSentinel (Python + LLM)
**Strategy:** News Latency Arbitrage

Uses **Google Gemini LLM** to parse breaking news headlines and front-run manual traders.

**Logic:**
1. Monitor news feeds for trigger keywords
2. Use Gemini to analyze sentiment and relevance
3. Map headlines to registered Polymarket markets
4. Generate trade signals before humans can react

**Implementation:** `strategy_layer/bots/semantic_sentinel.py`
```python
class SemanticSentinel:
    model_name: str = "gemini-2.0-flash"
    min_confidence: float = 0.75
```

**Trigger Keywords:**
- Political: resign, impeach, quit, fired
- Military: invade, attack, war, strike
- Corporate: acquire, merge, bankrupt, IPO
- Regulatory: ban, approve
- Natural: earthquake, hurricane

**Python Usage:**
```python
sentinel = SemanticSentinel()
sentinel.register_market("trump-resignation", ["trump", "resign", "president"])
event = await sentinel.process_headline("BREAKING: Trump considering resignation")
signals = await sentinel.generate_signals(event)
```

---

## 🏗️ Architecture

```
polymarket-hft/
├── main.py                    # Entry point & orchestrator
├── requirements.txt           # Python dependencies
├── .env                       # Secrets (not in git)
├── .env.example               # Template for secrets
│
├── config/
│   ├── __init__.py
│   └── settings.py            # Configuration management
│
├── rust_core/                 # Performance-critical Rust code
│   ├── Cargo.toml             # Rust dependencies
│   └── src/
│       ├── lib.rs             # PyO3 module exports
│       ├── graph.rs           # Bot 1: Correlation Scanner
│       ├── negrisk.rs         # Bot 2: NegRisk Miner
│       ├── vulture.rs         # Bot 4: Vulture MM
│       ├── orderbook.rs       # Shared orderbook management
│       └── signer.rs          # Transaction signing
│
├── strategy_layer/            # Python strategy code
│   ├── __init__.py
│   ├── bots/
│   │   ├── __init__.py
│   │   ├── resolution_sniper.py  # Bot 3
│   │   └── semantic_sentinel.py  # Bot 5
│   └── utils/
│       └── ...
│
└── venv/                      # Python virtual environment
```

### Rust → Python Bridge (PyO3)

The Rust core is compiled to a native Python module using [PyO3](https://pyo3.rs/) and [Maturin](https://github.com/PyO3/maturin).

**Build Command:**
```bash
cd rust_core && maturin develop --release
```

**Exposed Classes:**
```python
from rust_core import (
    # Bot 1
    Graph, Violation,
    # Bot 2
    NegRisk, NegRiskConfig, Opportunity,
    # Bot 4
    Vulture, VultureConfig, MarketOpportunity,
    # Infrastructure
    PyOrderbook, PyOrderbookManager,
    PySigner,
)
```

---

## 🔐 Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
# Required: Polymarket CLOB API Credentials
POLY_API_KEY=your_api_key
POLY_API_SECRET=your_api_secret
POLY_API_PASSPHRASE=your_passphrase

# Required: Wallet for signing
PRIVATE_KEY=0x...your_private_key
WALLET_ADDRESS=0x...your_wallet

# Optional: Polygon RPC
POLYGON_RPC=https://polygon-rpc.com

# Optional: LLM for Bot 5
ANTHROPIC_API_KEY=sk-...

# Optional: News feeds for Bot 5
TWITTER_BEARER_TOKEN=...
```

---

## 📦 Dependencies

### Python (requirements.txt)
```
py-clob-client>=0.17.0    # Polymarket SDK
python-dotenv>=1.0.0
httpx>=0.25.0
websockets>=12.0
pydantic>=2.5.0
numpy>=1.26.0
scipy>=1.11.0
google-genai>=1.0.0       # Gemini LLM
eth-account>=0.10.0
web3>=6.15.0
maturin>=1.4.0            # Rust→Python build
```

### Rust (Cargo.toml)
```toml
pyo3 = { version = "0.20", features = ["extension-module"] }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
thiserror = "1.0"
hex = "0.4"
sha3 = "0.10"
```

---

## 🚀 Quick Start

### 1. Clone & Setup
```bash
cd /Users/priyansh/Documents/polmarket-bots/polymarket-hft
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Build Rust Core
```bash
cd rust_core
maturin develop --release
cd ..
```

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 4. Dry Run
```bash
python main.py --mode dry-run
```

### 5. Expected Output
```
╔═══════════════════════════════════════════════════════════╗
║   🦅 POLYMARKET HFT BOT - 5-BOT FLEET                    ║
╚═══════════════════════════════════════════════════════════╝

[1/5] Checking Rust core module...
✓ Rust core module loaded successfully

[2/5] Checking Python bots...
✓ Python bots loaded successfully

[3/5] Checking environment configuration...
✓ Environment configuration valid

[4/5] Initializing bot fleet...
  ✓ Bot 1: CorrelationScanner initialized
  ✓ Bot 2: NegRiskMiner initialized
  ✓ Bot 3: ResolutionSniper initialized
  ✓ Bot 4: Vulture initialized
  ✓ Bot 5: SemanticSentinel initialized

[5/5] Running bot simulations...
  [Bot 1: CorrelationScanner - DAG Monotonicity]
    Found 1 monotonicity violations
    
DRY RUN COMPLETE - ALL SYSTEMS OPERATIONAL
```

---

## ☁️ Deployment (AWS)

### Recommended Setup

| Component | Recommendation |
|-----------|---------------|
| **Instance** | EC2 t3.medium or c6i.large |
| **Region** | us-east-1 (proximity to Polymarket) |
| **OS** | Ubuntu 22.04 LTS |
| **Storage** | 20GB gp3 SSD |

### Deployment Steps

1. **Provision EC2 Instance**
2. **Install Dependencies:**
   ```bash
   sudo apt update
   sudo apt install -y python3.11 python3.11-venv rustc cargo
   ```

3. **Clone & Build:**
   ```bash
   git clone <your-repo>
   cd polymarket-hft
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cd rust_core && maturin develop --release && cd ..
   ```

4. **Configure as systemd Service:**
   ```bash
   sudo nano /etc/systemd/system/polymarket-bot.service
   ```
   ```ini
   [Unit]
   Description=Polymarket HFT Bot Fleet
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/polymarket-hft
   ExecStart=/home/ubuntu/polymarket-hft/venv/bin/python main.py --mode live
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

5. **Enable & Start:**
   ```bash
   sudo systemctl enable polymarket-bot
   sudo systemctl start polymarket-bot
   ```

---

## 📊 API References

### Polymarket CLOB API
- **Base URL:** `https://clob.polymarket.com`
- **Docs:** https://docs.polymarket.com/
- **SDK:** `py-clob-client`

### Gamma Markets API (Market Discovery)
- **Base URL:** `https://gamma-api.polymarket.com`
- **Use:** Finding active markets, slugs, condition IDs

### UMA Oracle
- **CTF Adapter:** `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296`
- **Liveness Period:** 2 hours
- **Use:** Resolution sniping (Bot 3)

---

## ⚠️ Risk Warnings

1. **Financial Risk:** HFT on prediction markets carries significant risk of loss
2. **Smart Contract Risk:** Polymarket runs on Polygon; smart contract bugs possible
3. **Regulatory Risk:** Prediction markets may have legal restrictions in your jurisdiction
4. **API Risk:** Polymarket may change APIs or rate limits without notice
5. **Competition:** Other bots are likely running similar strategies

---

## 📈 Performance Metrics (Planned)

| Metric | Target |
|--------|--------|
| Latency (order submission) | <100ms |
| Uptime | 99.9% |
| Sharpe Ratio | >2.0 |
| Max Drawdown | <10% |

---

## 🔮 Roadmap

### Phase 1: Foundation ✅
- [x] Rust core with PyO3 bindings
- [x] 5-bot architecture
- [x] Dry-run verification

### Phase 2: Infrastructure (Current)
- [ ] AWS deployment scripts
- [ ] Prometheus metrics
- [ ] Grafana dashboard
- [ ] Telegram/Discord alerts

### Phase 3: Live Trading
- [ ] Paper trading mode
- [ ] Risk limits & circuit breakers
- [ ] Position sizing
- [ ] Live execution

### Phase 4: Optimization
- [ ] WebSocket orderbook streaming
- [ ] Latency optimization
- [ ] Strategy backtesting
- [ ] ML model integration

---

## 📝 License

MIT © 2026 Priyansh Rana

---

## 📞 Contact

- **GitHub:** [@RanaPriyansh](https://github.com/RanaPriyansh)
- **Project:** [polymarket-hft](https://github.com/RanaPriyansh/polymarket-hft)
