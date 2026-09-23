#!/usr/bin/env python3
"""Analyze GPC file structure and test importing only category 50000000."""

import json
from pathlib import Path
from collections import Counter


def load_gpc(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def count_all_level5(schema):
    """Count all Level 5 entries (including duplicates)."""
    count = 0

    def traverse(cats):
        nonlocal count
        for cat in cats:
            if cat.get("Level") == 5:
                count += 1
            children = cat.get("Childs", [])
            if children:
                traverse(children)

    traverse(schema)
    return count


def count_unique_level5(schema):
    """Count unique Level 5 codes."""
    codes = set()

    def traverse(cats):
        for cat in cats:
            if cat.get("Level") == 5:
                codes.add(cat.get("Code"))
            children = cat.get("Childs", [])
            if children:
                traverse(children)

    traverse(schema)
    return len(codes)


def find_category(schema, code):
    """Find a category by code."""
    for cat in schema:
        if cat.get("Code") == code:
            return cat
        children = cat.get("Childs", [])
        if children:
            result = find_category(children, code)
            if result:
                return result
    return None


def count_level5_in_subtree(category):
    """Count Level 5 entries in a category subtree."""
    count = 0
    codes = set()

    def traverse(cats):
        nonlocal count
        for cat in cats:
            if cat.get("Level") == 5:
                count += 1
                codes.add(cat.get("Code"))
            children = cat.get("Childs", [])
            if children:
                traverse(children)

    traverse(category.get("Childs", []))
    return count, len(codes)


def main():
    file_path = Path("gpclist-german.json")
    if not file_path.exists():
        print(f"File not found: {file_path}")
        return

    print(f"Analyzing: {file_path.name}")
    data = load_gpc(file_path)
    schema = data.get("Schema", [])

    # Overall counts
    total_l5 = count_all_level5(schema)
    unique_l5 = count_unique_level5(schema)
    print(f"\nOverall Level 5 counts:")
    print(f"  Total entries: {total_l5}")
    print(f"  Unique codes: {unique_l5}")
    print(f"  Duplicates: {total_l5 - unique_l5}")

    # Find category 50000000
    target_code = 50000000
    target = find_category(schema, target_code)

    if target:
        print(f"\nCategory {target_code}: {target.get('Title', '')[:50]}")
        subtree_total, subtree_unique = count_level5_in_subtree(target)
        print(f"  Level 5 entries in subtree: {subtree_total}")
        print(f"  Unique Level 5 codes in subtree: {subtree_unique}")
        print(f"  Duplicates in subtree: {subtree_total - subtree_unique}")

        # Compare with overall
        print(f"\nComparison:")
        print(f"  Overall unique: {unique_l5}")
        print(f"  Subtree unique: {subtree_unique}")
        print(f"  Difference: {unique_l5 - subtree_unique}")
    else:
        print(f"\nCategory {target_code} not found")

        # List top-level categories
        print("\nTop-level categories:")
        for cat in schema[:10]:
            code = cat.get("Code")
            title = cat.get("Title", "")[:40]
            print(f"  {code}: {title}")


if __name__ == "__main__":
    main()
