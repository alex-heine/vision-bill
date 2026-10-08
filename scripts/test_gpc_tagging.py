#!/usr/bin/env python3
"""Test GPC tagging quality against test data."""

import asyncio
import json
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, "/mnt/hdd_gaming/dev/vision-bill/src")

from vision_bill.model.receipt import LineItem, Receipt
from vision_bill.service.embedding_service import EmbeddingService
from vision_bill.service.tagging_service import TaggingService

# Database config
DB_USER = "vision_bill"
DB_PASSWORD = "Testest12!"
DB_NAME = "vision_bill"
DB_HOST = "postgres"
DB_PORT = 5432

OLLAMA_HOST = "http://host.docker.internal:11434"
EMBEDDING_MODEL = "nomic-embed-text"

TEST_DATA_DIR = Path("/app/tests/data")


def load_test_data():
    """Load all test receipts from JSON files."""
    receipts = []
    print(f"Looking for JSON files in {TEST_DATA_DIR}")
    json_files = list(TEST_DATA_DIR.glob("*.json"))
    print(f"Found {len(json_files)} JSON files")

    for json_file in json_files:
        print(f"Loading {json_file}")
        with open(json_file) as f:
            data = json.load(f)

        # Create receipt object
        receipt = Receipt(
            merchant_name=data["receipt"]["merchant_name"],
            merchant_address=data["receipt"]["merchant_address"],
            receipt_number=data["receipt"]["receipt_number"],
            date=data["receipt"]["date"],
            time=data["receipt"]["time"],
            currency=data["receipt"]["currency"],
            category=data["receipt"]["category"],
            confidence=data["receipt"].get("confidence", 95),
            subtotal=float(data["receipt"]["subtotal"]),
            tax_total=float(data["receipt"]["tax_total"]),
            total=float(data["receipt"]["total"]),
            payment_method=data["receipt"]["payment_method"],
            line_items=[],
            taxes=[],
        )

        # Add line items
        for item_data in data["line_items"]:
            item = LineItem(
                description=item_data["description"],
                quantity=item_data["quantity"],
                unit_price=float(item_data["unit_price"]),
                total_price=float(item_data["total_price"]),
                tags=item_data.get("tags", []),
            )
            receipt.line_items.append(item)

        receipts.append(receipt)
        print(f"  Loaded {len(receipt.line_items)} items from {json_file}")

    return receipts


async def test_tagging():
    """Run GPC tagging test and evaluate quality."""
    print("Loading test data...")
    receipts = load_test_data()
    print(
        f"Loaded {len(receipts)} receipts with {sum(len(r.line_items) for r in receipts)} line items"
    )

    print("\nInitializing services...")
    embedding_service = EmbeddingService(OLLAMA_HOST, EMBEDDING_MODEL)

    # Connect to database
    pool = await asyncpg.create_pool(
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        host=DB_HOST,
        port=DB_PORT,
        min_size=1,
        max_size=5,
    )

    # Import the DB class and wrap the pool
    from vision_bill.provider.db.receipt_db import ReceiptDB

    # Create a mock ReceiptDB with our pool
    class MockPGSettings:
        def __init__(self):
            self.pg_dsn = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    db = ReceiptDB(MockPGSettings())
    db._pool = pool
    tagging_service = TaggingService(embedding_service, db)

    # Test each line item
    results = []
    total_items = 0
    correct = 0
    close = 0
    wrong = 0

    print("\nTesting GPC tagging...")
    for receipt in receipts:
        for item in receipt.line_items:
            total_items += 1

            # Get GPC suggestion
            try:
                tag = await tagging_service.tag_line_item(item, language="de")
            except Exception as e:
                tag = f"ERROR: {e}"

            # Evaluate quality
            # Simple heuristic: check if the GPC tag makes sense for the item
            quality = evaluate_tag_quality(item, tag)

            if quality == "correct":
                correct += 1
            elif quality == "close":
                close += 1
            else:
                wrong += 1

            results.append(
                {
                    "receipt": receipt.merchant_name,
                    "description": item.description,
                    "existing_tags": item.tags,
                    "gpc_tag": tag,
                    "quality": quality,
                }
            )

    # Print results table
    print("\n" + "=" * 120)
    print(f"{'Receipt':<15} {'Description':<30} {'Existing Tags':<15} {'GPC Tag':<25} {'Quality'}")
    print("-" * 120)

    for r in results:
        existing = ",".join(r["existing_tags"]) if r["existing_tags"] else "-"
        print(
            f"{r['receipt']:<15} {r['description']:<30} {existing:<15} {r['gpc_tag']:<25} {r['quality']}"
        )

    print("=" * 120)

    # Summary
    print(f"\nSummary:")
    print(f"  Total items tested: {total_items}")
    print(f"  Correct: {correct} ({correct / total_items * 100:.1f}%)")
    print(f"  Close: {close} ({close / total_items * 100:.1f}%)")
    print(f"  Wrong: {wrong} ({wrong / total_items * 100:.1f}%)")
    print(f"  Overall accuracy: {(correct + close) / total_items * 100:.1f}%")

    await pool.close()


def evaluate_tag_quality(item: LineItem, gpc_tag: str) -> str:
    """Evaluate if the GPC tag makes sense for the item."""
    desc = item.description.lower()
    tag = gpc_tag.lower()

    # Define expected category mappings based on item description
    if any(w in desc for w in ["pfand", "leergut"]):
        # Deposit items should be tagged as deposit
        if "deposit" in tag or "pfand" in tag:
            return "correct"
        return "close"

    if any(
        w in desc
        for w in [
            "hähnchen",
            "schinken",
            "hack",
            "brat",
            "filet",
            "gulasch",
            "frikadellen",
            "wurst",
            "krusten",
        ]
    ):
        # Meat products
        if any(
            w in tag
            for w in ["meat", "poultry", "beef", "pork", "chicken", "ham", "sausage", "wurst"]
        ):
            return "correct"
        if "food" in tag or "grocery" in tag:
            return "close"
        return "wrong"

    if any(
        w in desc
        for w in [
            "bananen",
            "trauben",
            "gurken",
            "apfel",
            "nektarine",
            "kartoffel",
            "porree",
            "champ",
            "broccoli",
            "blumenkohl",
            "spinat",
        ]
    ):
        # Fresh produce
        if any(w in tag for w in ["fruit", "vegetable", "produce", "fresh"]):
            return "correct"
        if "food" in tag or "grocery" in tag:
            return "close"
        return "wrong"

    if any(
        w in desc
        for w in ["saft", "monster", "rockstar", "adl", "pfanner", "orangen", "ananas", "eist"]
    ):
        # Beverages
        if any(w in tag for w in ["beverage", "drink", "juice", "soda", "energy"]):
            return "correct"
        if "food" in tag or "grocery" in tag:
            return "close"
        return "wrong"

    if any(
        w in desc
        for w in [
            "milch",
            "käse",
            "fischstäbchen",
            "pizza",
            "nuggets",
            "nudelt",
            "samosas",
            "tortilla",
            "reis",
            "pasta",
            "noodle",
        ]
    ):
        # Dairy, frozen, prepared foods
        if any(
            w in tag
            for w in ["dairy", "cheese", "milk", "frozen", "pizza", "noodle", "pasta", "rice"]
        ):
            return "correct"
        if "food" in tag or "grocery" in tag:
            return "close"
        return "wrong"

    if any(w in desc for w in ["katjes", "süß", "schokolade", "candy", "bonbon"]):
        # Candy/sweets
        if any(w in tag for w in ["candy", "sweet", "chocolate", "snack"]):
            return "correct"
        if "food" in tag or "grocery" in tag:
            return "close"
        return "wrong"

    if any(w in desc for w in ["tasche", "silikon", "ot"]):
        # Household items
        if any(w in tag for w in ["household", "kitchen", "bag"]):
            return "correct"
        if "food" in tag or "grocery" in tag:
            return "close"
        return "wrong"

    if any(w in desc for w in ["storage", "box"]):
        # Storage
        if any(w in tag for w in ["storage", "box", "container"]):
            return "correct"
        if "household" in tag:
            return "close"
        return "wrong"

    # Default: any food/grocery tag is acceptable
    if "food" in tag or "grocery" in tag or "beverage" in tag:
        return "correct"

    return "close"


if __name__ == "__main__":
    asyncio.run(test_tagging())
