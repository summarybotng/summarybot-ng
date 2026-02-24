#!/usr/bin/env python3
"""
Start the webhook server in test mode with auth bypass enabled.

Usage:
    TEST_AUTH_SECRET=secret TEST_GUILD_ID=123 python scripts/start_test_server.py
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


async def main():
    from src.config import ConfigManager
    from src.summarization import SummarizationEngine, ClaudeClient
    from src.webhook_service import WebhookServer

    print("Loading configuration...")
    config_manager = ConfigManager()
    config = await config_manager.load_config()

    print("Initializing summarization engine...")
    claude_client = None
    api_key = os.getenv('OPENROUTER_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
    if api_key:
        claude_client = ClaudeClient(api_key=api_key)
    engine = SummarizationEngine(claude_client=claude_client)

    print("Creating webhook server...")
    server = WebhookServer(config=config, summarization_engine=engine)

    # Force-load dashboard routes for testing (normally requires discord_bot)
    print("Loading dashboard routes for testing...")
    try:
        from src.dashboard import create_dashboard_router
        dashboard_router = create_dashboard_router(
            discord_bot=None,  # Will limit some functionality but allows API testing
            summarization_engine=engine,
            task_scheduler=None,
            config_manager=config_manager,
        )
        server.app.include_router(dashboard_router)
        print("Dashboard routes loaded successfully")
    except Exception as e:
        print(f"Warning: Could not load dashboard routes: {e}")

    host = os.getenv('WEBHOOK_HOST', '0.0.0.0')
    port = int(os.getenv('WEBHOOK_PORT', '5000'))

    print(f"Starting server on {host}:{port}...")
    print(f"TEST_AUTH_SECRET: {'SET' if os.getenv('TEST_AUTH_SECRET') else 'NOT SET'}")
    print(f"TEST_GUILD_ID: {os.getenv('TEST_GUILD_ID', 'NOT SET')}")

    await server.start_server()

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        await server.stop_server()


if __name__ == "__main__":
    asyncio.run(main())
