#!/usr/bin/env python3
"""Analyze German GPC hierarchical structure."""

import json
from pathlib import Path
from collections import Counter


def load_gpc(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def count_levels(cats, counts):
    for cat in cats:
        level = cat.get("Level")
        counts[level] = counts.get(level, 0) + 1
        children = cat.get("Childs", [])
        if children:
            count_levels(children, counts)


def collect_l5_codes(cats, codes):
    for cat in cats:
        if cat.get("Level") == 5:
            codes.add(cat.get("Code"))
        children = cat.get("Childs", [])
        if children:
            collect_l5_codes(children, codes)


def main():
    file_path = Path("gpclist-german.json")
    data = load_gpc(file_path)
    schema = data.get("Schema", [])

    print(f"German GPC file analysis:")
    print(f"  DateUtc: {data.get('DateUtc', 'N/A')}")
    print(f"  Top-level categories: {len(schema)}")

    # Count by level
    level_counts = Counter()
    count_levels(schema, level_counts)

    print(f"\nCategories by level:")
    for level in sorted(level_counts.keys()):
        print(f"  Level {level}: {level_counts[level]}")

    # Count unique Level 5 codes
    l5_codes = set()
    collect_l5_codes(schema, l5_codes)

    print(f"\nLevel 5 (Attribute) counts:")
    print(f"  Total entries: {level_counts.get(5, 0)}")
    print(f"  Unique codes: {len(l5_codes)}")
    print(f"  Duplicates: {level_counts.get(5, 0) - len(l5_codes)}")


if __name__ == "__main__":
    main()
