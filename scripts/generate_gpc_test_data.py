#!/usr/bin/env python3
"""Generate a small test GPC dataset with pre-computed embeddings for E2E testing.

This creates a SQL file with a few test GPC categories and simple test embeddings
(not real Ollama embeddings, just deterministic test vectors).
"""

import json
from pathlib import Path


# Simple test embeddings (768-dim, deterministic for testing)
def make_test_embedding(seed: int) -> list[float]:
    """Generate a simple 768-dim test embedding based on a seed value."""
    # Use a simple pattern: first element is seed/100, rest are small values
    embedding = [seed / 100.0]
    for i in range(1, 768):
        embedding.append((seed + i) / 10000.0)
    return embedding


# Test GPC categories (simplified for testing)
TEST_CATEGORIES = [
    {
        "gpc_code": 30000001,
        "title": "MILK",
        "definition": "Dairy milk products including whole, reduced-fat, and skim milk.",
        "embedding": make_test_embedding(1),
    },
    {
        "gpc_code": 30000002,
        "title": "BREAD",
        "definition": "Baked bread products including loaves, rolls, and buns.",
        "embedding": make_test_embedding(2),
    },
    {
        "gpc_code": 30000003,
        "title": "EGGS",
        "definition": "Fresh eggs including chicken, duck, and quail eggs.",
        "embedding": make_test_embedding(3),
    },
]


def generate_sql(categories: list[dict], output_path: Path) -> None:
    """Generate SQL file for importing test GPC categories."""
    with open(output_path, "w") as f:
        f.write("BEGIN;\n\n")

        # Drop and recreate tables
        f.write("DROP TABLE IF EXISTS gpc_categories CASCADE;\n")
        f.write("DROP TABLE IF EXISTS gpc_import_metadata CASCADE;\n\n")

        # Create gpc_categories table
        f.write("""CREATE TABLE gpc_categories (
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
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
""")

        # Create gpc_import_metadata table
        f.write("""CREATE TABLE gpc_import_metadata (
    id INTEGER PRIMARY KEY DEFAULT 1,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_date TEXT NOT NULL,
    category_count INTEGER NOT NULL,
    embedding_model TEXT NOT NULL
);
""")

        # Insert test categories
        for cat in categories:
            embedding_str = "[" + ",".join(f"{x:.6f}" for x in cat["embedding"]) + "]"
            title_escaped = cat["title"].replace("'", "''")
            definition_escaped = cat["definition"].replace("'", "''")
            f.write(f"""INSERT INTO gpc_categories (gpc_code, title, definition, embedding)
VALUES ({cat["gpc_code"]}, '{title_escaped}', '{definition_escaped}', '{embedding_str}'::vector);
""")

        # Insert metadata
        f.write(f"""INSERT INTO gpc_import_metadata (source_date, category_count, embedding_model)
VALUES ('test-2026-01-01', {len(categories)}, 'test-embedding');
""")

        f.write("\nCOMMIT;\n")

    print(f"Generated test GPC SQL at {output_path}")
    print(f"Categories: {len(categories)}")


if __name__ == "__main__":
    output = Path("tests/e2e/data/gpc_test_import.sql")
    generate_sql(TEST_CATEGORIES, output)
