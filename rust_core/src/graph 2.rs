//! Correlation Scanner (Bot 1)
//! DAG for monotonicity and subset violation detection

use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::Direction;
use pyo3::prelude::*;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::str::FromStr;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MarketRelation {
    Implies,
    Exclusive,
    Contains,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketNode {
    pub market_id: String,
    pub token_id: String,
    pub description: String,
    pub current_price: Option<Decimal>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketEdge {
    pub relation: MarketRelation,
    pub weight: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CorrelationViolation {
    pub violation_type: ViolationType,
    pub parent_market: String,
    pub child_market: String,
    pub parent_price: Decimal,
    pub child_price: Decimal,
    pub expected_relation: String,
    pub arbitrage_edge_bps: i32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ViolationType {
    MonotonicityViolation,
    SubsetViolation,
    ExclusivityViolation,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DutchBookTrade {
    pub long_market: String,
    pub long_token_id: String,
    pub short_market: String,
    pub short_token_id: String,
    pub expected_profit_bps: i32,
}

pub struct CorrelationScanner {
    graph: DiGraph<MarketNode, MarketEdge>,
    market_to_node: HashMap<String, NodeIndex>,
    min_edge_bps: i32,
}

impl CorrelationScanner {
    pub fn new(min_edge_bps: i32) -> Self {
        Self {
            graph: DiGraph::new(),
            market_to_node: HashMap::new(),
            min_edge_bps,
        }
    }

    pub fn add_market(&mut self, node: MarketNode) -> NodeIndex {
        if let Some(&existing) = self.market_to_node.get(&node.market_id) {
            if let Some(market) = self.graph.node_weight_mut(existing) {
                market.current_price = node.current_price;
            }
            return existing;
        }
        let market_id = node.market_id.clone();
        let idx = self.graph.add_node(node);
        self.market_to_node.insert(market_id, idx);
        idx
    }

    pub fn add_relationship(
        &mut self, parent_id: &str, child_id: &str, relation: MarketRelation, weight: f64
    ) -> Result<(), ScannerError> {
        let parent_idx = self.market_to_node.get(parent_id)
            .ok_or_else(|| ScannerError::MarketNotFound(parent_id.to_string()))?;
        let child_idx = self.market_to_node.get(child_id)
            .ok_or_else(|| ScannerError::MarketNotFound(child_id.to_string()))?;
        self.graph.add_edge(*parent_idx, *child_idx, MarketEdge { relation, weight });
        Ok(())
    }

    pub fn update_price(&mut self, market_id: &str, price: Decimal) {
        if let Some(&idx) = self.market_to_node.get(market_id) {
            if let Some(node) = self.graph.node_weight_mut(idx) {
                node.current_price = Some(price);
            }
        }
    }

    pub fn scan_violations(&self) -> Vec<CorrelationViolation> {
        let mut violations = Vec::new();
        for edge_idx in self.graph.edge_indices() {
            if let Some((p, c)) = self.graph.edge_endpoints(edge_idx) {
                if let Some(v) = self.check_edge(p, c, edge_idx) {
                    if v.arbitrage_edge_bps >= self.min_edge_bps { violations.push(v); }
                }
            }
        }
        for node_idx in self.graph.node_indices() {
            let children: Vec<NodeIndex> = self.graph.neighbors_directed(node_idx, Direction::Outgoing).collect();
            if children.len() > 1 {
                if let Some(v) = self.check_exclusivity(&children) {
                    if v.arbitrage_edge_bps >= self.min_edge_bps { violations.push(v); }
                }
            }
        }
        violations
    }

    fn check_edge(&self, parent_idx: NodeIndex, child_idx: NodeIndex, edge_idx: petgraph::graph::EdgeIndex) -> Option<CorrelationViolation> {
        let parent = self.graph.node_weight(parent_idx)?;
        let child = self.graph.node_weight(child_idx)?;
        let edge = self.graph.edge_weight(edge_idx)?;
        let pp = parent.current_price?;
        let cp = child.current_price?;
        
        if (edge.relation == MarketRelation::Implies || edge.relation == MarketRelation::Contains) && cp > pp {
            let bps = ((cp - pp) / pp * Decimal::from(10000)).to_string().parse::<i32>().unwrap_or(0);
            let vt = if edge.relation == MarketRelation::Implies { ViolationType::MonotonicityViolation } else { ViolationType::SubsetViolation };
            return Some(CorrelationViolation {
                violation_type: vt, parent_market: parent.market_id.clone(), child_market: child.market_id.clone(),
                parent_price: pp, child_price: cp, expected_relation: "P(Child) <= P(Parent)".into(), arbitrage_edge_bps: bps,
            });
        }
        None
    }

    fn check_exclusivity(&self, nodes: &[NodeIndex]) -> Option<CorrelationViolation> {
        let prices: Vec<(String, Decimal)> = nodes.iter()
            .filter_map(|&idx| { let n = self.graph.node_weight(idx)?; Some((n.market_id.clone(), n.current_price?)) }).collect();
        if prices.len() < 2 { return None; }
        let sum: Decimal = prices.iter().map(|(_, p)| *p).sum();
        if sum > Decimal::ONE {
            let bps = ((sum - Decimal::ONE) * Decimal::from(10000)).to_string().parse::<i32>().unwrap_or(0);
            let mut sorted = prices.clone(); sorted.sort_by(|a, b| b.1.cmp(&a.1));
            return Some(CorrelationViolation {
                violation_type: ViolationType::ExclusivityViolation,
                parent_market: sorted.get(0).map(|(m,_)| m.clone()).unwrap_or_default(),
                child_market: sorted.get(1).map(|(m,_)| m.clone()).unwrap_or_default(),
                parent_price: sorted.get(0).map(|(_,p)| *p).unwrap_or_default(),
                child_price: sorted.get(1).map(|(_,p)| *p).unwrap_or_default(),
                expected_relation: format!("Sum <= 1.00, actual: {}", sum), arbitrage_edge_bps: bps,
            });
        }
        None
    }

    pub fn generate_dutch_book(&self, v: &CorrelationViolation) -> Option<DutchBookTrade> {
        let pn = self.market_to_node.get(&v.parent_market).and_then(|&i| self.graph.node_weight(i))?;
        let cn = self.market_to_node.get(&v.child_market).and_then(|&i| self.graph.node_weight(i))?;
        Some(DutchBookTrade { long_market: v.parent_market.clone(), long_token_id: pn.token_id.clone(),
            short_market: v.child_market.clone(), short_token_id: cn.token_id.clone(), expected_profit_bps: v.arbitrage_edge_bps })
    }
}

#[derive(Debug, thiserror::Error)]
pub enum ScannerError { #[error("Market not found: {0}")] MarketNotFound(String), }

#[pyclass]
pub struct PyCorrelationScanner { inner: std::sync::Mutex<CorrelationScanner>, }

#[pymethods]
impl PyCorrelationScanner {
    #[new]
    #[pyo3(signature = (min_edge_bps=50))]
    pub fn new(min_edge_bps: i32) -> Self { Self { inner: std::sync::Mutex::new(CorrelationScanner::new(min_edge_bps)) } }

    pub fn add_market(&self, json: &str) -> PyResult<()> {
        let node: MarketNode = serde_json::from_str(json).map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        self.inner.lock().unwrap().add_market(node); Ok(())
    }

    pub fn add_relationship(&self, parent_id: &str, child_id: &str, relation: &str, weight: f64) -> PyResult<()> {
        let rel = match relation.to_lowercase().as_str() { "implies" => MarketRelation::Implies, "contains" => MarketRelation::Contains, "exclusive" => MarketRelation::Exclusive,
            _ => return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Unknown relation")) };
        self.inner.lock().unwrap().add_relationship(parent_id, child_id, rel, weight).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    pub fn update_price(&self, market_id: &str, price: &str) -> PyResult<()> {
        let p = Decimal::from_str(price).map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        self.inner.lock().unwrap().update_price(market_id, p); Ok(())
    }

    pub fn scan(&self) -> PyResult<String> { serde_json::to_string(&self.inner.lock().unwrap().scan_violations()).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string())) }
}
