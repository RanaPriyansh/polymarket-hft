"""
Polymarket HFT Configuration
Central configuration for all bots and infrastructure
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class PolymarketConfig(BaseSettings):
    """Main configuration for Polymarket HFT system"""
    
    # API Keys - support multiple common env var names
    polymarket_api_key: str = Field(
        default="", 
        validation_alias="POLY_API_KEY",  # Common alternative
    )
    polymarket_api_secret: str = Field(
        default="",
        validation_alias="POLY_API_SECRET",
    )
    polymarket_passphrase: str = Field(
        default="",
        validation_alias="POLY_API_PASSPHRASE",
    )
    
    # Wallet
    private_key: str = Field(default="", validation_alias="PRIVATE_KEY")
    wallet_address: str = Field(default="", validation_alias="WALLET_ADDRESS")
    
    # LLM (Semantic Sentinel)
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    
    # Twitter (Semantic Sentinel)
    twitter_bearer_token: str = Field(default="", validation_alias="TWITTER_BEARER_TOKEN")
    
    # Endpoints - support common aliases
    clob_http_endpoint: str = Field(
        default="https://clob.polymarket.com",
        validation_alias="POLY_HOST",
    )
    clob_ws_endpoint: str = Field(
        default="wss://ws-subscriptions-clob.polymarket.com/ws",
        validation_alias="POLY_WS_HOST",
    )
    gamma_api_endpoint: str = "https://gamma-api.polymarket.com"
    polygon_rpc: str = Field(
        default="https://polygon-rpc.com", 
        validation_alias="POLYGON_RPC_URL",
    )
    
    # NegRisk Contract
    negrisk_adapter_address: str = Field(
        default="0xd91E80a2E199D407E53f37dE8A6bA5C6ec2849D0",
        validation_alias="NEGRISK_ADAPTER",
    )
    negrisk_ctf_exchange: str = Field(
        default="0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
        validation_alias="CTF_EXCHANGE",
    )
    
    # Trading Parameters
    max_position_size_usd: float = 1000.0
    min_edge_bps: int = 50  # 0.5% minimum edge
    max_gas_gwei: int = 100
    
    # Bot-specific configs
    vulture_min_spread_bps: int = 500  # 5% for zombie markets
    vulture_max_volume_usd: float = 500.0
    
    resolution_sniper_min_discount: float = 0.02  # Buy at 0.98 for $1 outcome
    resolution_sniper_griefing_threshold: float = 0.1  # 10% dispute probability max
    
    negrisk_min_arb_bps: int = 30  # 0.3% after fees
    
    # Risk Management
    emergency_mode: bool = False
    max_daily_loss_usd: float = 500.0
    reorg_protection_blocks: int = 3
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # Ignore unknown env vars
        "populate_by_name": True,  # Allow both field name and alias
    }


class WebSocketConfig(BaseSettings):
    """WebSocket connection configuration"""
    
    reconnect_delay_ms: int = 1000
    max_reconnect_attempts: int = 10
    heartbeat_interval_ms: int = 30000
    snapshot_refresh_interval_s: int = 300
    
    model_config = {
        "env_prefix": "WS_",
        "extra": "ignore",
    }


# Global config instances
config = PolymarketConfig()
ws_config = WebSocketConfig()


# Contract ABIs (minimal for our use case)
NEGRISK_ADAPTER_ABI = [
    {
        "inputs": [{"name": "conditionId", "type": "bytes32"}],
        "name": "getOutcomeSlotCount",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "conditionId", "type": "bytes32"},
            {"name": "partition", "type": "uint256[]"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "splitPosition",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "conditionId", "type": "bytes32"},
            {"name": "partition", "type": "uint256[]"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "mergePositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# EIP-712 Domain for Polymarket CLOB
EIP712_DOMAIN = {
    "name": "Polymarket CTF Exchange",
    "version": "1",
    "chainId": 137,  # Polygon
    "verifyingContract": "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
}

EIP712_ORDER_TYPES = {
    "Order": [
        {"name": "salt", "type": "uint256"},
        {"name": "maker", "type": "address"},
        {"name": "signer", "type": "address"},
        {"name": "taker", "type": "address"},
        {"name": "tokenId", "type": "uint256"},
        {"name": "makerAmount", "type": "uint256"},
        {"name": "takerAmount", "type": "uint256"},
        {"name": "expiration", "type": "uint256"},
        {"name": "nonce", "type": "uint256"},
        {"name": "feeRateBps", "type": "uint256"},
        {"name": "side", "type": "uint8"},
        {"name": "signatureType", "type": "uint8"}
    ]
}
