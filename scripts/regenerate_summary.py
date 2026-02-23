#!/usr/bin/env python3
"""
Script to regenerate a stored summary with grounding.
Run with: python scripts/regenerate_summary.py <summary_id>
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def regenerate_summary(summary_id: str):
    """Regenerate a stored summary with grounding."""
    from src.data.sqlite import SQLiteConnection, SQLiteStoredSummaryRepository
    from src.summarization.engine import SummarizationEngine
    from src.summarization.claude_client import ClaudeClient
    from src.models.summary import SummaryOptions, SummaryLength, SummarizationContext
    from src.models.message import ProcessedMessage, MessageType
    from datetime import datetime
    import json

    # Initialize database
    db_path = os.environ.get("DATABASE_PATH", "summarybot.db")
    print(f"Using database: {db_path}")

    connection = SQLiteConnection(db_path)
    await connection.initialize()

    stored_repo = SQLiteStoredSummaryRepository(connection)

    # Get the summary
    print(f"Looking up summary: {summary_id}")
    stored = await stored_repo.get(summary_id)

    if not stored:
        print(f"ERROR: Summary {summary_id} not found")
        return False

    print(f"Found summary: {stored.title}")
    print(f"  Guild: {stored.guild_id}")
    print(f"  Channels: {stored.source_channel_ids}")
    print(f"  Source: {stored.source.value}")

    summary_result = stored.summary_result
    if not summary_result:
        print("ERROR: No summary_result in stored summary")
        return False

    print(f"  Time range: {summary_result.start_time} to {summary_result.end_time}")
    print(f"  Message count: {summary_result.message_count}")
    print(f"  Has references: {bool(summary_result.reference_index)}")
    print(f"  Reference count: {len(summary_result.reference_index) if summary_result.reference_index else 0}")

    if summary_result.reference_index:
        print("  Summary already has grounding!")
        return True

    # Check if we have source_content to regenerate from
    if not summary_result.source_content:
        print("ERROR: No source_content available for regeneration")
        print("  This summary would need to be regenerated via the API with Discord access")
        return False

    print("\nParsing source content for regeneration...")

    # Parse source_content back into messages
    lines = summary_result.source_content.strip().split('\n')
    messages = []
    i = 0

    for line in lines:
        if line.startswith('[') and '] ' in line:
            # Parse: [2025-02-22 14:32] username: content
            try:
                bracket_end = line.index('] ')
                timestamp_str = line[1:bracket_end]
                rest = line[bracket_end + 2:]

                if ': ' in rest:
                    author, content = rest.split(': ', 1)
                else:
                    author = "Unknown"
                    content = rest

                # Parse timestamp
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M')
                except:
                    timestamp = datetime.utcnow()

                messages.append(ProcessedMessage(
                    id=f"msg_{i}",
                    author_name=author,
                    author_id=f"user_{i}",
                    content=content,
                    timestamp=timestamp,
                    message_type=MessageType.DEFAULT,
                    channel_id=stored.source_channel_ids[0] if stored.source_channel_ids else None,
                ))
                i += 1
            except Exception as e:
                print(f"  Warning: Could not parse line: {line[:50]}... ({e})")

    print(f"Parsed {len(messages)} messages from source_content")

    if len(messages) < 1:
        print("ERROR: No messages could be parsed")
        return False

    # Initialize summarization engine
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        return False

    print("\nInitializing summarization engine...")
    claude_client = ClaudeClient(api_key=api_key)
    engine = SummarizationEngine(claude_client=claude_client)

    # Get original options
    meta = summary_result.metadata or {}
    summary_length = meta.get("summary_length", "detailed")
    perspective = meta.get("perspective", "general")

    options = SummaryOptions(
        summary_length=SummaryLength(summary_length),
        perspective=perspective,
        min_messages=1,
    )

    # Build context
    time_span = (summary_result.end_time - summary_result.start_time).total_seconds() / 3600
    unique_authors = set(m.author_id for m in messages)

    context = SummarizationContext(
        channel_name="regenerated",
        guild_name="",
        total_participants=len(unique_authors),
        time_span_hours=time_span,
    )

    print(f"\nRegenerating summary with grounding enabled...")
    print(f"  Options: {summary_length}, {perspective}")

    try:
        new_result = await engine.summarize_messages(
            messages=messages,
            options=options,
            context=context,
            guild_id=stored.guild_id,
            channel_id=stored.source_channel_ids[0] if stored.source_channel_ids else "",
        )

        print(f"\nRegeneration complete!")
        print(f"  New summary ID: {new_result.id}")
        print(f"  Has references: {bool(new_result.reference_index)}")
        print(f"  Reference count: {len(new_result.reference_index) if new_result.reference_index else 0}")

        if new_result.reference_index:
            print("\n  Sample references:")
            for ref in new_result.reference_index[:3]:
                print(f"    [{ref.position}] {ref.sender}: {ref.snippet[:50]}...")

        # Update stored summary
        print(f"\nUpdating stored summary...")
        new_result.id = summary_id  # Keep original ID
        stored.summary_result = new_result
        await stored_repo.update(stored)

        print(f"SUCCESS: Summary {summary_id} regenerated with grounding!")
        return True

    except Exception as e:
        print(f"ERROR: Regeneration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/regenerate_summary.py <summary_id>")
        print("Example: python scripts/regenerate_summary.py sum_8d35d83ed123")
        sys.exit(1)

    summary_id = sys.argv[1]
    success = asyncio.run(regenerate_summary(summary_id))
    sys.exit(0 if success else 1)
