//! Graph Module - Bot 1: The Correlation Scanner
//! 
//! A Directed Acyclic Graph (DAG) detector for market correlations.
//! Detects Monotonicity Violations: P(Child) cannot be < P(Parent) when correlation=1.0
//! 
//! Example: If "Trump wins PA" implies "Trump wins Election" with correlation 1.0,
//! then P(Election) >= P(PA) must hold.

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// A node in the correlation graph (represents a market)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Node {
    pub market_id: String,
    pub description: String,
}

/// An edge in the DAG (represents conditional probability)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Edge {
    /// Parent market (if this happens...)
    pub parent_id: String,
    /// Child market (...this must also happen)
    pub child_id: String,
    /// Correlation strength (1.0 = perfect implication)
    pub correlation: f64,
}

/// A monotonicity violation detected by the scanner
#[derive(Debug, Clone, Serialize, Deserialize)]
#[pyclass]
pub struct Violation {
    #[pyo3(get)]
    pub parent_id: String,
    #[pyo3(get)]
    pub child_id: String,
    #[pyo3(get)]
    pub parent_price: f64,
    #[pyo3(get)]
    pub child_price: f64,
    #[pyo3(get)]
    pub correlation: f64,
    /// How much child is underpriced (parent - child)
    #[pyo3(get)]
    pub mispricing: f64,
    /// Mispricing in basis points
    #[pyo3(get)]
    pub mispricing_bps: f64,
    #[pyo3(get)]
    pub action: String,
}

#[pymethods]
impl Violation {
    fn __repr__(&self) -> String {
        format!(
            "Violation({} -> {}: P({:.2}) < P({:.2}), mispricing={}bps)",
            self.parent_id, self.child_id,
            self.child_price, self.parent_price,
            self.mispricing_bps as i64
        )
    }
}

/// The Correlation Scanner DAG
#[derive(Debug, Default)]
pub struct CorrelationDAG {
    nodes: HashMap<String, Node>,
    edges: Vec<Edge>,
}

impl CorrelationDAG {
    pub fn new() -> Self {
        Self::default()
    }

    /// Add a market node
    pub fn add_node(&mut self, market_id: &str, description: &str) {
        self.nodes.insert(market_id.to_string(), Node {
            market_id: market_id.to_string(),
            description: description.to_string(),
        });
    }

    /// Add a correlation edge: parent implies child
    /// correlation=1.0 means perfect implication (parent happening guarantees child)
    pub fn add_edge(&mut self, parent_id: &str, child_id: &str, correlation: f64) {
        self.edges.push(Edge {
            parent_id: parent_id.to_string(),
            child_id: child_id.to_string(),
            correlation: correlation.clamp(0.0, 1.0),
        });
    }

    /// Scan for monotonicity violations given current prices
    /// Rule: P(Child) >= P(Parent) * correlation
    /// If P(Child) < P(Parent) and correlation=1.0, it's a violation
    pub fn scan(&self, prices: &HashMap<String, f64>) -> Vec<Violation> {
        let mut violations = Vec::new();

        for edge in &self.edges {
            let parent_price = prices.get(&edge.parent_id).copied();
            let child_price = prices.get(&edge.child_id).copied();

            if let (Some(pp), Some(cp)) = (parent_price, child_price) {
                // Expected minimum child price based on correlation
                let expected_min = pp * edge.correlation;
                
                // VIOLATION: Child is priced LOWER than it should be
                // If parent=0.70, child=0.50, and correlation=1.0, child is underpriced
                if cp < expected_min {
                    let mispricing = expected_min - cp;
                    let mispricing_bps = (mispricing / cp) * 10_000.0;
                    
                    violations.push(Violation {
                        parent_id: edge.parent_id.clone(),
                        child_id: edge.child_id.clone(),
                        parent_price: pp,
                        child_price: cp,
                        correlation: edge.correlation,
                        mispricing,
                        mispricing_bps,
                        action: format!("BUY {} (underpriced) / SELL {} (overpriced)", 
                            edge.child_id, edge.parent_id),
                    });
                }
            }
        }

        violations
    }
}

// ============ PyO3 Bindings ============

/// Bot 1: The Correlation Scanner
#[pyclass]
pub struct Graph {
    dag: CorrelationDAG,
    min_violation_bps: f64,
}

#[pymethods]
impl Graph {
    #[new]
    #[pyo3(signature = (min_violation_bps=50.0))]
    fn new(min_violation_bps: f64) -> Self {
        Self {
            dag: CorrelationDAG::new(),
            min_violation_bps,
        }
    }

    /// Add a market node to the graph
    fn add_node(&mut self, market_id: &str, description: &str) {
        self.dag.add_node(market_id, description);
    }

    /// Add a correlation: parent implies child with given correlation strength
    /// Example: add_edge("trump-wins-pa", "trump-wins-election", 1.0)
    fn add_edge(&mut self, parent_id: &str, child_id: &str, correlation: f64) {
        self.dag.add_edge(parent_id, child_id, correlation);
    }

    /// Scan for monotonicity violations given a price map
    /// prices: list of (market_id, price) tuples
    fn scan(&self, prices: Vec<(String, f64)>) -> Vec<Violation> {
        let price_map: HashMap<String, f64> = prices.into_iter().collect();
        self.dag.scan(&price_map)
            .into_iter()
            .filter(|v| v.mispricing_bps >= self.min_violation_bps)
            .collect()
    }

    /// Scan with JSON string input
    fn scan_json(&self, prices_json: &str) -> PyResult<Vec<Violation>> {
        let prices: HashMap<String, f64> = serde_json::from_str(prices_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        Ok(self.dag.scan(&prices)
            .into_iter()
            .filter(|v| v.mispricing_bps >= self.min_violation_bps)
            .collect())
    }

    /// Get number of edges in the graph
    fn edge_count(&self) -> usize {
        self.dag.edges.len()
    }

    /// Get number of nodes
    fn node_count(&self) -> usize {
        self.dag.nodes.len()
    }

    fn __repr__(&self) -> String {
        format!(
            "Graph(nodes={}, edges={}, min_violation={}bps)",
            self.dag.nodes.len(),
            self.dag.edges.len(),
            self.min_violation_bps
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_monotonicity_violation() {
        let mut dag = CorrelationDAG::new();
        
        // If Trump wins PA, he wins the election (correlation=1.0)
        dag.add_edge("trump-wins-pa", "trump-wins-election", 1.0);
        
        let mut prices = HashMap::new();
        prices.insert("trump-wins-pa".to_string(), 0.70);
        prices.insert("trump-wins-election".to_string(), 0.50); // VIOLATION!
        
        let violations = dag.scan(&prices);
        assert_eq!(violations.len(), 1);
        assert!(violations[0].mispricing > 0.0);
    }

    #[test]
    fn test_no_violation() {
        let mut dag = CorrelationDAG::new();
        dag.add_edge("trump-wins-pa", "trump-wins-election", 1.0);
        
        let mut prices = HashMap::new();
        prices.insert("trump-wins-pa".to_string(), 0.50);
        prices.insert("trump-wins-election".to_string(), 0.70); // Valid: child > parent
        
        let violations = dag.scan(&prices);
        assert_eq!(violations.len(), 0);
    }
}
