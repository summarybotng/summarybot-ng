#!/usr/bin/env python3
"""
Migrate a single wiki page to RuVector and show comparison.

Usage:
    python scripts/ruvector_migrate_page.py <guild_id> <page_path>

Example:
    python scripts/ruvector_migrate_page.py 1283874310720716890 topics/agentic-flow.md
"""

import asyncio
import sys
import os
import json
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


async def migrate_single_page(guild_id: str, page_path: str):
    """Migrate a single wiki page to RuVector and show comparison."""

    from src.data.sqlite.connection import SQLiteConnection
    from src.wiki.ruvector import (
        VectorStore,
        KnowledgeExtractor,
        EmbeddingService,
        EdgeInferenceEngine,
        WikiViewRenderer,
    )

    print(f"\n{'='*60}")
    print(f"RuVector Migration: {page_path}")
    print(f"Guild: {guild_id}")
    print(f"{'='*60}\n")

    # Get database connection
    connection = SQLiteConnection.get_instance()

    # 1. Fetch existing wiki page
    print("1. Fetching existing wiki page...")
    page_query = """
    SELECT id, guild_id, path, title, content, synthesis, source_refs,
           created_at, updated_at, synthesis_updated_at
    FROM wiki_pages
    WHERE guild_id = ? AND path = ?
    """

    page_row = await connection.fetch_one(page_query, (guild_id, page_path))

    if not page_row:
        print(f"   ❌ Page not found: {page_path}")

        # List available pages
        list_query = """
        SELECT path, title FROM wiki_pages
        WHERE guild_id = ?
        ORDER BY path
        LIMIT 20
        """
        pages = await connection.fetch_all(list_query, (guild_id,))

        if pages:
            print(f"\n   Available pages for guild {guild_id}:")
            for p in pages:
                print(f"   - {p['path']}: {p['title']}")
        else:
            print(f"\n   No wiki pages found for guild {guild_id}")
        return

    print(f"   ✓ Found: {page_row['title']}")
    print(f"   - Sources: {len(json.loads(page_row['source_refs'] or '[]'))} references")
    print(f"   - Has synthesis: {'Yes' if page_row['synthesis'] else 'No'}")
    print(f"   - Content length: {len(page_row['content'] or '')} chars")

    # Show existing content preview
    print(f"\n   --- Existing Content (first 500 chars) ---")
    content = page_row['content'] or ''
    print(f"   {content[:500]}{'...' if len(content) > 500 else ''}")

    if page_row['synthesis']:
        print(f"\n   --- Existing Synthesis (first 500 chars) ---")
        synthesis = page_row['synthesis']
        print(f"   {synthesis[:500]}{'...' if len(synthesis) > 500 else ''}")

    # 2. Get source documents for this page
    print(f"\n2. Fetching source documents...")
    source_refs = json.loads(page_row['source_refs'] or '[]')

    sources = []
    if source_refs:
        placeholders = ','.join(['?' for _ in source_refs])
        source_query = f"""
        SELECT id, title, content, source_type, metadata, ingested_at
        FROM wiki_sources
        WHERE guild_id = ? AND id IN ({placeholders})
        """
        sources = await connection.fetch_all(source_query, (guild_id, *source_refs))

    print(f"   ✓ Found {len(sources)} source documents")
    for s in sources[:5]:
        print(f"   - {s['id']}: {s['title'][:50]}...")

    # 3. Initialize RuVector components
    print(f"\n3. Initializing RuVector...")
    embedding_service = EmbeddingService()
    vector_store = VectorStore(connection=connection, embedding_service=embedding_service)
    extractor = KnowledgeExtractor(embedding_service=embedding_service)

    print(f"   ✓ RuVector components ready")

    # 4. Extract knowledge units from sources
    print(f"\n4. Extracting knowledge units from sources...")
    all_units = []

    for source in sources:
        try:
            metadata = json.loads(source['metadata'] or '{}')
            channel_name = metadata.get('channel_name', 'unknown')

            # Parse timestamp
            source_date = None
            if metadata.get('timestamp'):
                try:
                    source_date = datetime.fromisoformat(
                        metadata['timestamp'].replace('Z', '+00:00')
                    )
                except:
                    pass

            extraction = await extractor.extract_from_summary(
                guild_id=guild_id,
                summary_id=source['id'],
                summary_text=source['content'] or '',
                channel_name=channel_name,
                summary_date=source_date,
                key_points=metadata.get('key_points', []),
                action_items=metadata.get('action_items', []),
            )

            all_units.extend(extraction.units)
            print(f"   - {source['id']}: {len(extraction.units)} units extracted")

        except Exception as e:
            print(f"   - {source['id']}: Error - {e}")

    print(f"   ✓ Total: {len(all_units)} knowledge units")

    # 5. Show extracted units
    print(f"\n5. Knowledge Units Preview:")
    for i, unit in enumerate(all_units[:10]):
        print(f"\n   [{i+1}] {unit.unit_type.value.upper()}")
        print(f"       {unit.content[:100]}{'...' if len(unit.content) > 100 else ''}")
        if unit.source_channel:
            print(f"       Channel: {unit.source_channel}")

    if len(all_units) > 10:
        print(f"\n   ... and {len(all_units) - 10} more units")

    # 6. Store units in RuVector (if not already stored)
    print(f"\n6. Storing units in RuVector...")

    # Check existing units
    existing_query = """
    SELECT COUNT(*) as count FROM wiki_knowledge_units
    WHERE guild_id = ? AND source_id IN ({})
    """.format(','.join(['?' for _ in source_refs]))

    existing_row = await connection.fetch_one(
        existing_query, (guild_id, *source_refs)
    )
    existing_count = existing_row['count'] if existing_row else 0

    if existing_count > 0:
        print(f"   ⚠ {existing_count} units already exist (skipping storage)")
    else:
        await vector_store.store_units_batch(all_units)
        print(f"   ✓ Stored {len(all_units)} units")

    # 7. Generate RuVector view
    print(f"\n7. Generating RuVector view...")

    # Extract topic from path (e.g., topics/agentic-flow.md -> agentic-flow)
    topic = page_path.replace('topics/', '').replace('.md', '').replace('-', ' ')

    renderer = WikiViewRenderer(vector_store=vector_store)
    view = await renderer.render_topic_page(
        guild_id=guild_id,
        topic=topic,
        max_units=30,
    )

    print(f"   ✓ Generated view: {view.title}")
    print(f"   - Source units: {len(view.source_units)}")
    print(f"   - Content length: {len(view.content)} chars")

    # 8. Show comparison
    print(f"\n{'='*60}")
    print(f"COMPARISON: {page_row['title']}")
    print(f"{'='*60}")

    print(f"\n--- EXISTING WIKI SYNTHESIS ---")
    if page_row['synthesis']:
        print(page_row['synthesis'][:1500])
        if len(page_row['synthesis']) > 1500:
            print(f"\n... [{len(page_row['synthesis']) - 1500} more chars]")
    else:
        print("(No synthesis available)")

    print(f"\n--- RUVECTOR GENERATED VIEW ---")
    print(view.content[:1500])
    if len(view.content) > 1500:
        print(f"\n... [{len(view.content) - 1500} more chars]")

    # Summary statistics
    print(f"\n{'='*60}")
    print("MIGRATION SUMMARY")
    print(f"{'='*60}")
    print(f"Page: {page_path}")
    print(f"Sources processed: {len(sources)}")
    print(f"Knowledge units: {len(all_units)}")
    print(f"  - Claims: {sum(1 for u in all_units if u.unit_type.value == 'claim')}")
    print(f"  - Decisions: {sum(1 for u in all_units if u.unit_type.value == 'decision')}")
    print(f"  - Questions: {sum(1 for u in all_units if u.unit_type.value == 'question')}")
    print(f"  - Action Items: {sum(1 for u in all_units if u.unit_type.value == 'action_item')}")
    print(f"Existing content: {len(page_row['content'] or '')} chars")
    print(f"Existing synthesis: {len(page_row['synthesis'] or '')} chars")
    print(f"RuVector view: {len(view.content)} chars")


async def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("\nTo list available pages for a guild:")
        print("  python scripts/ruvector_migrate_page.py <guild_id> --list")
        sys.exit(1)

    guild_id = sys.argv[1]
    page_path = sys.argv[2]

    if page_path == '--list':
        # List available pages
        from src.data.sqlite.connection import SQLiteConnection
        connection = SQLiteConnection.get_instance()

        query = """
        SELECT path, title, LENGTH(content) as content_len,
               LENGTH(synthesis) as synthesis_len,
               json_array_length(source_refs) as source_count
        FROM wiki_pages
        WHERE guild_id = ?
        ORDER BY path
        """
        pages = await connection.fetch_all(query, (guild_id,))

        print(f"\nWiki pages for guild {guild_id}:")
        print(f"{'Path':<40} {'Title':<30} {'Sources':<8} {'Content':<10} {'Synthesis':<10}")
        print("-" * 100)
        for p in pages:
            print(f"{p['path']:<40} {(p['title'] or '')[:28]:<30} {p['source_count'] or 0:<8} {p['content_len'] or 0:<10} {p['synthesis_len'] or 0:<10}")
        return

    await migrate_single_page(guild_id, page_path)


if __name__ == '__main__':
    asyncio.run(main())
