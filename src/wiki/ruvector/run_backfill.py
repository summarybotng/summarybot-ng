#!/usr/bin/env python3
"""
ADR-090: Run backfill from stored_summaries to RuVector.

Usage:
    python -m src.wiki.ruvector.run_backfill <guild_id> [--use-llm] [--max=N]
"""

import asyncio
import sys
import argparse


async def main(guild_id: str, use_llm: bool = False, max_summaries: int = None):
    import sys
    sys.path.insert(0, "/app")

    from src.wiki.ruvector.backfill import RuVectorBackfill
    from src.wiki.ruvector.vector_store import VectorStore
    from src.wiki.ruvector.knowledge_extractor import KnowledgeExtractor
    from src.wiki.ruvector.embeddings import EmbeddingService
    from src.data.sqlite.connection import SQLiteConnection

    print(f"Connecting to database...")
    conn = SQLiteConnection("/app/data/summarybot.db")
    await conn.connect()

    print(f"Initializing RuVector components...")
    emb = EmbeddingService()
    vs = VectorStore(connection=conn, embedding_service=emb)
    ext = KnowledgeExtractor()
    bf = RuVectorBackfill(wiki_connection=conn, vector_store=vs, knowledge_extractor=ext)

    print(f"Starting backfill for guild {guild_id}...")
    print(f"  use_llm={use_llm}, max_summaries={max_summaries}")

    result = await bf.backfill_from_summaries(
        guild_id=guild_id,
        use_llm=use_llm,
        max_summaries=max_summaries,
    )

    print("\n=== BACKFILL COMPLETE ===")
    print(f"Processed: {result['processed']}")
    print(f"Skipped: {result['skipped']}")
    print(f"Units created: {result['units_created']}")
    print(f"Errors: {len(result['errors'])}")

    if result['errors']:
        print("\nFirst 5 errors:")
        for err in result['errors'][:5]:
            print(f"  - {err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill RuVector from stored_summaries")
    parser.add_argument("guild_id", help="Guild ID to backfill")
    parser.add_argument("--use-llm", action="store_true", help="Use LLM for extraction")
    parser.add_argument("--max", type=int, default=None, help="Max summaries to process")

    args = parser.parse_args()
    asyncio.run(main(args.guild_id, args.use_llm, args.max))
