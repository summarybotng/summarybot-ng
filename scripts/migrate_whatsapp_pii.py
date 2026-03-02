#!/usr/bin/env python3
"""
Migration script for WhatsApp PII anonymization (ADR-028).

This script:
1. Finds all WhatsApp summaries in the database
2. Anonymizes phone numbers in summary text, key points, participants, etc.
3. Updates the summaries with anonymized content
4. Adds anonymization metadata

Usage:
    poetry run python scripts/migrate_whatsapp_pii.py --dry-run  # Preview changes
    poetry run python scripts/migrate_whatsapp_pii.py            # Apply changes
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.anonymization import PhoneAnonymizer
from src.services.anonymization.phone_anonymizer import create_guild_anonymizer, COMBINED_PHONE_PATTERN

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def has_phone_numbers(text: str) -> bool:
    """Check if text contains phone numbers."""
    if not text:
        return False
    return bool(COMBINED_PHONE_PATTERN.search(text))


def count_phone_numbers(text: str) -> int:
    """Count phone numbers in text."""
    if not text:
        return 0
    return len(COMBINED_PHONE_PATTERN.findall(text))


def anonymize_summary_result(
    summary_json: Dict[str, Any],
    anonymizer: PhoneAnonymizer,
) -> tuple[Dict[str, Any], Dict[str, int]]:
    """
    Anonymize phone numbers in a summary result dict.

    Args:
        summary_json: The summary result data
        anonymizer: PhoneAnonymizer instance

    Returns:
        Tuple of (anonymized_data, stats)
    """
    stats = {
        "summary_text": 0,
        "key_points": 0,
        "action_items": 0,
        "participants": 0,
        "technical_terms": 0,
    }

    data = summary_json.copy()

    # Anonymize summary_text
    if data.get("summary_text"):
        result = anonymizer.anonymize_text(data["summary_text"])
        data["summary_text"] = result.anonymized_text
        stats["summary_text"] = result.phone_count

    # Anonymize key_points
    if data.get("key_points"):
        new_key_points = []
        for kp in data["key_points"]:
            if isinstance(kp, str):
                result = anonymizer.anonymize_text(kp)
                new_key_points.append(result.anonymized_text)
                stats["key_points"] += result.phone_count
            elif isinstance(kp, dict):
                kp_copy = kp.copy()
                if kp_copy.get("text"):
                    result = anonymizer.anonymize_text(kp_copy["text"])
                    kp_copy["text"] = result.anonymized_text
                    stats["key_points"] += result.phone_count
                new_key_points.append(kp_copy)
            else:
                new_key_points.append(kp)
        data["key_points"] = new_key_points

    # Anonymize referenced_key_points (ADR-004 format)
    if data.get("referenced_key_points"):
        new_rkp = []
        for rkp in data["referenced_key_points"]:
            if isinstance(rkp, dict):
                rkp_copy = rkp.copy()
                if rkp_copy.get("text"):
                    result = anonymizer.anonymize_text(rkp_copy["text"])
                    rkp_copy["text"] = result.anonymized_text
                    stats["key_points"] += result.phone_count
                new_rkp.append(rkp_copy)
            else:
                new_rkp.append(rkp)
        data["referenced_key_points"] = new_rkp

    # Anonymize action_items
    if data.get("action_items"):
        new_items = []
        for item in data["action_items"]:
            if isinstance(item, dict):
                item_copy = item.copy()
                for field in ["action", "description", "assignee"]:
                    if item_copy.get(field):
                        result = anonymizer.anonymize_text(item_copy[field])
                        item_copy[field] = result.anonymized_text
                        stats["action_items"] += result.phone_count
                new_items.append(item_copy)
            else:
                new_items.append(item)
        data["action_items"] = new_items

    # Anonymize participants
    if data.get("participants"):
        new_participants = []
        for p in data["participants"]:
            if isinstance(p, dict):
                p_copy = p.copy()
                if p_copy.get("name"):
                    display_name, phone_hash = anonymizer.anonymize_sender(p_copy["name"])
                    if phone_hash:  # Was a phone number
                        p_copy["name"] = display_name
                        p_copy["phone_hash"] = phone_hash
                        stats["participants"] += 1
                new_participants.append(p_copy)
            elif isinstance(p, str):
                display_name, phone_hash = anonymizer.anonymize_sender(p)
                if phone_hash:
                    new_participants.append({"name": display_name, "phone_hash": phone_hash})
                    stats["participants"] += 1
                else:
                    new_participants.append(p)
            else:
                new_participants.append(p)
        data["participants"] = new_participants

    # Anonymize technical_terms (unlikely to have phones but check anyway)
    if data.get("technical_terms"):
        new_terms = []
        for term in data["technical_terms"]:
            if isinstance(term, dict):
                term_copy = term.copy()
                if term_copy.get("term") and has_phone_numbers(term_copy["term"]):
                    result = anonymizer.anonymize_text(term_copy["term"])
                    term_copy["term"] = result.anonymized_text
                    stats["technical_terms"] += result.phone_count
                new_terms.append(term_copy)
            else:
                new_terms.append(term)
        data["technical_terms"] = new_terms

    return data, stats


async def migrate_summaries(dry_run: bool = True) -> Dict[str, Any]:
    """
    Migrate WhatsApp summaries to anonymize phone numbers.

    Args:
        dry_run: If True, only preview changes without applying

    Returns:
        Migration statistics
    """
    import aiosqlite

    # Get database path from environment
    database_url = os.environ.get("DATABASE_URL", "sqlite:///data/summarybot.db")
    if database_url.startswith("sqlite:///"):
        db_path = database_url.replace("sqlite:///", "")
    else:
        db_path = "data/summarybot.db"

    logger.info(f"Using database: {db_path}")

    if not os.path.exists(db_path):
        logger.error(f"Database file not found: {db_path}")
        return {"error": f"Database file not found: {db_path}"}

    stats = {
        "total_summaries": 0,
        "whatsapp_summaries": 0,
        "summaries_with_pii": 0,
        "summaries_updated": 0,
        "phone_numbers_found": 0,
        "errors": [],
    }

    # Get all summaries with WhatsApp source using direct SQLite access
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT id, guild_id, summary_json, archive_source_key
                FROM stored_summaries
                WHERE archive_source_key LIKE 'whatsapp:%'
                ORDER BY created_at DESC
            """) as cursor:
                rows = await cursor.fetchall()

            stats["total_summaries"] = len(rows)

            for row in rows:
                summary_id = row["id"]
                guild_id = row["guild_id"]
                summary_json_raw = row["summary_json"]
                summary_json = json.loads(summary_json_raw) if isinstance(summary_json_raw, str) else (summary_json_raw or {})

                stats["whatsapp_summaries"] += 1

                # Create guild-specific anonymizer
                anonymizer = create_guild_anonymizer(guild_id)

                # Check if summary has phone numbers
                summary_text = summary_json.get("summary_text", "")
                has_pii = has_phone_numbers(summary_text)

                # Also check key points and participants
                for kp in summary_json.get("key_points", []):
                    text = kp.get("text", "") if isinstance(kp, dict) else kp
                    if has_phone_numbers(text):
                        has_pii = True
                        break

                for p in summary_json.get("participants", []):
                    name = p.get("name", "") if isinstance(p, dict) else p
                    if has_phone_numbers(name) or (isinstance(name, str) and name.startswith("+")):
                        has_pii = True
                        break

                if has_pii:
                    stats["summaries_with_pii"] += 1

                    # Anonymize the summary
                    anonymized_data, field_stats = anonymize_summary_result(summary_json, anonymizer)

                    total_phones = sum(field_stats.values())
                    stats["phone_numbers_found"] += total_phones

                    logger.info(
                        f"Summary {summary_id}: Found {total_phones} phone numbers "
                        f"(text: {field_stats['summary_text']}, "
                        f"key_points: {field_stats['key_points']}, "
                        f"participants: {field_stats['participants']})"
                    )

                    # Add anonymization metadata
                    metadata = anonymized_data.get("metadata", {})
                    metadata["anonymization"] = {
                        "version": 1,
                        "migrated_at": asyncio.get_event_loop().time(),
                        "fields_processed": field_stats,
                    }
                    anonymized_data["metadata"] = metadata

                    if not dry_run:
                        # Update the summary in database
                        try:
                            await db.execute(
                                "UPDATE stored_summaries SET summary_json = ? WHERE id = ?",
                                (json.dumps(anonymized_data), summary_id)
                            )
                            await db.commit()
                            stats["summaries_updated"] += 1
                            logger.info(f"Updated summary {summary_id}")
                        except Exception as e:
                            error_msg = f"Failed to update {summary_id}: {e}"
                            logger.error(error_msg)
                            stats["errors"].append(error_msg)
                    else:
                        logger.info(f"[DRY RUN] Would update summary {summary_id}")
                        stats["summaries_updated"] += 1

                else:
                    logger.debug(f"Summary {summary_id}: No phone numbers found")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        stats["errors"].append(str(e))

    return stats


async def main():
    parser = argparse.ArgumentParser(
        description="Migrate WhatsApp summaries to anonymize phone numbers (ADR-028)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("WhatsApp PII Anonymization Migration (ADR-028)")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
    else:
        logger.warning("LIVE MODE - Changes will be applied to database")

    logger.info("")

    stats = await migrate_summaries(dry_run=args.dry_run)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Migration Results:")
    logger.info("=" * 60)
    logger.info(f"  WhatsApp summaries found: {stats.get('whatsapp_summaries', 0)}")
    logger.info(f"  Summaries with PII:       {stats.get('summaries_with_pii', 0)}")
    logger.info(f"  Phone numbers found:      {stats.get('phone_numbers_found', 0)}")
    logger.info(f"  Summaries {'would be ' if args.dry_run else ''}updated: {stats.get('summaries_updated', 0)}")

    if stats.get("errors"):
        logger.error(f"  Errors: {len(stats['errors'])}")
        for err in stats["errors"]:
            logger.error(f"    - {err}")

    logger.info("")

    if args.dry_run and stats.get("summaries_with_pii", 0) > 0:
        logger.info("To apply changes, run without --dry-run flag")


if __name__ == "__main__":
    asyncio.run(main())
