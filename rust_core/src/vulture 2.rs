//! Vulture Module - The Zombie Market Maker
//! 
//! Scans for dead/dying markets and provides liquidity where others fear to tread.
//! Implements rebate farming strategy for 15-minute crypto markets.

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

/// A market opportunity detected by the Vulture
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
        format!(
            "MarketOpportunity(slug='{}', spread={}bps, mid={:.4}, post_only={})",
            self.market_slug, self.spread_bps, self.mid_price, self.use_post_only
        )
    }
}

/// Configuration for the Vulture scanner
#[derive(Debug, Clone)]
#[pyclass]
pub struct VultureConfig {
    /// Minimum spread in basis points to consider a market
    #[pyo3(get, set)]
    pub min_spread_bps: f64,
    /// Maximum spread to avoid extremely illiquid markets
    #[pyo3(get, set)]
    pub max_spread_bps: f64,
    /// Minimum mid-price (avoid penny stocks)
    #[pyo3(get, set)]
    pub min_mid_price: f64,
    /// Edge inside the spread to target (as fraction, e.g., 0.25 = 25% inside)
    #[pyo3(get, set)]
    pub edge_fraction: f64,
    /// Whether to force POST_ONLY for all orders
    #[pyo3(get, set)]
    pub force_post_only: bool,
}

#[pymethods]
impl VultureConfig {
    #[new]
    fn new() -> Self {
        Self {
            min_spread_bps: 50.0,     // Minimum 50bps spread
            max_spread_bps: 500.0,    // Maximum 5% spread
            min_mid_price: 0.05,      // At least 5 cents
            edge_fraction: 0.25,      // Target 25% inside the spread
            force_post_only: false,   // Don't force by default
        }
    }
    
    fn __repr__(&self) -> String {
        format!(
            "VultureConfig(min_spread={}bps, max_spread={}bps, edge={:.0}%)",
            self.min_spread_bps, self.max_spread_bps, self.edge_fraction * 100.0
        )
    }
}

/// The Vulture - Zombie Market Maker
/// 
/// Scans markets for profitable spread opportunities and generates
/// maker orders to capture rebates. Especially optimized for 15-minute
/// crypto resolution markets.
#[derive(Debug)]
#[pyclass]
pub struct Vulture {
    config: VultureConfig,
}

#[pymethods]
impl Vulture {
    /// Create a new Vulture with default configuration
    #[new]
    fn new() -> Self {
        Self {
            config: VultureConfig::new(),
        }
    }

    /// Create a Vulture with custom configuration
    #[staticmethod]
    fn with_config(config: VultureConfig) -> Self {
        Self { config }
    }

    /// Check if a market is a 15-minute crypto resolution market
    /// These markets qualify for maker rebates under the new fee structure
    #[pyo3(name = "is_15min_crypto")]
    fn is_15min_crypto(&self, market_slug: &str) -> bool {
        is_15min_crypto_market(market_slug)
    }

    /// Scan a market and return opportunity if profitable
    /// 
    /// # Arguments
    /// * `market_slug` - The market identifier/slug
    /// * `condition_id` - The condition ID for the market
    /// * `best_bid` - Current best bid price (0-1)
    /// * `best_ask` - Current best ask price (0-1)
    /// 
    /// # Returns
    /// * `Option<MarketOpportunity>` - The opportunity if spread meets criteria
    #[pyo3(name = "scan")]
    fn scan(
        &self,
        market_slug: &str,
        condition_id: &str,
        best_bid: f64,
        best_ask: f64,
    ) -> Option<MarketOpportunity> {
        // Validate inputs
        if best_bid <= 0.0 || best_ask <= 0.0 || best_bid >= best_ask {
            return None;
        }

        let mid_price = (best_bid + best_ask) / 2.0;
        
        // Check minimum mid price
        if mid_price < self.config.min_mid_price {
            return None;
        }

        // Calculate spread in basis points
        let spread = best_ask - best_bid;
        let spread_bps = (spread / mid_price) * 10_000.0;

        // Check if spread is in acceptable range
        if spread_bps < self.config.min_spread_bps || spread_bps > self.config.max_spread_bps {
            return None;
        }

        // Determine if this is a 15-min crypto market (for rebate farming)
        let is_crypto = is_15min_crypto_market(market_slug);
        
        // Force POST_ONLY for crypto markets or if globally configured
        let use_post_only = is_crypto || self.config.force_post_only;

        // Calculate optimal entry price (inside the spread)
        let edge = spread * self.config.edge_fraction;
        let recommended_price = best_bid + edge;
        
        // For rebate farming, we want to be a maker (buy below mid, sell above mid)
        let recommended_side = if recommended_price < mid_price {
            "BUY"
        } else {
            "SELL"
        };

        Some(MarketOpportunity {
            market_slug: market_slug.to_string(),
            condition_id: condition_id.to_string(),
            spread_bps,
            best_bid,
            best_ask,
            mid_price,
            is_crypto_15min: is_crypto,
            recommended_side: recommended_side.to_string(),
            recommended_price,
            use_post_only,
        })
    }

    /// Scan multiple markets and return all opportunities
    #[pyo3(name = "scan_batch")]
    fn scan_batch(
        &self,
        markets: Vec<(String, String, f64, f64)>, // (slug, condition_id, bid, ask)
    ) -> Vec<MarketOpportunity> {
        markets
            .into_iter()
            .filter_map(|(slug, cid, bid, ask)| self.scan(&slug, &cid, bid, ask))
            .collect()
    }

    /// Get current configuration
    fn get_config(&self) -> VultureConfig {
        self.config.clone()
    }

    /// Update configuration
    fn set_config(&mut self, config: VultureConfig) {
        self.config = config;
    }

    fn __repr__(&self) -> String {
        format!(
            "Vulture(min_spread={}bps, max_spread={}bps, edge={:.0}%)",
            self.config.min_spread_bps,
            self.config.max_spread_bps,
            self.config.edge_fraction * 100.0
        )
    }
}

/// Check if a market slug indicates a 15-minute crypto resolution market
/// 
/// These markets have specific naming patterns:
/// - "btc-price-*-15m" or "bitcoin-*-15-min*"
/// - "eth-price-*-15m" or "ethereum-*-15-min*"  
/// - Similar patterns for other major cryptos
/// 
/// Under the new Polymarket fee structure, these qualify for maker rebates.
fn is_15min_crypto_market(market_slug: &str) -> bool {
    let slug_lower = market_slug.to_lowercase();
    
    // Known crypto prefixes
    let crypto_prefixes = [
        "btc", "bitcoin", 
        "eth", "ethereum",
        "sol", "solana",
        "xrp", "ripple",
        "doge", "dogecoin",
        "bnb", "binance",
        "ada", "cardano",
        "avax", "avalanche",
        "matic", "polygon",
        "link", "chainlink",
        "crypto",
    ];
    
    // Check for 15-minute resolution patterns
    let is_15min = slug_lower.contains("15m") 
        || slug_lower.contains("15-min")
        || slug_lower.contains("15min")
        || slug_lower.contains("fifteen-min");
    
    if !is_15min {
        return false;
    }
    
    // Check if it's a crypto market
    for prefix in crypto_prefixes.iter() {
        if slug_lower.starts_with(prefix) || slug_lower.contains(&format!("-{}-", prefix)) {
            return true;
        }
    }
    
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_15min_crypto() {
        assert!(is_15min_crypto_market("btc-price-above-100k-15m"));
        assert!(is_15min_crypto_market("ethereum-15-min-resolution"));
        assert!(is_15min_crypto_market("sol-price-15min-bucket"));
        
        // Non-crypto or non-15min should return false
        assert!(!is_15min_crypto_market("will-trump-win-election"));
        assert!(!is_15min_crypto_market("btc-price-daily"));
        assert!(!is_15min_crypto_market("fed-rate-decision"));
    }

    #[test]
    fn test_vulture_scan() {
        let vulture = Vulture::new();
        
        // Valid opportunity with good spread
        let opp = vulture.scan("test-market", "0x123", 0.45, 0.55);
        assert!(opp.is_some());
        
        let opp = opp.unwrap();
        assert!((opp.spread_bps - 200.0).abs() < 1.0); // ~200bps spread
        assert_eq!(opp.recommended_side, "BUY");
        
        // Spread too small
        let opp = vulture.scan("test-market", "0x123", 0.49, 0.51);
        assert!(opp.is_none());
    }

    #[test]
    fn test_crypto_post_only() {
        let vulture = Vulture::new();
        
        // Crypto 15min market should use POST_ONLY
        let opp = vulture.scan("btc-price-15m", "0x123", 0.45, 0.55);
        assert!(opp.is_some());
        assert!(opp.unwrap().use_post_only);
        
        // Non-crypto market should not force POST_ONLY
        let opp = vulture.scan("trump-wins-2024", "0x456", 0.45, 0.55);
        assert!(opp.is_some());
        assert!(!opp.unwrap().use_post_only);
    }
}
