#!/usr/bin/env python3
"""Import GPC Level 5 categories into pgvector-compatible SQL.

Generates embeddings for each category using Ollama's nomic-embed-text model
and exports SQL INSERT statements for PostgreSQL with pgvector extension.

When Ollama is unavailable (e.g. during Docker build), falls back to
deterministic placeholder embeddings so the SQL file can still be generated.
"""

import json
import argparse
import asyncio
import hashlib
from pathlib import Path

from ollama import AsyncClient


def load_gpc_json(path: Path) -> dict:
    """Load GPC JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_level5_categories(schema: list) -> list[dict]:
    """Extract all Level 5 categories from GPC schema."""
    categories = []

    def traverse(categories_list: list):
        for cat in categories_list:
            if cat.get("Level") == 5:
                categories.append(
                    {
                        "code": cat.get("Code"),
                        "title": cat.get("Title"),
                        "definition": cat.get("Definition", ""),
                        "active": cat.get("Active", True),
                    }
                )
            children = cat.get("Childs", [])
            if children:
                traverse(children)

    traverse(schema)
    return categories


def _placeholder_embedding(text: str, dim: int = 768) -> list[float]:
    """Generate a deterministic placeholder embedding from text hash.

    Used when Ollama is unavailable (e.g. Docker build stage).
    """
    h = hashlib.sha256(text.encode("utf-8")).digest()
    # Expand 32 bytes to 768 dims by repeating with slight variation
    embedding: list[float] = []
    for i in range(dim):
        byte_val = h[i % len(h)]
        embedding.append((byte_val / 127.5) - 1.0)  # range [-1, 1]
    return embedding


async def generate_embedding(
    text: str, client: AsyncClient, model: str = "nomic-embed-text"
) -> list[float]:
    """Generate embedding for text using Ollama."""
    response = await client.embeddings(model=model, prompt=text)
    embedding = response.embedding
    assert len(embedding) == 768, f"Expected 768-dim embedding, got {len(embedding)}"
    return embedding


async def embed_categories(
    categories: list[dict],
    ollama_host: str,
    model: str = "nomic-embed-text",
) -> list[dict]:
    """Generate embeddings for all categories.

    Falls back to deterministic placeholder embeddings when Ollama is
    unavailable (e.g. during Docker build).
    """
    client = AsyncClient(host=ollama_host)

    # Quick connectivity probe
    try:
        await client.ps()
    except Exception:
        print(
            f"WARNING: Ollama not reachable at {ollama_host}; "
            "using deterministic placeholder embeddings."
        )
        for i, cat in enumerate(categories):
            embed_text = f"{cat['title']} - {cat['definition']}"
            print(f"Embedding {i + 1}/{len(categories)}: {cat['title']} (placeholder)")
            cat["embedding"] = _placeholder_embedding(embed_text)
        return categories

    for i, cat in enumerate(categories):
        # Build embedding text from title and definition
        embed_text = f"{cat['title']} - {cat['definition']}"
        # Truncate to ~512 tokens (approx 2000 chars)
        embed_text = embed_text[:2000]

        print(f"Embedding {i + 1}/{len(categories)}: {cat['title']}")
        embedding = await generate_embedding(embed_text, client, model)
        cat["embedding"] = embedding

    return categories


def export_sql(
    categories: list[dict],
    output_path: Path,
    source_date: str,
    model: str = "nomic-embed-text",
):
    """Export categories to SQL file."""
    with open(output_path, "w", encoding="utf-8") as f:
        # Drop and recreate table
        f.write("BEGIN;\n")
        f.write("DROP TABLE IF EXISTS gpc_categories CASCADE;\n")
        f.write("DROP TABLE IF EXISTS gpc_import_metadata CASCADE;\n")

        # Create tables
        f.write(
            """
CREATE TABLE gpc_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gpc_code INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    definition TEXT,
    level INTEGER NOT NULL DEFAULT 5,
    embedding vector(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_gpc_embedding ON gpc_categories
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE gpc_import_metadata (
    id INTEGER PRIMARY KEY DEFAULT 1,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_date TEXT NOT NULL,
    category_count INTEGER NOT NULL,
    embedding_model TEXT NOT NULL
);
"""
        )

        # Insert categories
        for cat in categories:
            embedding_str = "[" + ",".join(str(x) for x in cat["embedding"]) + "]"
            title_escaped = cat["title"].replace("'", "''")
            definition_escaped = cat["definition"].replace("'", "''")
            f.write(
                f"""
INSERT INTO gpc_categories (gpc_code, title, definition, embedding)
VALUES ({cat["code"]}, '{title_escaped}',
        '{definition_escaped}', '{embedding_str}'::vector);
"""
            )

        # Insert metadata
        f.write(
            f"""
INSERT INTO gpc_import_metadata (source_date, category_count, embedding_model)
VALUES ('{source_date}', {len(categories)}, '{model}');
"""
        )

        f.write("COMMIT;\n")

    print(f"SQL exported to {output_path}")


async def main():
    parser = argparse.ArgumentParser(description="Import GPC categories")
    parser.add_argument("--input", required=True, help="Path to GPC JSON file")
    parser.add_argument("--output", required=True, help="Path to output SQL file")
    parser.add_argument("--ollama-host", default="http://localhost:11434", help="Ollama host")
    parser.add_argument("--model", default="nomic-embed-text", help="Embedding model name")
    args = parser.parse_args()

    print(f"Loading GPC JSON from {args.input}...")
    gpc_data = load_gpc_json(Path(args.input))
    source_date = gpc_data.get("DateUtc", "unknown")

    print("Extracting Level 5 categories...")
    categories = extract_level5_categories(gpc_data.get("Schema", []))
    print(f"Found {len(categories)} Level 5 categories")

    print("Generating embeddings...")
    categories = await embed_categories(categories, args.ollama_host, args.model)

    print("Exporting SQL...")
    export_sql(categories, Path(args.output), source_date, args.model)

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
