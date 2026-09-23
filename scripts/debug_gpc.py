#!/usr/bin/env python3
"""Debug GPC tagging for a specific product.

Usage: python debug_gpc.py "Herb cream cheese"
"""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vision_bill.service.embedding_service import EmbeddingService
from vision_bill.provider.db.receipt_db import ReceiptDB
from vision_bill.config import Settings


async def debug_gpc_tagging(query_text: str):
    print(f"=== Debugging GPC tagging for: '{query_text}' ===\n")

    # Step 1: Load settings
    print("Step 1: Loading settings...")
    try:
        settings = Settings()
        print(f"  LLM host: {settings.llm.host}")
        print(f"  PG DSN: {settings.pg.pg_dsn[:50]}...")
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    # Step 2: Check embedding service
    print("\nStep 2: Checking embedding service...")
    embedding_service = EmbeddingService(settings.llm.host)
    print(f"  Mock mode: {embedding_service.mock}")
    print(f"  Model: {embedding_service.model}")

    # Step 3: Generate embedding
    print(f"\nStep 3: Generating embedding for '{query_text}'...")
    try:
        embedding = await embedding_service.embed_text(query_text)
        print(f"  Embedding dimensions: {len(embedding)}")
        print(f"  First 5 values: {[round(x, 4) for x in embedding[:5]]}")
        print(f"  Last 5 values: {[round(x, 4) for x in embedding[-5:]]}")
    except Exception as e:
        print(f"  ERROR generating embedding: {e}")
        return

    # Step 4: Connect to DB and check GPC data
    print("\nStep 4: Checking GPC data in database...")
    db = ReceiptDB(settings.pg)
    await db.init_db()
    try:
        # Check if GPC table has data
        async with db.pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM gpc_categories")
            print(f"  Total GPC categories: {count}")

            # Check metadata
            meta = await conn.fetchrow("SELECT * FROM gpc_import_metadata WHERE id = 1")
            if meta:
                print(f"  Source date: {meta['source_date']}")
                print(f"  Embedding model: {meta['embedding_model']}")
    except Exception as e:
        print(f"  ERROR checking GPC data: {e}")
        await db.destroy_db()
        return

    # Step 5: Find suggestions with low threshold
    print("\nStep 5: Searching for GPC suggestions (threshold=0.30, limit=10)...")
    try:
        suggestions = await db.find_gpc_suggestions(embedding, threshold=0.30, limit=10)
        print(f"  Found {len(suggestions)} suggestions:")
        for i, s in enumerate(suggestions):
            print(f"    {i + 1}. {s['title']} (similarity: {s['similarity']:.4f})")
            print(f"       Code: {s['gpc_code']}")
            print(f"       Definition: {s['definition'][:100]}...")
    except Exception as e:
        print(f"  ERROR searching: {e}")
        await db.destroy_db()
        return

    # Step 6: Try with even lower threshold
    print("\nStep 6: Searching with very low threshold (0.10)...")
    suggestions_low = []
    try:
        suggestions_low = await db.find_gpc_suggestions(embedding, threshold=0.10, limit=5)
        print(f"  Found {len(suggestions_low)} suggestions:")
        for i, s in enumerate(suggestions_low):
            print(f"    {i + 1}. {s['title']} (similarity: {s['similarity']:.4f})")
    except Exception as e:
        print(f"  ERROR: {e}")

    await db.destroy_db()

    # Summary
    print("\n=== Summary ===")
    if not suggestions and not suggestions_low:
        print("No suggestions found even at low threshold. Possible issues:")
        print("  1. GPC categories not imported (check Step 4 count)")
        print("  2. Embedding model mismatch (check Step 4 vs Step 2)")
        print("  3. Embedding dimensions mismatch")
    elif suggestions:
        print(f"Found {len(suggestions)} suggestions above 0.30 threshold.")
        print("If your app shows no results, check the SIMILARITY_THRESHOLD setting.")
    else:
        print("Found suggestions only at very low threshold (< 0.10).")
        print("The embedding quality or model may be an issue.")


if __name__ == "__main__":
    query = "Herb cream cheese"
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])

    asyncio.run(debug_gpc_tagging(query))
