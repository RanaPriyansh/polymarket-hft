# 🦅 Polymarket HFT Bot Fleet

> **5 Autonomous Bots. 1 Mission. Exploit Every Edge.**

A high-frequency trading system for [Polymarket](https://polymarket.com) prediction markets, built with **Rust** (core) + **Python** (orchestration) via PyO3 FFI.

---

## The Fleet

| # | Bot | Strategy |
|---|-----|----------|
| 1 | **CorrelationScanner** | Detects DAG monotonicity violations — when correlated markets (e.g., "Trump wins PA" → "Trump wins Election") are mispriced relative to each other |
| 2 | **NegRiskMiner** | Exploits unity constraint arbitrage — when mutually exclusive outcomes don't sum to $1.00, executes mint-and-sell or buy-and-merge |
| 3 | **ResolutionSniper** | Snipes the UMA Oracle liveness window — buys confirmed outcomes during the 2-hour dispute period before markets update |
| 4 | **Vulture** | Zombie market maker + rebate farmer — quotes inside wide spreads and farms maker rebates on 15-min crypto markets |
| 5 | **SemanticSentinel** | LLM-powered news arbitrage — parses breaking headlines with Gemini to front-run manual traders |

---

## License

MIT © 2026 Priyansh Rana
