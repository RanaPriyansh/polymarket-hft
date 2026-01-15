//! NegRisk Arbitrage Miner (Bot 2)
//! Enforces the "Unity Constraint" - Sum of probabilities must equal 1.00
//! Triggers: Mint-and-Sell when Sum(Bids) > $1.00 + Fees
//!           Buy-and-Merge when Sum(Asks) < $1.00 - Fees

use crate::orderbook::{OrderBookManager, PriceLevel};
use pyo3::prelude::*;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::str::FromStr;
use std::sync::Arc;

/// NegRisk market structure
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NegRiskMarket {
    pub condition_id: String,
    pub token_ids: Vec<String>,  // All outcome tokens for this market
    pub outcome_names: Vec<String>,
}

/// Arbitrage opportunity detected
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NegRiskArbitrage {
    pub arb_type: ArbType,
    pub condition_id: String,
    pub expected_profit_bps: i32,  // In basis points
    pub total_cost: Decimal,
    pub total_revenue: Decimal,
    pub legs: Vec<ArbLeg>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ArbType {
    MintAndSell,   // Sum(Bids) > 1.00 -> Mint full set, sell individually
    BuyAndMerge,   // Sum(Asks) < 1.00 -> Buy all outcomes, merge to USDC
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArbLeg {
    pub token_id: String,
    pub outcome_name: String,
    pub side: String,  // "BUY" or "SELL"
    pub price: Decimal,
    pub size: Decimal,
}

/// Configuration for NegRisk mining
#[derive(Debug, Clone)]
pub struct NegRiskConfig {
    pub min_arb_bps: i32,         // Minimum profit in basis points
    pub max_position_usd: Decimal, // Maximum position size
    pub fee_bps: i32,             // Exchange fees in bps (typically 0-200)
}

impl Default for NegRiskConfig {
    fn default() -> Self {
        Self {
            min_arb_bps: 30,  // 0.3% minimum profit
            max_position_usd: Decimal::from(1000),
            fee_bps: 0,  // Maker orders are often 0 fee
        }
    }
}

/// NegRisk Arbitrage Miner
pub struct NegRiskMiner {
    orderbook_manager: Arc<OrderBookManager>,
    markets: HashMap<String, NegRiskMarket>,  // condition_id -> market
    config: NegRiskConfig,
}

impl NegRiskMiner {
    pub fn new(orderbook_manager: Arc<OrderBookManager>, config: NegRiskConfig) -> Self {
        Self {
            orderbook_manager,
            markets: HashMap::new(),
            config,
        }
    }

    /// Register a NegRisk market to monitor
    pub fn register_market(&mut self, market: NegRiskMarket) {
        self.markets.insert(market.condition_id.clone(), market);
    }

    /// Unregister a market
    pub fn unregister_market(&mut self, condition_id: &str) {
        self.markets.remove(condition_id);
    }

    /// Scan all registered markets for arbitrage opportunities
    pub fn scan_all(&self) -> Vec<NegRiskArbitrage> {
        self.markets
            .values()
            .filter_map(|market| self.check_market(market))
            .collect()
    }

    /// Check a single market for arbitrage
    pub fn check_market(&self, market: &NegRiskMarket) -> Option<NegRiskArbitrage> {
        // Collect best bids and asks for all outcomes
        let mut best_bids: Vec<(String, String, Option<Decimal>)> = Vec::new();
        let mut best_asks: Vec<(String, String, Option<Decimal>)> = Vec::new();

        for (i, token_id) in market.token_ids.iter().enumerate() {
            let outcome_name = market.outcome_names.get(i)
                .map(|s| s.clone())
                .unwrap_or_else(|| format!("Outcome {}", i));

            let book = self.orderbook_manager.get(token_id);
            
            let best_bid = book.as_ref()
                .and_then(|b| b.bids.read().best_price(true));
            let best_ask = book.as_ref()
                .and_then(|b| b.asks.read().best_price(false));

            best_bids.push((token_id.clone(), outcome_name.clone(), best_bid));
            best_asks.push((token_id.clone(), outcome_name, best_ask));
        }

        // Check for Mint-and-Sell opportunity
        // All bids must exist and sum > 1.00
        if let Some(arb) = self.check_mint_and_sell(&market.condition_id, &best_bids) {
            if arb.expected_profit_bps >= self.config.min_arb_bps {
                return Some(arb);
            }
        }

        // Check for Buy-and-Merge opportunity
        // All asks must exist and sum < 1.00
        if let Some(arb) = self.check_buy_and_merge(&market.condition_id, &best_asks) {
            if arb.expected_profit_bps >= self.config.min_arb_bps {
                return Some(arb);
            }
        }

        None
    }

    /// Check for Mint-and-Sell arbitrage
    /// If Sum(Best Bids) > 1.00, we can mint a full set for $1, sell each outcome
    fn check_mint_and_sell(
        &self,
        condition_id: &str,
        bids: &[(String, String, Option<Decimal>)],
    ) -> Option<NegRiskArbitrage> {
        // All outcomes must have bids
        let all_have_bids = bids.iter().all(|(_, _, b)| b.is_some());
        if !all_have_bids {
            return None;
        }

        let sum_bids: Decimal = bids.iter()
            .filter_map(|(_, _, b)| *b)
            .sum();

        // Need sum > 1.00 + fees to profit
        let fee_adjustment = Decimal::from(self.config.fee_bps) / Decimal::from(10000);
        let threshold = Decimal::ONE + fee_adjustment;

        if sum_bids <= threshold {
            return None;
        }

        // Calculate profit
        let mint_cost = Decimal::ONE;  // $1 to mint full set
        let sell_revenue = sum_bids * (Decimal::ONE - fee_adjustment);
        let profit = sell_revenue - mint_cost;
        let profit_bps = ((profit / mint_cost) * Decimal::from(10000))
            .to_string()
            .parse::<i32>()
            .unwrap_or(0);

        // Build legs
        let legs: Vec<ArbLeg> = bids.iter()
            .filter_map(|(token_id, name, bid)| {
                Some(ArbLeg {
                    token_id: token_id.clone(),
                    outcome_name: name.clone(),
                    side: "SELL".to_string(),
                    price: (*bid)?,
                    size: Decimal::ONE,  // Will be sized to position limit
                })
            })
            .collect();

        Some(NegRiskArbitrage {
            arb_type: ArbType::MintAndSell,
            condition_id: condition_id.to_string(),
            expected_profit_bps: profit_bps,
            total_cost: mint_cost,
            total_revenue: sell_revenue,
            legs,
        })
    }

    /// Check for Buy-and-Merge arbitrage
    /// If Sum(Best Asks) < 1.00, we can buy all outcomes and merge for $1
    fn check_buy_and_merge(
        &self,
        condition_id: &str,
        asks: &[(String, String, Option<Decimal>)],
    ) -> Option<NegRiskArbitrage> {
        // All outcomes must have asks
        let all_have_asks = asks.iter().all(|(_, _, a)| a.is_some());
        if !all_have_asks {
            return None;
        }

        let sum_asks: Decimal = asks.iter()
            .filter_map(|(_, _, a)| *a)
            .sum();

        // Need sum < 1.00 - fees to profit
        let fee_adjustment = Decimal::from(self.config.fee_bps) / Decimal::from(10000);
        let threshold = Decimal::ONE - fee_adjustment;

        if sum_asks >= threshold {
            return None;
        }

        // Calculate profit
        let buy_cost = sum_asks * (Decimal::ONE + fee_adjustment);
        let merge_revenue = Decimal::ONE;  // $1 back from merge
        let profit = merge_revenue - buy_cost;
        let profit_bps = ((profit / buy_cost) * Decimal::from(10000))
            .to_string()
            .parse::<i32>()
            .unwrap_or(0);

        // Build legs
        let legs: Vec<ArbLeg> = asks.iter()
            .filter_map(|(token_id, name, ask)| {
                Some(ArbLeg {
                    token_id: token_id.clone(),
                    outcome_name: name.clone(),
                    side: "BUY".to_string(),
                    price: (*ask)?,
                    size: Decimal::ONE,
                })
            })
            .collect();

        Some(NegRiskArbitrage {
            arb_type: ArbType::BuyAndMerge,
            condition_id: condition_id.to_string(),
            expected_profit_bps: profit_bps,
            total_cost: buy_cost,
            total_revenue: merge_revenue,
            legs,
        })
    }

    /// Calculate optimal position size based on liquidity
    pub fn calculate_position_size(
        &self,
        arb: &NegRiskArbitrage,
    ) -> Decimal {
        // Find the minimum liquidity across all legs
        let min_liquidity = arb.legs.iter()
            .filter_map(|leg| {
                let book = self.orderbook_manager.get(&leg.token_id)?;
                let side_is_buy = leg.side == "BUY";
                
                if side_is_buy {
                    // Check ask liquidity
                    Some(book.asks.read().size_at_price(&leg.price))
                } else {
                    // Check bid liquidity
                    Some(book.bids.read().size_at_price(&leg.price))
                }
            })
            .min()
            .unwrap_or(Decimal::ZERO);

        // Limit by config max position
        let max_shares = self.config.max_position_usd;  // Assuming $1 per share
        
        min_liquidity.min(max_shares)
    }
}

// ============ PyO3 Bindings ============

#[pyclass]
pub struct PyNegRiskMiner {
    inner: std::sync::Mutex<NegRiskMiner>,
}

#[pymethods]
impl PyNegRiskMiner {
    #[new]
    #[pyo3(signature = (min_arb_bps=30, max_position_usd="1000", fee_bps=0))]
    pub fn new(min_arb_bps: i32, max_position_usd: &str, fee_bps: i32) -> PyResult<Self> {
        let config = NegRiskConfig {
            min_arb_bps,
            max_position_usd: Decimal::from_str(max_position_usd)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?,
            fee_bps,
        };

        let orderbook_manager = Arc::new(OrderBookManager::new());
        let inner = NegRiskMiner::new(orderbook_manager, config);

        Ok(Self {
            inner: std::sync::Mutex::new(inner),
        })
    }

    /// Register a NegRisk market (JSON input)
    pub fn register_market(&self, json: &str) -> PyResult<()> {
        let market: NegRiskMarket = serde_json::from_str(json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        
        self.inner.lock().unwrap().register_market(market);
        Ok(())
    }

    /// Scan all markets for arbitrage, returns JSON array
    pub fn scan(&self) -> PyResult<String> {
        let arbs = self.inner.lock().unwrap().scan_all();
        serde_json::to_string(&arbs)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    /// Load orderbook snapshot for a token
    pub fn load_snapshot(&self, json: &str) -> PyResult<()> {
        let snapshot: crate::orderbook::OrderBookSnapshot = serde_json::from_str(json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        
        self.inner.lock().unwrap()
            .orderbook_manager
            .load_snapshot(snapshot);
        Ok(())
    }

    /// Apply delta update
    pub fn apply_delta(&self, json: &str) -> PyResult<()> {
        let delta: crate::orderbook::OrderBookDelta = serde_json::from_str(json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        
        self.inner.lock().unwrap()
            .orderbook_manager
            .apply_delta(delta)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }
}
