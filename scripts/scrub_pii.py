#!/usr/bin/env python3
"""
One-time PII scrubbing script for WhatsApp messages.
Run this on the production database to anonymize phone numbers in existing content.
"""

import re
import hmac
import hashlib
import sqlite3
import os

ADJECTIVES = [
    "Swift", "Brave", "Calm", "Bright", "Bold", "Clever", "Eager", "Fair",
    "Gentle", "Happy", "Jolly", "Keen", "Lively", "Merry", "Noble", "Proud",
    "Quick", "Ready", "Sharp", "True", "Warm", "Wise", "Witty", "Zesty",
    "Misty", "Sunny", "Breezy", "Frosty", "Dusty", "Sandy", "Rocky", "Mossy",
    "Azure", "Coral", "Crimson", "Golden", "Jade", "Ruby", "Silver", "Violet",
    "Amber", "Copper", "Ivory", "Onyx", "Pearl", "Rusty", "Teal", "Bronze",
    "Ancient", "Cosmic", "Crystal", "Dancing", "Electric", "Floating", "Glowing", "Hidden",
    "Lunar", "Mystic", "Nordic", "Pacific", "Quiet", "Radiant", "Silent", "Wandering",
]

ANIMALS = [
    "Fox", "Bear", "Wolf", "Deer", "Otter", "Badger", "Lynx", "Panda",
    "Tiger", "Koala", "Seal", "Jaguar", "Beaver", "Hare", "Moose", "Whale",
    "Penguin", "Owl", "Hawk", "Raven", "Falcon", "Heron", "Eagle", "Crane",
    "Osprey", "Condor", "Finch", "Ibis", "Jay", "Parrot", "Swan", "Wren",
    "Gecko", "Turtle", "Cobra", "Dragon", "Newt", "Viper", "Frog", "Toad",
    "Dolphin", "Shark", "Squid", "Marlin", "Urchin", "Mantis", "Crab", "Eel",
    "Moth", "Beetle", "Cricket", "Firefly", "Hornet", "Spider", "Sphinx", "Phoenix",
    "Griffin", "Wyrm", "Roc", "Hydra", "Kraken", "Sprite", "Nymph", "Djinn",
]

# Phone pattern: +{country}{groups of digits with optional separators}
PHONE_PATTERN = re.compile(r'\+\d{1,3}(?:[\s.\-]?\d{1,4}){2,5}')

def get_salt():
    return os.environ.get("ANONYMIZATION_SALT", "summarybot-default-salt")

def hash_phone(phone: str, salt: str) -> str:
    normalized = "".join(c for c in phone if c.isdigit())
    h = hmac.new(salt.encode(), normalized.encode(), hashlib.sha256)
    return h.hexdigest()[:8]

def to_pseudonym(phone_hash: str) -> str:
    adj = ADJECTIVES[int(phone_hash[0:2], 16) % 64]
    animal = ANIMALS[int(phone_hash[2:4], 16) % 64]
    num = int(phone_hash[4:8], 16) % 10000
    return f"{adj} {animal} {num:04d}"

def scrub_content(text: str, salt: str) -> tuple:
    """Scrub phone numbers from text, return (scrubbed_text, count)."""
    count = 0

    def replace(m):
        nonlocal count
        count += 1
        return to_pseudonym(hash_phone(m.group(0), salt))

    return PHONE_PATTERN.sub(replace, text), count

def main():
    db_path = os.environ.get("DB_PATH", "/app/data/summarybot.db")
    salt = get_salt()

    print(f"Database: {db_path}")
    print(f"Salt configured: {'Yes' if salt != 'summarybot-default-salt' else 'Using default'}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Count total WhatsApp messages
    total = conn.execute(
        "SELECT COUNT(*) as c FROM ingest_messages WHERE source_type = ?",
        ("whatsapp",)
    ).fetchone()["c"]
    print(f"\nTotal WhatsApp messages: {total}")

    # Find messages that might contain phone numbers (have + character)
    candidates = conn.execute(
        "SELECT id, content FROM ingest_messages WHERE source_type = ? AND content LIKE ?",
        ("whatsapp", "%+%")
    ).fetchall()
    print(f"Messages with '+' character: {len(candidates)}")

    # Process and scrub
    updated = 0
    phones_scrubbed = 0

    for row in candidates:
        content = row["content"] or ""
        if not content:
            continue

        new_content, count = scrub_content(content, salt)
        if count > 0:
            conn.execute(
                "UPDATE ingest_messages SET content = ? WHERE id = ?",
                (new_content, row["id"])
            )
            updated += 1
            phones_scrubbed += count

    conn.commit()

    # Checkpoint WAL
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    print(f"\n=== Results ===")
    print(f"Messages updated: {updated}")
    print(f"Phone numbers scrubbed: {phones_scrubbed}")

    conn.close()

if __name__ == "__main__":
    main()
