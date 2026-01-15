"""Polymarket HFT Bot Configuration"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")


class Settings:
    """Bot configuration settings."""
    
    # API Credentials
    PRIVATE_KEY: str = os.getenv("PRIVATE_KEY", "")
    WALLET_ADDRESS: str = os.getenv("WALLET_ADDRESS", "")
    POLY_API_KEY: str = os.getenv("POLY_API_KEY", "")
    POLY_API_SECRET: str = os.getenv("POLY_API_SECRET", "")
    POLY_API_PASSPHRASE: str = os.getenv("POLY_API_PASSPHRASE", "")
    POLYGON_RPC_URL: str = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    
    # Trading Parameters
    DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"
    CONDITION_ID_OVERRIDE: str = os.getenv("CONDITION_ID_OVERRIDE", "")
    
    # Vulture Config
    MIN_SPREAD_BPS: float = float(os.getenv("MIN_SPREAD_BPS", "50"))
    MAX_SPREAD_BPS: float = float(os.getenv("MAX_SPREAD_BPS", "500"))
    EDGE_FRACTION: float = float(os.getenv("EDGE_FRACTION", "0.25"))
    
    # API Endpoints
    CLOB_API_URL: str = "https://clob.polymarket.com"
    GAMMA_API_URL: str = "https://gamma-api.polymarket.com"
    
    @classmethod
    def is_configured(cls) -> bool:
        """Check if minimum required config is present."""
        required = [
            cls.PRIVATE_KEY,
            cls.WALLET_ADDRESS,
            cls.POLY_API_KEY,
            cls.POLY_API_SECRET,
            cls.POLY_API_PASSPHRASE,
        ]
        return all(v and v != "REPLACE_ME" for v in required)


settings = Settings()
