#!/usr/bin/env python3
"""Comprehensive analysis of GPC JSON structure."""

import json
import sys


def count_categories(schema):
    """Count all categories by level."""
    levels = {}

    def traverse(categories):
        for cat in categories:
            level = cat.get("Level", 0)
            levels[level] = levels.get(level, 0) + 1
            children = cat.get("Childs", [])
            if children:
                traverse(children)

    traverse(schema)
    return levels


def get_all_leaf_categories(schema):
    """Get all leaf categories (no children)."""
    leaves = []

    def traverse(categories):
        for cat in categories:
            children = cat.get("Childs", [])
            if not children:
                leaves.append(
                    {
                        "code": cat.get("Code"),
                        "title": cat.get("Title"),
                        "level": cat.get("Level"),
                        "definition": cat.get("Definition", "")[:100],
                    }
                )
            else:
                traverse(children)

    traverse(schema)
    return leaves


def analyze_gpc_file(filepath):
    """Analyze GPC JSON structure."""
    print(f"Analyzing: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Language: {data.get('LanguageCode')}")
    print(f"Date: {data.get('DateUtc')}")
    print(f"Schema entries (top-level): {len(data.get('Schema', []))}")

    # Count by level
    levels = count_categories(data.get("Schema", []))
    print(f"\nCategories by level:")
    for level in sorted(levels.keys()):
        print(f"  Level {level}: {levels[level]}")
    print(f"  Total: {sum(levels.values())}")

    # Get leaf categories
    leaves = get_all_leaf_categories(data.get("Schema", []))
    print(f"\nLeaf categories (no children): {len(leaves)}")

    # Show some examples
    print(f"\nExample leaf categories:")
    for leaf in leaves[:5]:
        print(f"  {leaf['code']} - {leaf['title']} (Level {leaf['level']})")
        print(f"    Definition: {leaf['definition']}...")

    # Show top-level structure
    print(f"\nTop-level categories:")
    for cat in data.get("Schema", [])[:5]:
        print(f"  {cat.get('Code')} - {cat.get('Title')}")
        print(f"    Children: {len(cat.get('Childs', []))}")


if __name__ == "__main__":
    filepath = "./docs/gpc-list_formatted.json"
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    analyze_gpc_file(filepath)
