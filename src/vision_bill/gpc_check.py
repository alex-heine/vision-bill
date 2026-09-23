#!/usr/bin/env python3
"""Check if GPC data needs import."""

import argparse
import re
import sys
from pathlib import Path

import asyncpg


def extract_source_date(sql_path: Path) -> str:
    """Extract the source_date from the GPC import SQL file."""
    content = sql_path.read_text(encoding="utf-8")
    # Match: INSERT INTO gpc_import_metadata (source_date, category_count, embedding_model) VALUES ('20/5/2026', 10188, 'nomic-embed-text');
    match = re.search(
        r"INSERT INTO gpc_import_metadata\s*\([^)]*\)\s*VALUES\s*\('([^']+)'",
        content,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"Could not find source_date in {sql_path}")
    return match.group(1)


async def needs_import(db_url: str, sql_path: Path) -> bool:
    """Check if GPC data needs to be imported or updated."""
    expected_source = extract_source_date(sql_path)

    conn = None
    try:
        conn = await asyncpg.connect(db_url)

        # Check if the metadata table exists and has a row
        try:
            result = await conn.fetchrow("SELECT source_date FROM gpc_import_metadata WHERE id = 1")
        except asyncpg.exceptions.UndefinedTableError:
            # Table doesn't exist yet — fresh DB needs import
            return True

        if result is None:
            return True

        current_source = str(result["source_date"])
        return current_source != expected_source
    finally:
        if conn:
            await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Check if GPC data needs import")
    parser.add_argument("--db-url", required=True, help="PostgreSQL DSN")
    parser.add_argument("--sql-path", required=True, type=Path, help="Path to GPC import SQL file")
    args = parser.parse_args()

    import asyncio

    result = asyncio.run(needs_import(args.db_url, args.sql_path))
    # Exit 0 = needs import, Exit 1 = up to date
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
