//! Signer Module - EIP-712 Signing for Polymarket CTF Orders
//! 
//! Implements order signing compatible with Polymarket's CTF Exchange:
//! - EIP-712 typed data hashing
//! - Order struct serialization
//! - Signature generation

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use sha3::{Digest, Keccak256};

/// EIP-712 Domain for Polymarket CTF Exchange
const DOMAIN_NAME: &str = "Polymarket CTF Exchange";
const DOMAIN_VERSION: &str = "1";
const CHAIN_ID: u64 = 137; // Polygon mainnet

/// Order side
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum OrderSide {
    Buy = 0,
    Sell = 1,
}

/// Order type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SignatureType {
    EOA = 0,
    PolyProxy = 1,
    PolyGnosisSafe = 2,
}

/// A Polymarket CTF Order
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Order {
    pub salt: String,
    pub maker: String,
    pub signer: String,
    pub taker: String,
    pub token_id: String,
    pub maker_amount: String,
    pub taker_amount: String,
    pub expiration: String,
    pub nonce: String,
    pub fee_rate_bps: String,
    pub side: OrderSide,
    pub signature_type: SignatureType,
}

impl Order {
    /// Create a new order
    pub fn new(
        maker: String,
        token_id: String,
        side: OrderSide,
        price: f64,
        size: f64,
        expiration_secs: u64,
    ) -> Self {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        
        // Generate random salt
        let salt = format!("{:016x}{:016x}", rand_u64(), rand_u64());
        
        // Calculate amounts based on side
        let (maker_amount, taker_amount) = match side {
            OrderSide::Buy => {
                // Buying: paying USDC, receiving shares
                let usdc_amount = (price * size * 1_000_000.0) as u64; // 6 decimals
                let share_amount = (size * 1_000_000.0) as u64;
                (usdc_amount.to_string(), share_amount.to_string())
            }
            OrderSide::Sell => {
                // Selling: paying shares, receiving USDC
                let share_amount = (size * 1_000_000.0) as u64;
                let usdc_amount = (price * size * 1_000_000.0) as u64;
                (share_amount.to_string(), usdc_amount.to_string())
            }
        };

        Self {
            salt,
            maker: maker.clone(),
            signer: maker,
            taker: "0x0000000000000000000000000000000000000000".to_string(),
            token_id,
            maker_amount,
            taker_amount,
            expiration: (now + expiration_secs).to_string(),
            nonce: "0".to_string(),
            fee_rate_bps: "0".to_string(),
            side,
            signature_type: SignatureType::EOA,
        }
    }
}

/// Simple pseudo-random u64 for salt generation
fn rand_u64() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .subsec_nanos() as u64;
    nanos.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407)
}

/// Keccak256 hash helper
fn keccak256(data: &[u8]) -> [u8; 32] {
    let mut hasher = Keccak256::new();
    hasher.update(data);
    hasher.finalize().into()
}

/// EIP-712 Domain Separator
pub fn domain_separator(verifying_contract: &str) -> [u8; 32] {
    let type_hash = keccak256(
        b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
    );
    
    let name_hash = keccak256(DOMAIN_NAME.as_bytes());
    let version_hash = keccak256(DOMAIN_VERSION.as_bytes());
    
    // Encode domain struct
    let mut encoded = Vec::new();
    encoded.extend_from_slice(&type_hash);
    encoded.extend_from_slice(&name_hash);
    encoded.extend_from_slice(&version_hash);
    encoded.extend_from_slice(&encode_u256(CHAIN_ID));
    encoded.extend_from_slice(&encode_address(verifying_contract));
    
    keccak256(&encoded)
}

/// Encode u64 as u256 (32 bytes, big-endian, left-padded)
fn encode_u256(value: u64) -> [u8; 32] {
    let mut buf = [0u8; 32];
    buf[24..32].copy_from_slice(&value.to_be_bytes());
    buf
}

/// Encode address string to 32 bytes
fn encode_address(addr: &str) -> [u8; 32] {
    let addr = addr.strip_prefix("0x").unwrap_or(addr);
    let mut buf = [0u8; 32];
    if let Ok(bytes) = hex::decode(addr) {
        let start = 32 - bytes.len().min(20);
        buf[start..start + bytes.len().min(20)].copy_from_slice(&bytes[..bytes.len().min(20)]);
    }
    buf
}

/// Order type hash for EIP-712
pub fn order_type_hash() -> [u8; 32] {
    keccak256(
        b"Order(uint256 salt,address maker,address signer,address taker,uint256 tokenId,uint256 makerAmount,uint256 taker,uint256 expiration,uint256 nonce,uint256 feeRateBps,uint8 side,uint8 signatureType)"
    )
}

/// Hash an order for signing
pub fn hash_order(order: &Order) -> [u8; 32] {
    let type_hash = order_type_hash();
    
    let mut encoded = Vec::new();
    encoded.extend_from_slice(&type_hash);
    encoded.extend_from_slice(&encode_u256(u64::from_str_radix(order.salt.trim_start_matches("0x"), 16).unwrap_or(0)));
    encoded.extend_from_slice(&encode_address(&order.maker));
    encoded.extend_from_slice(&encode_address(&order.signer));
    encoded.extend_from_slice(&encode_address(&order.taker));
    encoded.extend_from_slice(&encode_u256(order.token_id.parse().unwrap_or(0)));
    encoded.extend_from_slice(&encode_u256(order.maker_amount.parse().unwrap_or(0)));
    encoded.extend_from_slice(&encode_u256(order.taker_amount.parse().unwrap_or(0)));
    encoded.extend_from_slice(&encode_u256(order.expiration.parse().unwrap_or(0)));
    encoded.extend_from_slice(&encode_u256(order.nonce.parse().unwrap_or(0)));
    encoded.extend_from_slice(&encode_u256(order.fee_rate_bps.parse().unwrap_or(0)));
    encoded.extend_from_slice(&encode_u256(order.side as u64));
    encoded.extend_from_slice(&encode_u256(order.signature_type as u64));
    
    keccak256(&encoded)
}

/// Create the final EIP-712 message hash
pub fn eip712_hash(order: &Order, verifying_contract: &str) -> [u8; 32] {
    let domain_sep = domain_separator(verifying_contract);
    let order_hash = hash_order(order);
    
    let mut msg = Vec::with_capacity(66);
    msg.push(0x19);
    msg.push(0x01);
    msg.extend_from_slice(&domain_sep);
    msg.extend_from_slice(&order_hash);
    
    keccak256(&msg)
}

// ============ PyO3 Bindings ============

#[pyclass]
pub struct PySigner {
    wallet_address: String,
    ctf_exchange: String,
}

#[pymethods]
impl PySigner {
    #[new]
    #[pyo3(signature = (wallet_address, ctf_exchange="0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"))]
    fn new(wallet_address: &str, ctf_exchange: &str) -> Self {
        Self {
            wallet_address: wallet_address.to_string(),
            ctf_exchange: ctf_exchange.to_string(),
        }
    }

    /// Create an order and return its hash for signing
    fn create_order_hash(
        &self,
        token_id: &str,
        side: &str, // "buy" or "sell"
        price: f64,
        size: f64,
        expiration_secs: u64,
    ) -> PyResult<String> {
        let order_side = match side.to_lowercase().as_str() {
            "buy" => OrderSide::Buy,
            "sell" => OrderSide::Sell,
            _ => return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Invalid side")),
        };

        let order = Order::new(
            self.wallet_address.clone(),
            token_id.to_string(),
            order_side,
            price,
            size,
            expiration_secs,
        );

        let hash = eip712_hash(&order, &self.ctf_exchange);
        Ok(format!("0x{}", hex::encode(hash)))
    }

    /// Build a complete order as JSON
    fn build_order(
        &self,
        token_id: &str,
        side: &str,
        price: f64,
        size: f64,
        expiration_secs: u64,
    ) -> PyResult<String> {
        let order_side = match side.to_lowercase().as_str() {
            "buy" => OrderSide::Buy,
            "sell" => OrderSide::Sell,
            _ => return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Invalid side")),
        };

        let order = Order::new(
            self.wallet_address.clone(),
            token_id.to_string(),
            order_side,
            price,
            size,
            expiration_secs,
        );

        serde_json::to_string(&order)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
    }

    /// Get domain separator hash
    fn domain_separator(&self) -> String {
        let sep = domain_separator(&self.ctf_exchange);
        format!("0x{}", hex::encode(sep))
    }

    fn __repr__(&self) -> String {
        format!("Signer(wallet={}, exchange={})", 
            &self.wallet_address[..10.min(self.wallet_address.len())],
            &self.ctf_exchange[..10.min(self.ctf_exchange.len())]
        )
    }
}
