"""
Orderbook Client
Manages WebSocket connection and local orderbook state
"""
import asyncio
import json
from typing import Optional, Dict, Callable, List
from decimal import Decimal
import websockets
import aiohttp
import structlog

log = structlog.get_logger()


class OrderbookClient:
    """
    WebSocket-based orderbook client
    Connects to Polymarket CLOB WebSocket and maintains local state
    Uses Rust backend if available, falls back to Python
    """
    
    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws"
    REST_URL = "https://clob.polymarket.com/book"
    
    def __init__(self):
        self._rust_reconstructor = None
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._orderbooks: Dict[str, Dict] = {}
        self._callbacks: List[Callable] = []
        self._running = False
        
        # Try to load Rust module
        try:
            from polymarket_muscle import PySnapshotReconstructor
            self._rust_reconstructor = PySnapshotReconstructor()
            log.info("rust_reconstructor_loaded")
        except ImportError:
            log.warning("rust_reconstructor_not_available", fallback="python")

    def on_update(self, callback: Callable):
        """Register callback for orderbook updates"""
        self._callbacks.append(callback)

    async def fetch_snapshot(self, token_id: str) -> Dict:
        """Fetch initial orderbook snapshot"""
        if self._rust_reconstructor:
            self._rust_reconstructor.fetch_snapshot(token_id)
            return {}
            
        async with aiohttp.ClientSession() as session:
            url = f"{self.REST_URL}?token_id={token_id}"
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to fetch snapshot: {resp.status}")
                data = await resp.json()
                self._orderbooks[token_id] = data
                return data

    async def connect(self, token_ids: List[str]):
        """Connect to WebSocket and subscribe to tokens"""
        if self._rust_reconstructor:
            self._rust_reconstructor.connect(token_ids)
            return
            
        self._ws = await websockets.connect(self.WS_URL)
        log.info("websocket_connected")
        
        # Fetch snapshots first
        for token_id in token_ids:
            try:
                await self.fetch_snapshot(token_id)
            except Exception as e:
                log.warning("snapshot_failed", token_id=token_id, error=str(e))
        
        # Subscribe
        subscribe_msg = {
            "type": "subscribe",
            "channel": "book",
            "assets_ids": token_ids,
        }
        await self._ws.send(json.dumps(subscribe_msg))
        log.info("subscribed", tokens=len(token_ids))

    async def start(self):
        """Start processing messages"""
        if not self._ws:
            raise Exception("Not connected")
            
        self._running = True
        
        try:
            async for message in self._ws:
                if not self._running:
                    break
                    
                try:
                    data = json.loads(message)
                    await self._process_message(data)
                except json.JSONDecodeError:
                    continue
                    
        except websockets.ConnectionClosed:
            log.warning("websocket_disconnected")
        finally:
            self._running = False

    async def _process_message(self, data: Dict):
        """Process a WebSocket message"""
        msg_type = data.get("type")
        
        if msg_type == "book":
            token_id = data.get("asset_id")
            if not token_id:
                return
                
            # Update local orderbook
            if token_id not in self._orderbooks:
                self._orderbooks[token_id] = {"bids": [], "asks": []}
                
            book = self._orderbooks[token_id]
            
            # Apply delta updates
            for bid in data.get("bids", []):
                self._apply_update(book["bids"], bid, is_bid=True)
            for ask in data.get("asks", []):
                self._apply_update(book["asks"], ask, is_bid=False)
                
            # Notify callbacks
            for cb in self._callbacks:
                try:
                    cb(token_id, book)
                except Exception as e:
                    log.error("callback_error", error=str(e))

    def _apply_update(self, levels: List[Dict], update: Dict, is_bid: bool):
        """Apply a price level update"""
        price = Decimal(update.get("price", "0"))
        size = Decimal(update.get("size", "0"))
        
        # Find existing level
        for i, level in enumerate(levels):
            if Decimal(level["price"]) == price:
                if size.is_zero():
                    levels.pop(i)
                else:
                    level["size"] = str(size)
                return
                
        # Add new level if size > 0
        if not size.is_zero():
            levels.append({"price": str(price), "size": str(size)})
            # Re-sort
            levels.sort(key=lambda x: Decimal(x["price"]), reverse=is_bid)

    def get_best_bid(self, token_id: str) -> Optional[Decimal]:
        """Get best bid price"""
        if self._rust_reconstructor:
            result = self._rust_reconstructor.best_bid(token_id)
            return Decimal(result) if result else None
            
        book = self._orderbooks.get(token_id, {})
        bids = book.get("bids", [])
        if bids:
            return Decimal(bids[0]["price"])
        return None

    def get_best_ask(self, token_id: str) -> Optional[Decimal]:
        """Get best ask price"""
        if self._rust_reconstructor:
            result = self._rust_reconstructor.best_ask(token_id)
            return Decimal(result) if result else None
            
        book = self._orderbooks.get(token_id, {})
        asks = book.get("asks", [])
        if asks:
            return Decimal(asks[0]["price"])
        return None

    def get_spread_bps(self, token_id: str) -> Optional[int]:
        """Get spread in basis points"""
        bid = self.get_best_bid(token_id)
        ask = self.get_best_ask(token_id)
        
        if bid and ask and not bid.is_zero():
            return int((ask - bid) / bid * 10000)
        return None

    async def stop(self):
        """Stop the client"""
        self._running = False
        if self._ws:
            await self._ws.close()

    def enable_emergency_mode(self):
        """Enable emergency mode (pause processing)"""
        if self._rust_reconstructor:
            self._rust_reconstructor.enable_emergency_mode()
        self._running = False
        log.warning("emergency_mode_enabled")

    def disable_emergency_mode(self):
        """Disable emergency mode"""
        if self._rust_reconstructor:
            self._rust_reconstructor.disable_emergency_mode()
        log.info("emergency_mode_disabled")
