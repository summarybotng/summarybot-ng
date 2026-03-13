#!/usr/bin/env python3
"""
One-time migration: encrypt plaintext webhook secrets in guild_configs.

Usage:
    ENCRYPTION_KEY=your-fernet-key python scripts/migrate_encrypt_secrets.py

Idempotent - safe to run multiple times.
"""

import asyncio
import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.encryption import encrypt_value, decrypt_value, get_cipher
from src.data.sqlite.connection import SQLiteConnection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    db_path = os.environ.get("DATABASE_PATH", "data/summarybot.db")

    if not os.path.exists(db_path):
        logger.error(f"Database not found: {db_path}")
        sys.exit(1)

    # Verify encryption key is set
    if not os.environ.get("ENCRYPTION_KEY"):
        logger.warning("ENCRYPTION_KEY not set - will use ephemeral key (NOT recommended for production)")

    conn = SQLiteConnection(db_path, pool_size=1)
    await conn.connect()

    try:
        rows = await conn.fetch_all(
            "SELECT guild_id, webhook_secret FROM guild_configs WHERE webhook_secret IS NOT NULL"
        )

        migrated = 0
        skipped = 0

        for row in rows:
            guild_id = row["guild_id"]
            secret = row["webhook_secret"]

            if not secret:
                continue

            # Check if already encrypted by trying to decrypt
            cipher = get_cipher()
            try:
                cipher.decrypt(secret.encode())
                # If decrypt succeeds, it's already encrypted
                skipped += 1
                logger.debug(f"Guild {guild_id}: already encrypted, skipping")
                continue
            except Exception:
                # Not valid Fernet token - it's plaintext, encrypt it
                pass

            encrypted = encrypt_value(secret)
            await conn.execute(
                "UPDATE guild_configs SET webhook_secret = ? WHERE guild_id = ?",
                (encrypted, guild_id)
            )
            migrated += 1
            logger.info(f"Guild {guild_id}: encrypted webhook_secret")

        logger.info(f"Migration complete: {migrated} encrypted, {skipped} already encrypted")
    finally:
        await conn.disconnect()


if __name__ == "__main__":
    asyncio.run(migrate())
