"""
Polymarket CLOB Client
Wrapper around py-clob-client with additional functionality
"""
import asyncio
from decimal import Decimal
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import aiohttp
import structlog

log = structlog.get_logger()


@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    error: Optional[str] = None
    filled_amount: Optional[Decimal] = None


class PolymarketCLOBClient:
    """
    High-level client for Polymarket CLOB operations
    Handles order submission, cancellation, and position management
    """
    
    BASE_URL = "https://clob.polymarket.com"
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        private_key: Optional[str] = None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.private_key = private_key
        self._session: Optional[aiohttp.ClientSession] = None
        self._signer = None
        
        if private_key:
            self._init_signer()

    def _init_signer(self):
        """Initialize Rust signer if available"""
        try:
            from polymarket_muscle import PySigner
            self._signer = PySigner(self.private_key, is_negrisk=False)
            log.info("rust_signer_initialized", address=self._signer.address())
        except ImportError:
            log.warning("rust_signer_not_available", fallback="python")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {
                "POLY_API_KEY": self.api_key,
                "POLY_API_SECRET": self.api_secret,
                "POLY_PASSPHRASE": self.passphrase,
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_orderbook(self, token_id: str) -> Dict[str, Any]:
        """Fetch orderbook snapshot"""
        session = await self._get_session()
        url = f"{self.BASE_URL}/book?token_id={token_id}"
        
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch orderbook: {resp.status}")
            return await resp.json()

    async def get_markets(self, condition_id: Optional[str] = None) -> List[Dict]:
        """Fetch markets from Gamma API"""
        session = await self._get_session()
        url = "https://gamma-api.polymarket.com/markets"
        if condition_id:
            url += f"?condition_id={condition_id}"
            
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            return await resp.json()

    async def submit_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        price: Decimal,
        size: Decimal,
        expiration_secs: int = 3600,
    ) -> OrderResult:
        """Submit a signed limit order"""
        if not self._signer:
            return OrderResult(success=False, error="Signer not initialized")
            
        try:
            # Create signed order using Rust signer
            if side == "BUY":
                signed_json = self._signer.create_buy_order(
                    token_id, str(price), str(size), expiration_secs
                )
            else:
                signed_json = self._signer.create_sell_order(
                    token_id, str(price), str(size), expiration_secs
                )
                
            # Submit to CLOB
            session = await self._get_session()
            async with session.post(
                f"{self.BASE_URL}/order",
                json={"order": signed_json},
            ) as resp:
                data = await resp.json()
                
                if resp.status == 200:
                    return OrderResult(
                        success=True,
                        order_id=data.get("orderID"),
                        filled_amount=Decimal(str(data.get("filledAmount", 0))),
                    )
                else:
                    return OrderResult(
                        success=False,
                        error=data.get("error", str(resp.status)),
                    )
                    
        except Exception as e:
            log.error("order_submission_failed", error=str(e))
            return OrderResult(success=False, error=str(e))

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order"""
        session = await self._get_session()
        async with session.delete(f"{self.BASE_URL}/order/{order_id}") as resp:
            return resp.status == 200

    async def cancel_all_orders(self) -> bool:
        """Cancel all open orders"""
        if self._signer:
            self._signer.cancel_all()
        session = await self._get_session()
        async with session.delete(f"{self.BASE_URL}/orders") as resp:
            return resp.status == 200

    async def get_open_orders(self) -> List[Dict]:
        """Get all open orders"""
        session = await self._get_session()
        async with session.get(f"{self.BASE_URL}/orders") as resp:
            if resp.status != 200:
                return []
            return await resp.json()

    async def get_positions(self) -> List[Dict]:
        """Get current positions"""
        session = await self._get_session()
        async with session.get(f"{self.BASE_URL}/positions") as resp:
            if resp.status != 200:
                return []
            return await resp.json()
