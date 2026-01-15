//! Vulture Module - Bot 4: Zombie Market Maker
//! 15-minute crypto POST_ONLY rebate farming

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[pyclass]
pub struct MarketOpportunity {
    #[pyo3(get)]
    pub market_slug: String,
    #[pyo3(get)]
    pub condition_id: String,
    #[pyo3(get)]
    pub spread_bps: f64,
    #[pyo3(get)]
    pub best_bid: f64,
    #[pyo3(get)]
    pub best_ask: f64,
    #[pyo3(get)]
    pub mid_price: f64,
    #[pyo3(get)]
    pub is_crypto_15min: bool,
    #[pyo3(get)]
    pub recommended_side: String,
    #[pyo3(get)]
    pub recommended_price: f64,
    #[pyo3(get)]
    pub use_post_only: bool,
}

#[pymethods]
impl MarketOpportunity {
    fn __repr__(&self) -> String {
        format!("MarketOpportunity(slug='{}', spread={}bps, post_only={})",
            self.market_slug, self.spread_bps, self.use_post_only)
    }
}

#[derive(Debug, Clone)]
#[pyclass]
pub struct VultureConfig {
    #[pyo3(get, set)]
    pub min_spread_bps: f64,
    #[pyo3(get, set)]
    pub max_spread_bps: f64,
    #[pyo3(get, set)]
    pub min_mid_price: f64,
    #[pyo3(get, set)]
    pub edge_fraction: f64,
    #[pyo3(get, set)]
    pub force_post_only: bool,
}

#[pymethods]
impl VultureConfig {
    #[new]
    fn new() -> Self {
        Self {
            min_spread_bps: 50.0,
            max_spread_bps: 500.0,
            min_mid_price: 0.05,
            edge_fraction: 0.25,
            force_post_only: false,
        }
    }
}

#[derive(Debug)]
#[pyclass]
pub struct Vulture {
    config: VultureConfig,
}

#[pymethods]
impl Vulture {
    #[new]
    fn new() -> Self {
        Self { config: VultureConfig::new() }
    }

    #[staticmethod]
    fn with_config(config: VultureConfig) -> Self {
        Self { config }
    }

    #[pyo3(name = "is_15min_crypto")]
    fn is_15min_crypto(&self, market_slug: &str) -> bool {
        let slug = market_slug.to_lowercase();
        let cryptos = ["btc", "bitcoin", "eth", "ethereum", "sol", "solana", "xrp", "doge", "bnb", "ada", "avax", "matic", "link"];
        let is_15min = slug.contains("15m") || slug.contains("15-min") || slug.contains("15min");
        is_15min && cryptos.iter().any(|c| slug.contains(c))
    }

    #[pyo3(name = "scan")]
    fn scan(&self, market_slug: &str, condition_id: &str, best_bid: f64, best_ask: f64) -> Option<MarketOpportunity> {
        if best_bid <= 0.0 || best_ask <= 0.0 || best_bid >= best_ask { return None; }
        let mid_price = (best_bid + best_ask) / 2.0;
        if mid_price < self.config.min_mid_price { return None; }
        let spread = best_ask - best_bid;
        let spread_bps = (spread / mid_price) * 10_000.0;
        if spread_bps < self.config.min_spread_bps || spread_bps > self.config.max_spread_bps { return None; }
        let is_crypto = self.is_15min_crypto(market_slug);
        let use_post_only = is_crypto || self.config.force_post_only;
        let edge = spread * self.config.edge_fraction;
        let recommended_price = best_bid + edge;
        let recommended_side = if recommended_price < mid_price { "BUY" } else { "SELL" };
        Some(MarketOpportunity {
            market_slug: market_slug.to_string(),
            condition_id: condition_id.to_string(),
            spread_bps, best_bid, best_ask, mid_price,
            is_crypto_15min: is_crypto,
            recommended_side: recommended_side.to_string(),
            recommended_price, use_post_only,
        })
    }

    #[pyo3(name = "scan_batch")]
    fn scan_batch(&self, markets: Vec<(String, String, f64, f64)>) -> Vec<MarketOpportunity> {
        markets.into_iter().filter_map(|(slug, cid, bid, ask)| self.scan(&slug, &cid, bid, ask)).collect()
    }

    fn __repr__(&self) -> String {
        format!("Vulture(min_spread={}bps, max_spread={}bps)", self.config.min_spread_bps, self.config.max_spread_bps)
    }
}
