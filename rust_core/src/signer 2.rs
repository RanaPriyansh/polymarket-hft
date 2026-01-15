//! EIP-712 Signing for Polymarket Gasless Maker Orders
//! Implements the signing logic for CTF Exchange orders

use ethers::core::types::{Address, H256, U256};
use ethers::signers::{LocalWallet, Signer};
use pyo3::prelude::*;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use sha3::{Digest, Keccak256};
use std::str::FromStr;
use std::sync::atomic::{AtomicU64, Ordering};

/// Polymarket Chain ID (Polygon)
const CHAIN_ID: u64 = 137;

/// CTF Exchange Contract
const CTF_EXCHANGE: &str = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E";

/// NegRisk CTF Exchange
const NEGRISK_CTF_EXCHANGE: &str = "0xC5d563A36AE78145C45a50134d48A1215220f80a";

/// Order side
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum Side {
    Buy = 0,
    Sell = 1,
}

/// Signature type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum SignatureType {
    Eoa = 0,
    Poly = 1,
    PolyProxy = 2,
}

/// Order structure matching Polymarket CLOB
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Order {
    pub salt: U256,
    pub maker: Address,
    pub signer: Address,
    pub taker: Address,
    pub token_id: U256,
    pub maker_amount: U256,
    pub taker_amount: U256,
    pub expiration: U256,
    pub nonce: U256,
    pub fee_rate_bps: U256,
    pub side: Side,
    pub signature_type: SignatureType,
}

/// Signed order ready for submission
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignedOrder {
    pub order: Order,
    pub signature: String,
}

/// EIP-712 Domain Separator components
struct EIP712Domain {
    name: String,
    version: String,
    chain_id: U256,
    verifying_contract: Address,
}

impl EIP712Domain {
    fn new(is_negrisk: bool) -> Self {
        let contract = if is_negrisk {
            NEGRISK_CTF_EXCHANGE
        } else {
            CTF_EXCHANGE
        };

        Self {
            name: "Polymarket CTF Exchange".to_string(),
            version: "1".to_string(),
            chain_id: U256::from(CHAIN_ID),
            verifying_contract: Address::from_str(contract).unwrap(),
        }
    }

    fn separator_hash(&self) -> H256 {
        let type_hash = keccak256(
            b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)",
        );

        let mut data = Vec::new();
        data.extend_from_slice(type_hash.as_slice());
        data.extend_from_slice(keccak256(self.name.as_bytes()).as_slice());
        data.extend_from_slice(keccak256(self.version.as_bytes()).as_slice());
        data.extend_from_slice(&u256_to_bytes32(self.chain_id));
        data.extend_from_slice(self.verifying_contract.as_bytes());

        H256::from_slice(&keccak256(&data))
    }
}

/// Main signer for Polymarket orders
pub struct PolymarketSigner {
    wallet: LocalWallet,
    nonce: AtomicU64,
    is_negrisk: bool,
}

impl PolymarketSigner {
    pub fn new(private_key: &str, is_negrisk: bool) -> Result<Self, SignerError> {
        let key = private_key.strip_prefix("0x").unwrap_or(private_key);
        let wallet = LocalWallet::from_str(key)
            .map_err(|e| SignerError::InvalidKey(e.to_string()))?
            .with_chain_id(CHAIN_ID);

        Ok(Self {
            wallet,
            nonce: AtomicU64::new(0),
            is_negrisk,
        })
    }

    /// Get signer address
    pub fn address(&self) -> Address {
        self.wallet.address()
    }

    /// Generate next nonce
    pub fn next_nonce(&self) -> U256 {
        U256::from(self.nonce.fetch_add(1, Ordering::SeqCst))
    }

    /// Set nonce (for synchronization with chain state)
    pub fn set_nonce(&self, nonce: u64) {
        self.nonce.store(nonce, Ordering::SeqCst);
    }

    /// Create and sign a limit order
    pub async fn create_limit_order(
        &self,
        token_id: &str,
        price: Decimal,
        size: Decimal,
        side: Side,
        expiration_secs: u64,
    ) -> Result<SignedOrder, SignerError> {
        let token_id_u256 = U256::from_str_radix(
            token_id.strip_prefix("0x").unwrap_or(token_id),
            16,
        )
        .map_err(|e| SignerError::InvalidTokenId(e.to_string()))?;

        // Calculate amounts based on side
        // For BUY: maker pays USDC, receives tokens
        // For SELL: maker pays tokens, receives USDC
        let (maker_amount, taker_amount) = match side {
            Side::Buy => {
                let usdc_amount = (price * size * Decimal::from(1_000_000))
                    .to_string()
                    .parse::<u128>()
                    .unwrap_or(0);
                let token_amount = (size * Decimal::from(1_000_000))
                    .to_string()
                    .parse::<u128>()
                    .unwrap_or(0);
                (U256::from(usdc_amount), U256::from(token_amount))
            }
            Side::Sell => {
                let token_amount = (size * Decimal::from(1_000_000))
                    .to_string()
                    .parse::<u128>()
                    .unwrap_or(0);
                let usdc_amount = (price * size * Decimal::from(1_000_000))
                    .to_string()
                    .parse::<u128>()
                    .unwrap_or(0);
                (U256::from(token_amount), U256::from(usdc_amount))
            }
        };

        let current_time = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();

        let order = Order {
            salt: generate_salt(),
            maker: self.address(),
            signer: self.address(),
            taker: Address::zero(),
            token_id: token_id_u256,
            maker_amount,
            taker_amount,
            expiration: U256::from(current_time + expiration_secs),
            nonce: self.next_nonce(),
            fee_rate_bps: U256::zero(),
            side,
            signature_type: SignatureType::Eoa,
        };

        let signature = self.sign_order(&order).await?;

        Ok(SignedOrder { order, signature })
    }

    /// Sign an order using EIP-712
    async fn sign_order(&self, order: &Order) -> Result<String, SignerError> {
        let domain = EIP712Domain::new(self.is_negrisk);
        let domain_separator = domain.separator_hash();

        // Type hash for Order struct
        let order_type_hash = keccak256(
            b"Order(uint256 salt,address maker,address signer,address taker,uint256 tokenId,uint256 makerAmount,uint256 takerAmount,uint256 expiration,uint256 nonce,uint256 feeRateBps,uint8 side,uint8 signatureType)",
        );

        // Encode order data
        let mut order_data = Vec::new();
        order_data.extend_from_slice(order_type_hash.as_slice());
        order_data.extend_from_slice(&u256_to_bytes32(order.salt));
        order_data.extend_from_slice(&address_to_bytes32(order.maker));
        order_data.extend_from_slice(&address_to_bytes32(order.signer));
        order_data.extend_from_slice(&address_to_bytes32(order.taker));
        order_data.extend_from_slice(&u256_to_bytes32(order.token_id));
        order_data.extend_from_slice(&u256_to_bytes32(order.maker_amount));
        order_data.extend_from_slice(&u256_to_bytes32(order.taker_amount));
        order_data.extend_from_slice(&u256_to_bytes32(order.expiration));
        order_data.extend_from_slice(&u256_to_bytes32(order.nonce));
        order_data.extend_from_slice(&u256_to_bytes32(order.fee_rate_bps));
        order_data.extend_from_slice(&u8_to_bytes32(order.side as u8));
        order_data.extend_from_slice(&u8_to_bytes32(order.signature_type as u8));

        let struct_hash = H256::from_slice(&keccak256(&order_data));

        // Final message hash: \x19\x01 || domainSeparator || structHash
        let mut message = Vec::new();
        message.push(0x19);
        message.push(0x01);
        message.extend_from_slice(domain_separator.as_bytes());
        message.extend_from_slice(struct_hash.as_bytes());

        let message_hash = H256::from_slice(&keccak256(&message));

        // Sign the hash
        let signature = self
            .wallet
            .sign_hash(message_hash)
            .map_err(|e| SignerError::SigningError(e.to_string()))?;

        // Return signature as hex string with 0x prefix
        Ok(format!("0x{}", hex::encode(signature.to_vec())))
    }

    /// Cancel an order (by incrementing nonce)
    pub fn cancel_all_orders(&self) {
        // In Polymarket, incrementing the nonce cancels all orders with lower nonces
        self.next_nonce();
    }
}

/// Generate random salt for order uniqueness
fn generate_salt() -> U256 {
    use std::time::{SystemTime, UNIX_EPOCH};
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let random_part: u64 = rand_simple();
    U256::from(timestamp as u64) << 64 | U256::from(random_part)
}

/// Simple random number (not cryptographically secure, but fine for salt)
fn rand_simple() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .subsec_nanos();
    nanos as u64 ^ 0xDEADBEEF
}

/// Keccak256 hash
fn keccak256(data: &[u8]) -> [u8; 32] {
    let mut hasher = Keccak256::new();
    hasher.update(data);
    hasher.finalize().into()
}

/// Convert U256 to 32-byte array
fn u256_to_bytes32(value: U256) -> [u8; 32] {
    let mut bytes = [0u8; 32];
    value.to_big_endian(&mut bytes);
    bytes
}

/// Convert Address to 32-byte array (left-padded)
fn address_to_bytes32(addr: Address) -> [u8; 32] {
    let mut bytes = [0u8; 32];
    bytes[12..].copy_from_slice(addr.as_bytes());
    bytes
}

/// Convert u8 to 32-byte array (left-padded)
fn u8_to_bytes32(value: u8) -> [u8; 32] {
    let mut bytes = [0u8; 32];
    bytes[31] = value;
    bytes
}

#[derive(Debug, thiserror::Error)]
pub enum SignerError {
    #[error("Invalid private key: {0}")]
    InvalidKey(String),

    #[error("Invalid token ID: {0}")]
    InvalidTokenId(String),

    #[error("Signing error: {0}")]
    SigningError(String),
}

// ============ PyO3 Bindings ============

#[pyclass]
pub struct PySigner {
    inner: PolymarketSigner,
    runtime: tokio::runtime::Runtime,
}

#[pymethods]
impl PySigner {
    #[new]
    #[pyo3(signature = (private_key, is_negrisk=false))]
    pub fn new(private_key: &str, is_negrisk: bool) -> PyResult<Self> {
        let runtime = tokio::runtime::Runtime::new()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;

        let inner = PolymarketSigner::new(private_key, is_negrisk)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;

        Ok(Self { inner, runtime })
    }

    /// Get signer address
    pub fn address(&self) -> String {
        format!("{:?}", self.inner.address())
    }

    /// Create and sign a BUY limit order, returns JSON
    pub fn create_buy_order(
        &self,
        token_id: &str,
        price: &str,
        size: &str,
        expiration_secs: u64,
    ) -> PyResult<String> {
        let price_dec = Decimal::from_str(price)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        let size_dec = Decimal::from_str(size)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;

        self.runtime.block_on(async {
            let signed = self
                .inner
                .create_limit_order(token_id, price_dec, size_dec, Side::Buy, expiration_secs)
                .await
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;

            serde_json::to_string(&signed)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
        })
    }

    /// Create and sign a SELL limit order, returns JSON
    pub fn create_sell_order(
        &self,
        token_id: &str,
        price: &str,
        size: &str,
        expiration_secs: u64,
    ) -> PyResult<String> {
        let price_dec = Decimal::from_str(price)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        let size_dec = Decimal::from_str(size)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;

        self.runtime.block_on(async {
            let signed = self
                .inner
                .create_limit_order(token_id, price_dec, size_dec, Side::Sell, expiration_secs)
                .await
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;

            serde_json::to_string(&signed)
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))
        })
    }

    /// Set the current nonce
    pub fn set_nonce(&self, nonce: u64) {
        self.inner.set_nonce(nonce);
    }

    /// Cancel all orders by incrementing nonce
    pub fn cancel_all(&self) {
        self.inner.cancel_all_orders();
    }
}
