#!/usr/bin/env python3
"""
Discord Notification System for Remote Monitoring

Sends notifications to Discord via webhook for:
- Trade executions
- Errors and warnings
- Bot startup/shutdown
- Daily summaries

Usage:
    from utils.notifier import DiscordNotifier
    notifier = DiscordNotifier()
    await notifier.on_trade("BOUGHT", "Trump Wins", 0.55, 10.0, 0.15)
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """
    Discord webhook notifier for remote monitoring.
    
    Set DISCORD_WEBHOOK_URL in your .env file.
    Get webhook URL from Discord: Server Settings > Integrations > Webhooks
    """
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        self.enabled = bool(self.webhook_url)
        self.bot_name = "Polymarket HFT"
        self.instance_id = os.getenv("INSTANCE_ID", "local")
        
        if self.enabled:
            logger.info("📣 Discord notifications enabled")
        else:
            logger.warning("📣 Discord notifications disabled (no webhook URL)")
    
    async def _send(self, content: str, embeds: Optional[list] = None):
        """Send message to Discord webhook."""
        if not self.enabled:
            return False
        
        payload = {"content": content}
        if embeds:
            payload["embeds"] = embeds
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                if resp.status_code not in (200, 204):
                    logger.warning(f"Discord webhook failed: {resp.status_code}")
                    return False
                return True
        except Exception as e:
            logger.error(f"Discord notification failed: {e}")
            return False
    
    async def send_message(self, msg: str) -> bool:
        """
        Send a simple text message to Discord.
        
        Args:
            msg: The message text to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug(f"Discord disabled, would send: {msg}")
            return False
        
        return await self._send(msg)
    
    def is_configured(self) -> bool:
        """Check if Discord webhook is configured and valid."""
        if not self.webhook_url:
            return False
        # Basic URL validation
        return self.webhook_url.startswith("https://discord.com/api/webhooks/")
    
    def get_status(self) -> dict:
        """Get notifier status for diagnostics."""
        return {
            "enabled": self.enabled,
            "configured": self.is_configured(),
            "webhook_url_set": bool(self.webhook_url),
            "instance_id": self.instance_id,
        }
    
    async def on_startup(self, mode: str = "live"):
        """Send notification when bot starts."""
        timestamp = datetime.utcnow().isoformat()
        
        embed = {
            "title": "🚀 Bot Deployed and Active",
            "description": f"**{self.bot_name}** is now running",
            "color": 0x00FF00,  # Green
            "fields": [
                {"name": "Mode", "value": mode.upper(), "inline": True},
                {"name": "Instance", "value": self.instance_id, "inline": True},
                {"name": "Started", "value": timestamp, "inline": False},
            ],
            "footer": {"text": "Polymarket HFT Bot Fleet"}
        }
        
        await self._send("", embeds=[embed])
        logger.info(f"📣 Sent startup notification (mode: {mode})")
    
    async def on_shutdown(self, reason: str = "Manual stop"):
        """Send notification when bot shuts down."""
        embed = {
            "title": "🛑 Bot Shutdown",
            "description": f"**{self.bot_name}** has stopped",
            "color": 0xFF0000,  # Red
            "fields": [
                {"name": "Reason", "value": reason, "inline": False},
                {"name": "Instance", "value": self.instance_id, "inline": True},
            ],
            "footer": {"text": "Polymarket HFT Bot Fleet"}
        }
        
        await self._send("", embeds=[embed])
        logger.info(f"📣 Sent shutdown notification (reason: {reason})")
    
    async def on_trade(
        self,
        side: str,
        market: str,
        price: float,
        size: float,
        profit: float,
        bot_name: str = "Unknown",
    ):
        """Send notification when trade executes."""
        emoji = "📈" if side.upper() == "BUY" else "📉"
        color = 0x00FF00 if profit >= 0 else 0xFF6600  # Green or Orange
        
        embed = {
            "title": f"{emoji} {side.upper()} - {market[:40]}",
            "color": color,
            "fields": [
                {"name": "Price", "value": f"${price:.4f}", "inline": True},
                {"name": "Size", "value": f"${size:.2f}", "inline": True},
                {"name": "Expected Profit", "value": f"${profit:.4f}", "inline": True},
                {"name": "Bot", "value": bot_name, "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        await self._send("", embeds=[embed])
    
    async def on_error(self, error: str, traceback: Optional[str] = None):
        """Send notification on error."""
        embed = {
            "title": "⚠️ ERROR",
            "description": f"```\n{error[:1000]}\n```",
            "color": 0xFF0000,  # Red
            "fields": [
                {"name": "Instance", "value": self.instance_id, "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        if traceback:
            embed["fields"].append({
                "name": "Traceback",
                "value": f"```\n{traceback[:500]}\n```",
                "inline": False
            })
        
        await self._send("@here", embeds=[embed])  # @here pings channel
        logger.error(f"📣 Sent error notification: {error[:100]}")
    
    async def on_kill_switch(self):
        """Send notification when kill switch is triggered."""
        embed = {
            "title": "🚨 KILL SWITCH ACTIVATED",
            "description": "Bot has been emergency stopped!",
            "color": 0xFF0000,
            "fields": [
                {"name": "Instance", "value": self.instance_id, "inline": True},
                {"name": "Action", "value": "All orders cancelled", "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        await self._send("@everyone", embeds=[embed])  # @everyone for emergency
    
    async def on_daily_summary(
        self,
        total_trades: int,
        pnl: float,
        wins: int,
        losses: int,
    ):
        """Send daily performance summary."""
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        color = 0x00FF00 if pnl >= 0 else 0xFF0000
        pnl_emoji = "💰" if pnl >= 0 else "💸"
        
        embed = {
            "title": "📊 Daily Summary",
            "color": color,
            "fields": [
                {"name": "Total Trades", "value": str(total_trades), "inline": True},
                {"name": f"{pnl_emoji} P&L", "value": f"${pnl:.2f}", "inline": True},
                {"name": "Win Rate", "value": f"{win_rate:.1f}%", "inline": True},
                {"name": "Wins", "value": str(wins), "inline": True},
                {"name": "Losses", "value": str(losses), "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        await self._send("", embeds=[embed])
    
    async def on_pnl_alert(self, current_pnl: float, limit: float):
        """Send alert when P&L approaches limit."""
        remaining = limit - abs(current_pnl)
        
        embed = {
            "title": "⚠️ P&L Alert",
            "description": f"Approaching daily loss limit",
            "color": 0xFFFF00,  # Yellow
            "fields": [
                {"name": "Current P&L", "value": f"${current_pnl:.2f}", "inline": True},
                {"name": "Limit", "value": f"${limit:.2f}", "inline": True},
                {"name": "Remaining", "value": f"${remaining:.2f}", "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        await self._send("@here", embeds=[embed])


# Global instance (lazy initialization)
_notifier: Optional[DiscordNotifier] = None


def get_notifier() -> DiscordNotifier:
    """Get or create the global notifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = DiscordNotifier()
    return _notifier


async def notify_trade(side: str, market: str, price: float, size: float, profit: float, bot: str = ""):
    """Convenience function for trade notifications."""
    await get_notifier().on_trade(side, market, price, size, profit, bot)


async def notify_error(error: str, traceback: Optional[str] = None):
    """Convenience function for error notifications."""
    await get_notifier().on_error(error, traceback)
