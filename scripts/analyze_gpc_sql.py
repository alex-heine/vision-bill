#!/usr/bin/env python3
"""Analyze GPC import SQL file without dumping vector data.

Usage: python analyze_gpc_sql.py <path_to_sql_file>
"""

import re
import sys
from collections import Counter


def analyze_sql(sql_path: str) -> None:
    print(f"Analyzing: {sql_path}")
    print("=" * 60)

    with open(sql_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Count INSERT statements
    inserts = re.findall(r"INSERT INTO gpc_categories", content)
    print(f"Total INSERT statements: {len(inserts)}")

    # Extract language_code values
    lang_pattern = r"VALUES \(\d+, '[^']+', '[^']*', '\[[^\]]+\]'::vector, '(\w+)'\)"
    languages = re.findall(lang_pattern, content)
    lang_counts = Counter(languages)

    print(f"\nLanguages found:")
    for lang, count in lang_counts.most_common():
        print(f"  {lang}: {count}")

    # Extract some sample titles (first 5)
    title_pattern = r"VALUES \(\d+, '([^']+)',"
    titles = re.findall(title_pattern, content)[:5]
    print(f"\nSample titles (first 5):")
    for t in titles:
        print(f"  {t[:60]}")

    # Check for vector data size
    vector_pattern = r"'(\[[^\]]+\])'::vector"
    vectors = re.findall(vector_pattern, content)
    if vectors:
        avg_len = sum(len(v) for v in vectors) / len(vectors)
        print(f"\nVector data: {len(vectors)} vectors, avg length {avg_len:.0f} chars")

    # Check for duplicate GPC codes
    code_pattern = r"VALUES \((\d+),"
    codes = re.findall(code_pattern, content)
    code_counts = Counter(codes)
    duplicates = {code: count for code, count in code_counts.items() if count > 1}
    if duplicates:
        print(f"\nWARNING: {len(duplicates)} duplicate GPC codes found")
        for code, count in list(duplicates.items())[:5]:
            print(f"  Code {code}: {count} occurrences")
    else:
        print(f"\nNo duplicate GPC codes found")

    # Check table structure
    if "CREATE TABLE gpc_categories" in content:
        print("\nTable structure: Present")
        if "language_code" in content:
            print("  language_code column: Present")
        if "UNIQUE (gpc_code, language_code)" in content:
            print("  Composite unique constraint: Present")
    else:
        print("\nTable structure: Not found (expected in fresh import)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python analyze_gpc_sql.py <path_to_sql_file>")
        sys.exit(1)

    analyze_sql(sys.argv[1])
