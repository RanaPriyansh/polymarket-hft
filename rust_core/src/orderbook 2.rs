//! Order Book Data Structures and Operations
//! Maintains a local HashMap-based orderbook with delta updates

use dashmap::DashMap;
use parking_lot::RwLock;
use pyo3::prelude::*;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::sync::Arc;

/// Price level in the order book
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceLevel {
    pub price: Decimal,
    pub size: Decimal,
    pub order_count: u32,
}

/// Single side of the order book (bids or asks)
#[derive(Debug, Clone, Default)]
pub struct OrderBookSide {
    /// Price -> (Size, OrderCount)
    pub levels: BTreeMap<Decimal, (Decimal, u32)>,
}

impl OrderBookSide {
    pub fn new() -> Self {
        Self {
            levels: BTreeMap::new(),
        }
    }

    /// Apply a delta update to this side
    pub fn apply_delta(&mut self, price: Decimal, size: Decimal) {
        if size.is_zero() {
            self.levels.remove(&price);
        } else {
            self.levels
                .entry(price)
                .and_modify(|(s, c)| {
                    *s = size;
                    *c += 1;
                })
                .or_insert((size, 1));
        }
    }

    /// Get best price (highest bid or lowest ask)
    pub fn best_price(&self, is_bid: bool) -> Option<Decimal> {
        if is_bid {
            self.levels.keys().last().copied()
        } else {
            self.levels.keys().next().copied()
        }
    }

    /// Get total size at a price level
    pub fn size_at_price(&self, price: &Decimal) -> Decimal {
        self.levels.get(price).map(|(s, _)| *s).unwrap_or_default()
    }

    /// Get top N levels
    pub fn top_n(&self, n: usize, is_bid: bool) -> Vec<PriceLevel> {
        let iter: Box<dyn Iterator<Item = _>> = if is_bid {
            Box::new(self.levels.iter().rev())
        } else {
            Box::new(self.levels.iter())
        };

        iter.take(n)
            .map(|(price, (size, count))| PriceLevel {
                price: *price,
                size: *size,
                order_count: *count,
            })
            .collect()
    }

    /// Calculate total liquidity up to a price
    pub fn liquidity_to_price(&self, target_price: Decimal, is_bid: bool) -> Decimal {
        let mut total = Decimal::ZERO;
        for (price, (size, _)) in &self.levels {
            if (is_bid && *price >= target_price) || (!is_bid && *price <= target_price) {
                total += size;
            }
        }
        total
    }
}

/// Complete order book for a single market
#[derive(Debug)]
pub struct OrderBook {
    pub token_id: String,
    pub bids: RwLock<OrderBookSide>,
    pub asks: RwLock<OrderBookSide>,
    pub last_update_ts: RwLock<u64>,
    pub sequence_number: RwLock<u64>,
}

impl OrderBook {
    pub fn new(token_id: String) -> Self {
        Self {
            token_id,
            bids: RwLock::new(OrderBookSide::new()),
            asks: RwLock::new(OrderBookSide::new()),
            last_update_ts: RwLock::new(0),
            sequence_number: RwLock::new(0),
        }
    }

    /// Initialize from snapshot
    pub fn from_snapshot(token_id: String, snapshot: OrderBookSnapshot) -> Self {
        let mut bids = OrderBookSide::new();
        let mut asks = OrderBookSide::new();

        for level in snapshot.bids {
            bids.levels.insert(level.price, (level.size, 1));
        }
        for level in snapshot.asks {
            asks.levels.insert(level.price, (level.size, 1));
        }

        Self {
            token_id,
            bids: RwLock::new(bids),
            asks: RwLock::new(asks),
            last_update_ts: RwLock::new(snapshot.timestamp),
            sequence_number: RwLock::new(snapshot.sequence),
        }
    }

    /// Apply delta update
    pub fn apply_delta(&self, delta: OrderBookDelta) -> Result<(), OrderBookError> {
        let mut seq = self.sequence_number.write();
        
        // Sequence validation for re-org protection
        if delta.sequence <= *seq {
            return Err(OrderBookError::StaleUpdate {
                expected: *seq + 1,
                received: delta.sequence,
            });
        }

        // Gap detection
        if delta.sequence > *seq + 1 {
            return Err(OrderBookError::SequenceGap {
                expected: *seq + 1,
                received: delta.sequence,
            });
        }

        // Apply updates
        {
            let mut bids = self.bids.write();
            for update in &delta.bid_updates {
                bids.apply_delta(update.price, update.size);
            }
        }
        {
            let mut asks = self.asks.write();
            for update in &delta.ask_updates {
                asks.apply_delta(update.price, update.size);
            }
        }

        *seq = delta.sequence;
        *self.last_update_ts.write() = delta.timestamp;

        Ok(())
    }

    /// Get current spread
    pub fn spread(&self) -> Option<Decimal> {
        let best_bid = self.bids.read().best_price(true)?;
        let best_ask = self.asks.read().best_price(false)?;
        Some(best_ask - best_bid)
    }

    /// Get mid price
    pub fn mid_price(&self) -> Option<Decimal> {
        let best_bid = self.bids.read().best_price(true)?;
        let best_ask = self.asks.read().best_price(false)?;
        Some((best_bid + best_ask) / Decimal::TWO)
    }

    /// Check if spread exceeds threshold (for Vulture bot)
    pub fn spread_exceeds_bps(&self, threshold_bps: u32) -> bool {
        if let (Some(bid), Some(ask)) = (
            self.bids.read().best_price(true),
            self.asks.read().best_price(false),
        ) {
            if bid.is_zero() {
                return false;
            }
            let spread_bps = ((ask - bid) / bid * Decimal::from(10000)).to_string();
            if let Ok(bps) = spread_bps.parse::<u32>() {
                return bps > threshold_bps;
            }
        }
        false
    }
}

/// Snapshot from REST API
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderBookSnapshot {
    pub token_id: String,
    pub bids: Vec<PriceLevel>,
    pub asks: Vec<PriceLevel>,
    pub timestamp: u64,
    pub sequence: u64,
}

/// Delta update from WebSocket
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderBookDelta {
    pub token_id: String,
    pub bid_updates: Vec<PriceUpdate>,
    pub ask_updates: Vec<PriceUpdate>,
    pub timestamp: u64,
    pub sequence: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceUpdate {
    pub price: Decimal,
    pub size: Decimal,
}

/// Errors in order book operations
#[derive(Debug, thiserror::Error)]
pub enum OrderBookError {
    #[error("Stale update: expected seq {expected}, got {received}")]
    StaleUpdate { expected: u64, received: u64 },

    #[error("Sequence gap: expected seq {expected}, got {received}")]
    SequenceGap { expected: u64, received: u64 },

    #[error("Token not found: {0}")]
    TokenNotFound(String),
}

/// Global order book manager
pub struct OrderBookManager {
    pub books: DashMap<String, Arc<OrderBook>>,
}

impl OrderBookManager {
    pub fn new() -> Self {
        Self {
            books: DashMap::new(),
        }
    }

    pub fn get_or_create(&self, token_id: &str) -> Arc<OrderBook> {
        self.books
            .entry(token_id.to_string())
            .or_insert_with(|| Arc::new(OrderBook::new(token_id.to_string())))
            .clone()
    }

    pub fn get(&self, token_id: &str) -> Option<Arc<OrderBook>> {
        self.books.get(token_id).map(|r| r.clone())
    }

    pub fn load_snapshot(&self, snapshot: OrderBookSnapshot) {
        let token_id = snapshot.token_id.clone();
        let book = Arc::new(OrderBook::from_snapshot(token_id.clone(), snapshot));
        self.books.insert(token_id, book);
    }

    pub fn apply_delta(&self, delta: OrderBookDelta) -> Result<(), OrderBookError> {
        match self.books.get(&delta.token_id) {
            Some(book) => book.apply_delta(delta),
            None => Err(OrderBookError::TokenNotFound(delta.token_id)),
        }
    }

    /// Get all token IDs with wide spreads (for Vulture)
    pub fn find_wide_spread_markets(&self, min_spread_bps: u32) -> Vec<String> {
        self.books
            .iter()
            .filter(|entry| entry.value().spread_exceeds_bps(min_spread_bps))
            .map(|entry| entry.key().clone())
            .collect()
    }
}

impl Default for OrderBookManager {
    fn default() -> Self {
        Self::new()
    }
}

// ============ PyO3 Bindings ============

#[pyclass]
pub struct PyOrderbook {
    inner: Arc<OrderBookManager>,
}

#[pymethods]
impl PyOrderbook {
    #[new]
    pub fn new() -> Self {
        Self {
            inner: Arc::new(OrderBookManager::new()),
        }
    }

    /// Load a snapshot from JSON
    pub fn load_snapshot_json(&self, json: &str) -> PyResult<()> {
        let snapshot: OrderBookSnapshot = serde_json::from_str(json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        self.inner.load_snapshot(snapshot);
        Ok(())
    }

    /// Apply a delta update from JSON
    pub fn apply_delta_json(&self, json: &str) -> PyResult<()> {
        let delta: OrderBookDelta = serde_json::from_str(json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        self.inner
            .apply_delta(delta)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    /// Get best bid for a token
    pub fn best_bid(&self, token_id: &str) -> Option<String> {
        self.inner
            .get(token_id)?
            .bids
            .read()
            .best_price(true)
            .map(|p| p.to_string())
    }

    /// Get best ask for a token
    pub fn best_ask(&self, token_id: &str) -> Option<String> {
        self.inner
            .get(token_id)?
            .asks
            .read()
            .best_price(false)
            .map(|p| p.to_string())
    }

    /// Get spread in basis points
    pub fn spread_bps(&self, token_id: &str) -> Option<u32> {
        let book = self.inner.get(token_id)?;
        let bid = book.bids.read().best_price(true)?;
        let ask = book.asks.read().best_price(false)?;
        if bid.is_zero() {
            return None;
        }
        let spread_bps = ((ask - bid) / bid * Decimal::from(10000))
            .to_string()
            .parse::<u32>()
            .ok()?;
        Some(spread_bps)
    }

    /// Find markets with wide spreads
    pub fn find_wide_spreads(&self, min_bps: u32) -> Vec<String> {
        self.inner.find_wide_spread_markets(min_bps)
    }

    /// Get top N bids as JSON
    pub fn top_bids_json(&self, token_id: &str, n: usize) -> Option<String> {
        let book = self.inner.get(token_id)?;
        let levels = book.bids.read().top_n(n, true);
        serde_json::to_string(&levels).ok()
    }

    /// Get top N asks as JSON
    pub fn top_asks_json(&self, token_id: &str, n: usize) -> Option<String> {
        let book = self.inner.get(token_id)?;
        let levels = book.asks.read().top_n(n, false);
        serde_json::to_string(&levels).ok()
    }
}
