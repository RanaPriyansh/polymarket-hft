//! Orderbook Module - High-Performance Price-Time Priority Orderbook
//! 
//! Implements a BTreeMap-based orderbook with:
//! - Price-time priority ordering
//! - Bid/Ask level management
//! - Delta application for WebSocket updates
//! - Spread and mid-price calculations

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::sync::RwLock;

/// A single price level in the orderbook
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceLevel {
    pub price: f64,
    pub size: f64,
    pub order_count: u32,
}

/// Side of the orderbook
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Side {
    Bid,
    Ask,
}

/// Orderbook delta update from WebSocket
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderbookDelta {
    pub price: f64,
    pub size: f64,  // 0 means remove level
    pub side: String, // "bid" or "ask"
}

/// Half of an orderbook (either bids or asks)
#[derive(Debug)]
pub struct OrderbookHalf {
    /// BTreeMap for price-sorted levels
    /// For bids: sorted descending (best bid first)
    /// For asks: sorted ascending (best ask first)
    levels: BTreeMap<u64, PriceLevel>,
    is_bid: bool,
}

impl OrderbookHalf {
    pub fn new(is_bid: bool) -> Self {
        Self {
            levels: BTreeMap::new(),
            is_bid,
        }
    }

    /// Convert f64 price to u64 key (6 decimal precision)
    fn price_to_key(&self, price: f64) -> u64 {
        if self.is_bid {
            // Invert for bids so highest price comes first
            u64::MAX - (price * 1_000_000.0) as u64
        } else {
            (price * 1_000_000.0) as u64
        }
    }

    fn key_to_price(&self, key: u64) -> f64 {
        if self.is_bid {
            (u64::MAX - key) as f64 / 1_000_000.0
        } else {
            key as f64 / 1_000_000.0
        }
    }

    /// Apply a delta update
    pub fn apply_delta(&mut self, price: f64, size: f64) {
        let key = self.price_to_key(price);
        
        if size <= 0.0 {
            // Remove level
            self.levels.remove(&key);
        } else {
            // Update or insert level
            self.levels.insert(key, PriceLevel {
                price,
                size,
                order_count: 1,
            });
        }
    }

    /// Get the best price (top of book)
    pub fn best_price(&self) -> Option<f64> {
        self.levels.iter().next().map(|(key, _)| self.key_to_price(*key))
    }

    /// Get the best level
    pub fn best_level(&self) -> Option<&PriceLevel> {
        self.levels.values().next()
    }

    /// Get top N levels
    pub fn top_levels(&self, n: usize) -> Vec<PriceLevel> {
        self.levels.values().take(n).cloned().collect()
    }

    /// Get total size at all levels
    pub fn total_size(&self) -> f64 {
        self.levels.values().map(|l| l.size).sum()
    }

    /// Get total size up to a price threshold
    pub fn size_to_price(&self, threshold: f64) -> f64 {
        self.levels.iter()
            .take_while(|(key, _)| {
                let price = self.key_to_price(**key);
                if self.is_bid {
                    price >= threshold
                } else {
                    price <= threshold
                }
            })
            .map(|(_, level)| level.size)
            .sum()
    }

    /// Clear all levels
    pub fn clear(&mut self) {
        self.levels.clear();
    }

    /// Number of price levels
    pub fn depth(&self) -> usize {
        self.levels.len()
    }
}

/// Full orderbook for a single market/token
#[derive(Debug)]
pub struct Orderbook {
    pub token_id: String,
    pub bids: RwLock<OrderbookHalf>,
    pub asks: RwLock<OrderbookHalf>,
    pub last_update_ts: RwLock<u64>,
}

impl Orderbook {
    pub fn new(token_id: String) -> Self {
        Self {
            token_id,
            bids: RwLock::new(OrderbookHalf::new(true)),
            asks: RwLock::new(OrderbookHalf::new(false)),
            last_update_ts: RwLock::new(0),
        }
    }

    /// Apply a delta update
    pub fn apply_delta(&self, delta: &OrderbookDelta) {
        match delta.side.to_lowercase().as_str() {
            "bid" | "buy" => {
                self.bids.write().unwrap().apply_delta(delta.price, delta.size);
            }
            "ask" | "sell" => {
                self.asks.write().unwrap().apply_delta(delta.price, delta.size);
            }
            _ => {}
        }
    }

    /// Get the current spread
    pub fn spread(&self) -> Option<f64> {
        let best_bid = self.bids.read().unwrap().best_price()?;
        let best_ask = self.asks.read().unwrap().best_price()?;
        Some(best_ask - best_bid)
    }

    /// Get spread in basis points
    pub fn spread_bps(&self) -> Option<f64> {
        let best_bid = self.bids.read().unwrap().best_price()?;
        let best_ask = self.asks.read().unwrap().best_price()?;
        let mid = (best_bid + best_ask) / 2.0;
        if mid > 0.0 {
            Some((best_ask - best_bid) / mid * 10_000.0)
        } else {
            None
        }
    }

    /// Get the mid price
    pub fn mid_price(&self) -> Option<f64> {
        let best_bid = self.bids.read().unwrap().best_price()?;
        let best_ask = self.asks.read().unwrap().best_price()?;
        Some((best_bid + best_ask) / 2.0)
    }

    /// Check if spread is wide (opportunity for market making)
    pub fn is_wide_spread(&self, threshold_bps: f64) -> bool {
        self.spread_bps().map(|s| s >= threshold_bps).unwrap_or(false)
    }
}

/// Manager for multiple orderbooks
#[derive(Debug, Default)]
pub struct OrderbookManager {
    books: RwLock<std::collections::HashMap<String, std::sync::Arc<Orderbook>>>,
}

impl OrderbookManager {
    pub fn new() -> Self {
        Self {
            books: RwLock::new(std::collections::HashMap::new()),
        }
    }

    /// Get or create an orderbook for a token
    pub fn get_or_create(&self, token_id: &str) -> std::sync::Arc<Orderbook> {
        let mut books = self.books.write().unwrap();
        books.entry(token_id.to_string())
            .or_insert_with(|| std::sync::Arc::new(Orderbook::new(token_id.to_string())))
            .clone()
    }

    /// Get an existing orderbook
    pub fn get(&self, token_id: &str) -> Option<std::sync::Arc<Orderbook>> {
        self.books.read().unwrap().get(token_id).cloned()
    }

    /// Apply a delta to a specific orderbook
    pub fn apply_delta(&self, token_id: &str, delta: &OrderbookDelta) {
        let book = self.get_or_create(token_id);
        book.apply_delta(delta);
    }

    /// Find markets with wide spreads
    pub fn find_wide_spreads(&self, threshold_bps: f64) -> Vec<String> {
        self.books.read().unwrap()
            .iter()
            .filter(|(_, book)| book.is_wide_spread(threshold_bps))
            .map(|(id, _)| id.clone())
            .collect()
    }

    /// Get all token IDs
    pub fn token_ids(&self) -> Vec<String> {
        self.books.read().unwrap().keys().cloned().collect()
    }
}

// ============ PyO3 Bindings ============

#[pyclass]
pub struct PyOrderbook {
    inner: std::sync::Arc<Orderbook>,
}

#[pymethods]
impl PyOrderbook {
    #[new]
    fn new(token_id: &str) -> Self {
        Self {
            inner: std::sync::Arc::new(Orderbook::new(token_id.to_string())),
        }
    }

    /// Apply a delta update: (price, size, side)
    fn apply_delta(&self, price: f64, size: f64, side: &str) {
        self.inner.apply_delta(&OrderbookDelta {
            price,
            size,
            side: side.to_string(),
        });
    }

    /// Get best bid price
    fn best_bid(&self) -> Option<f64> {
        self.inner.bids.read().unwrap().best_price()
    }

    /// Get best ask price
    fn best_ask(&self) -> Option<f64> {
        self.inner.asks.read().unwrap().best_price()
    }

    /// Get mid price
    fn mid_price(&self) -> Option<f64> {
        self.inner.mid_price()
    }

    /// Get spread in basis points
    fn spread_bps(&self) -> Option<f64> {
        self.inner.spread_bps()
    }

    /// Check if spread is wide
    fn is_wide_spread(&self, threshold_bps: f64) -> bool {
        self.inner.is_wide_spread(threshold_bps)
    }

    /// Get top N bid levels as JSON
    fn top_bids(&self, n: usize) -> String {
        let levels = self.inner.bids.read().unwrap().top_levels(n);
        serde_json::to_string(&levels).unwrap_or_default()
    }

    /// Get top N ask levels as JSON
    fn top_asks(&self, n: usize) -> String {
        let levels = self.inner.asks.read().unwrap().top_levels(n);
        serde_json::to_string(&levels).unwrap_or_default()
    }

    /// Get bid depth (number of levels)
    fn bid_depth(&self) -> usize {
        self.inner.bids.read().unwrap().depth()
    }

    /// Get ask depth (number of levels)
    fn ask_depth(&self) -> usize {
        self.inner.asks.read().unwrap().depth()
    }

    fn __repr__(&self) -> String {
        let bid = self.best_bid().map(|p| format!("{:.4}", p)).unwrap_or("--".into());
        let ask = self.best_ask().map(|p| format!("{:.4}", p)).unwrap_or("--".into());
        let spread = self.spread_bps().map(|s| format!("{:.0}bps", s)).unwrap_or("--".into());
        format!("Orderbook({}: {} x {} [{}])", self.inner.token_id, bid, ask, spread)
    }
}

#[pyclass]
pub struct PyOrderbookManager {
    inner: std::sync::Arc<OrderbookManager>,
}

#[pymethods]
impl PyOrderbookManager {
    #[new]
    fn new() -> Self {
        Self {
            inner: std::sync::Arc::new(OrderbookManager::new()),
        }
    }

    /// Apply a delta to a token's orderbook
    fn apply_delta(&self, token_id: &str, price: f64, size: f64, side: &str) {
        self.inner.apply_delta(token_id, &OrderbookDelta {
            price,
            size,
            side: side.to_string(),
        });
    }

    /// Get mid price for a token
    fn mid_price(&self, token_id: &str) -> Option<f64> {
        self.inner.get(token_id)?.mid_price()
    }

    /// Get spread in bps for a token
    fn spread_bps(&self, token_id: &str) -> Option<f64> {
        self.inner.get(token_id)?.spread_bps()
    }

    /// Find tokens with wide spreads
    fn find_wide_spreads(&self, threshold_bps: f64) -> Vec<String> {
        self.inner.find_wide_spreads(threshold_bps)
    }

    /// Get all token IDs
    fn token_ids(&self) -> Vec<String> {
        self.inner.token_ids()
    }

    fn __repr__(&self) -> String {
        format!("OrderbookManager(tokens={})", self.inner.token_ids().len())
    }
}
