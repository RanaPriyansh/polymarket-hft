//! Polymarket HFT - Rust Core
//! The Complete 5-Bot Suite + Infrastructure
//! 
//! Bot 1: Graph (Correlation Scanner) - Monotonicity Violations
//! Bot 2: NegRisk (Unity Constraint) - Mint-and-Sell / Buy-and-Merge
//! Bot 3: ResolutionSniper (Python) - UMA Oracle Liveness
//! Bot 4: Vulture (Zombie Market Maker) - Rebate Farming
//! Bot 5: SemanticSentinel (Python) - News Latency Arbitrage
//! 
//! Infrastructure: Orderbook, Signer

pub mod graph;
pub mod negrisk;
pub mod orderbook;
pub mod signer;
pub mod vulture;

use pyo3::prelude::*;

/// Python module for rust_core - The Full 5-Bot Suite
#[pymodule]
fn rust_core(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    // Bot 1: Correlation Scanner (DAG)
    m.add_class::<graph::Graph>()?;
    m.add_class::<graph::Violation>()?;
    
    // Bot 2: NegRisk Miner (Unity Constraint)
    m.add_class::<negrisk::NegRisk>()?;
    m.add_class::<negrisk::NegRiskConfig>()?;
    m.add_class::<negrisk::Opportunity>()?;
    
    // Bot 4: Vulture (Zombie Market Maker)
    m.add_class::<vulture::Vulture>()?;
    m.add_class::<vulture::VultureConfig>()?;
    m.add_class::<vulture::MarketOpportunity>()?;
    
    // Infrastructure
    m.add_class::<orderbook::PyOrderbook>()?;
    m.add_class::<orderbook::PyOrderbookManager>()?;
    m.add_class::<signer::PySigner>()?;
    
    Ok(())
}
