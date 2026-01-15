use pyo3::prelude::*;

pub mod vulture;

use vulture::Vulture;

/// Rust Core module for Polymarket HFT Bot
/// Provides high-performance trading primitives
#[pymodule]
fn rust_core(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_class::<Vulture>()?;
    Ok(())
}
