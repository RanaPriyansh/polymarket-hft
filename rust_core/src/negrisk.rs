//! NegRisk Module - Bot 2: The NegRisk Miner
//! 
//! Targets the "Unity Constraint" in Mutually Exclusive markets.
//! 
//! Logic:
//! - Sum of Bids (ΣBids) > 1.00 + fees → Mint-and-Sell opportunity
//! - Sum of Asks (ΣAsks) < 1.00 - fees → Buy-and-Merge opportunity
//! 
//! In a binary market: YES + NO outcomes must sum to 1.0
//! In an N-way market: All outcomes must sum to 1.0

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

/// Default fee assumptions (in decimal, not bps)
const DEFAULT_FEE: f64 = 0.02; // 2% round-trip fee assumption

/// Type of NegRisk opportunity
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum OpportunityType {
    /// ΣBids > 1.0 + fees: Mint shares and sell to all bidders
    MintAndSell,
    /// ΣAsks < 1.0 - fees: Buy all outcomes and merge for $1
    BuyAndMerge,
    /// No opportunity
    None,
}

/// A NegRisk opportunity
#[derive(Debug, Clone, Serialize, Deserialize)]
#[pyclass]
pub struct Opportunity {
    #[pyo3(get)]
    pub opportunity_type: String,
    #[pyo3(get)]
    pub condition_id: String,
    #[pyo3(get)]
    pub prices: Vec<f64>,
    #[pyo3(get)]
    pub sum_bids: f64,
    #[pyo3(get)]
    pub sum_asks: f64,
    #[pyo3(get)]
    pub profit_gross: f64,
    #[pyo3(get)]
    pub profit_net: f64,
    #[pyo3(get)]
    pub profit_bps: f64,
    #[pyo3(get)]
    pub is_profitable: bool,
}

#[pymethods]
impl Opportunity {
    fn __repr__(&self) -> String {
        format!(
            "Opportunity({}: Σbids={:.4}, Σasks={:.4}, profit={}bps, profitable={})",
            self.opportunity_type,
            self.sum_bids,
            self.sum_asks,
            self.profit_bps as i64,
            self.is_profitable
        )
    }
}

/// NegRisk Miner configuration
#[derive(Debug, Clone)]
#[pyclass]
pub struct NegRiskConfig {
    /// Fee assumption (decimal, e.g., 0.02 = 2%)
    #[pyo3(get, set)]
    pub fee: f64,
    /// Minimum profit in basis points to trigger
    #[pyo3(get, set)]
    pub min_profit_bps: f64,
    /// Maximum notional per trade
    #[pyo3(get, set)]
    pub max_notional: f64,
}

#[pymethods]
impl NegRiskConfig {
    #[new]
    fn new() -> Self {
        Self {
            fee: DEFAULT_FEE,
            min_profit_bps: 10.0,
            max_notional: 1000.0,
        }
    }
}

/// Bot 2: The NegRisk Miner
#[pyclass]
pub struct NegRisk {
    config: NegRiskConfig,
}

#[pymethods]
impl NegRisk {
    #[new]
    fn new() -> Self {
        Self {
            config: NegRiskConfig::new(),
        }
    }

    #[staticmethod]
    fn with_config(config: NegRiskConfig) -> Self {
        Self { config }
    }

    /// Scan a market for NegRisk opportunities
    /// 
    /// # Arguments
    /// * `condition_id` - Market condition ID
    /// * `bids` - Best bid prices for each outcome (Vec<f64>)
    /// * `asks` - Best ask prices for each outcome (Vec<f64>)
    /// 
    /// # Returns
    /// * Opportunity enum indicating the type and profitability
    #[pyo3(name = "scan")]
    fn scan(
        &self,
        condition_id: &str,
        bids: Vec<f64>,
        asks: Vec<f64>,
    ) -> Opportunity {
        let sum_bids: f64 = bids.iter().sum();
        let sum_asks: f64 = asks.iter().sum();
        
        // Check for Mint-and-Sell: ΣBids > 1.0 + fee
        let mint_threshold = 1.0 + self.config.fee;
        if sum_bids > mint_threshold {
            let profit_gross = sum_bids - 1.0;
            let profit_net = profit_gross - self.config.fee;
            let profit_bps = profit_net * 10_000.0;
            
            return Opportunity {
                opportunity_type: "MintAndSell".to_string(),
                condition_id: condition_id.to_string(),
                prices: bids.clone(),
                sum_bids,
                sum_asks,
                profit_gross,
                profit_net,
                profit_bps,
                is_profitable: profit_bps >= self.config.min_profit_bps,
            };
        }
        
        // Check for Buy-and-Merge: ΣAsks < 1.0 - fee
        let merge_threshold = 1.0 - self.config.fee;
        if sum_asks < merge_threshold {
            let profit_gross = 1.0 - sum_asks;
            let profit_net = profit_gross - self.config.fee;
            let profit_bps = profit_net * 10_000.0;
            
            return Opportunity {
                opportunity_type: "BuyAndMerge".to_string(),
                condition_id: condition_id.to_string(),
                prices: asks.clone(),
                sum_bids,
                sum_asks,
                profit_gross,
                profit_net,
                profit_bps,
                is_profitable: profit_bps >= self.config.min_profit_bps,
            };
        }
        
        // No opportunity
        Opportunity {
            opportunity_type: "None".to_string(),
            condition_id: condition_id.to_string(),
            prices: Vec::new(),
            sum_bids,
            sum_asks,
            profit_gross: 0.0,
            profit_net: 0.0,
            profit_bps: 0.0,
            is_profitable: false,
        }
    }

    /// Quick check for potential opportunity (fast filter)
    fn quick_check(&self, bids: Vec<f64>, asks: Vec<f64>) -> bool {
        let sum_bids: f64 = bids.iter().sum();
        let sum_asks: f64 = asks.iter().sum();
        
        sum_bids > (1.0 + self.config.fee) || sum_asks < (1.0 - self.config.fee)
    }

    /// Scan a binary market (2 outcomes: YES/NO)
    fn scan_binary(
        &self,
        condition_id: &str,
        yes_bid: f64,
        yes_ask: f64,
        no_bid: f64,
        no_ask: f64,
    ) -> Opportunity {
        self.scan(condition_id, vec![yes_bid, no_bid], vec![yes_ask, no_ask])
    }

    /// Get current config
    fn get_config(&self) -> NegRiskConfig {
        self.config.clone()
    }

    /// Update config
    fn set_config(&mut self, config: NegRiskConfig) {
        self.config = config;
    }

    fn __repr__(&self) -> String {
        format!(
            "NegRisk(fee={:.1}%, min_profit={}bps)",
            self.config.fee * 100.0,
            self.config.min_profit_bps
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mint_and_sell() {
        let miner = NegRisk::new();
        
        // ΣBids = 0.55 + 0.55 = 1.10 > 1.02 (threshold)
        let opp = miner.scan("cond1", vec![0.55, 0.55], vec![0.60, 0.60]);
        assert_eq!(opp.opportunity_type, "MintAndSell");
        assert!(opp.is_profitable);
    }

    #[test]
    fn test_buy_and_merge() {
        let miner = NegRisk::new();
        
        // ΣAsks = 0.45 + 0.45 = 0.90 < 0.98 (threshold)
        let opp = miner.scan("cond2", vec![0.40, 0.40], vec![0.45, 0.45]);
        assert_eq!(opp.opportunity_type, "BuyAndMerge");
        assert!(opp.is_profitable);
    }

    #[test]
    fn test_no_opportunity() {
        let miner = NegRisk::new();
        
        // Fair market: sums near 1.0
        let opp = miner.scan("cond3", vec![0.49, 0.49], vec![0.51, 0.51]);
        assert_eq!(opp.opportunity_type, "None");
        assert!(!opp.is_profitable);
    }
}
