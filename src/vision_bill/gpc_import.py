#!/usr/bin/env python3
"""Import GPC data from embedded SQL file."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def import_gpc(db_url: str, sql_path: Path) -> None:
    """Run psql to import GPC data."""
    # Parse db_url to extract connection parameters
    # Format: postgresql://user:pass@host:port/db
    from urllib.parse import urlparse

    parsed = urlparse(db_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    user = parsed.username or "vision_bill"
    password = parsed.password or ""
    db = parsed.path.lstrip("/") or "vision_bill"

    env = os.environ.copy()
    env["PGPASSWORD"] = password
    cmd = [
        "psql",
        "-h",
        host,
        "-p",
        str(port),
        "-U",
        user,
        "-d",
        db,
        "-f",
        str(sql_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    if result.returncode != 0:
        print(f"Import failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print("GPC data imported successfully")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import GPC data")
    parser.add_argument("--db-url", required=True, help="PostgreSQL DSN")
    parser.add_argument("--sql-path", required=True, type=Path, help="Path to GPC import SQL file")
    args = parser.parse_args()

    import_gpc(args.db_url, args.sql_path)


if __name__ == "__main__":
    main()
