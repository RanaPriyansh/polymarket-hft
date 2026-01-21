#!/usr/bin/env python3
"""
Discord Webhook Test Script

Tests the Discord notification system by sending a test message.

Usage:
    python test_discord.py

Requires DISCORD_WEBHOOK_URL to be set in .env file.
Get webhook URL from: Discord Server Settings > Integrations > Webhooks
"""

import asyncio
import os
import sys
from pathlib import Path

# Load .env file
from dotenv import load_dotenv
load_dotenv()


async def test_discord():
    """Send a test message to Discord."""
    from utils.notifier import DiscordNotifier
    
    print("\n" + "=" * 50)
    print("🧪 DISCORD WEBHOOK TEST")
    print("=" * 50 + "\n")
    
    # Check configuration
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    
    if not webhook_url:
        print("❌ DISCORD_WEBHOOK_URL not set in .env")
        print("\nTo fix:")
        print("  1. Go to Discord > Server Settings > Integrations > Webhooks")
        print("  2. Create a webhook and copy the URL")
        print("  3. Add to .env: DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...")
        print("")
        return False
    
    print(f"📡 Webhook URL: {webhook_url[:50]}...")
    
    # Create notifier and check status
    notifier = DiscordNotifier()
    status = notifier.get_status()
    
    print(f"\n📊 Notifier Status:")
    print(f"   Enabled:    {status['enabled']}")
    print(f"   Configured: {status['configured']}")
    print(f"   Instance:   {status['instance_id']}")
    
    if not status['configured']:
        print("\n⚠️  Webhook URL doesn't appear to be a valid Discord webhook")
        print("   Expected format: https://discord.com/api/webhooks/...")
    
    # Send test message
    print("\n📤 Sending test message...")
    
    try:
        success = await notifier.send_message("✅ **System Connected** - Discord notifications working!")
        
        if success:
            print("✅ Test message sent successfully!")
            print("\n   Check your Discord channel for the message.")
        else:
            print("❌ Failed to send test message")
            if not notifier.enabled:
                print("   Notifier is disabled (no webhook URL)")
            return False
        
        # Also test a rich embed
        print("\n📤 Sending rich embed test...")
        await notifier.on_startup(mode="test")
        print("✅ Rich embed sent!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("✅ DISCORD TEST COMPLETE")
    print("=" * 50 + "\n")
    
    return True


if __name__ == "__main__":
    # Add project root to path
    project_root = Path(__file__).parent
    sys.path.insert(0, str(project_root))
    
    # Run test
    success = asyncio.run(test_discord())
    sys.exit(0 if success else 1)
