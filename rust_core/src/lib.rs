//! Polymarket HFT - Rust Core
//! The Complete 5-Bot Suite + Infrastructure

pub mod graph;
pub mod negrisk;
pub mod orderbook;
pub mod signer;
pub mod vulture;

use pyo3::prelude::*;

#[pymodule]
fn rust_core(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_class::<graph::Graph>()?;
    m.add_class::<graph::Violation>()?;
    m.add_class::<negrisk::NegRisk>()?;
    m.add_class::<negrisk::NegRiskConfig>()?;
    m.add_class::<negrisk::Opportunity>()?;
    m.add_class::<vulture::Vulture>()?;
    m.add_class::<vulture::VultureConfig>()?;
    m.add_class::<vulture::MarketOpportunity>()?;
    m.add_class::<orderbook::PyOrderbook>()?;
    m.add_class::<orderbook::PyOrderbookManager>()?;
    m.add_class::<signer::PySigner>()?;
    Ok(())
}
