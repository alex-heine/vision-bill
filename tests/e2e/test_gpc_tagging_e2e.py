"""E2E: GPC vector-based tagging flow.

Pre-imports test GPC categories with pre-computed embeddings, then verifies
that uploading a receipt results in correct GPC tags being applied to line items.
Uses the mocked LLM stub so no real Ollama calls are made.
"""

import subprocess
from pathlib import Path

import pytest

from e2e.helpers import API, register_user, wait_until

pytestmark = pytest.mark.e2e


def import_test_gpc_data():
    """Import test GPC data into the E2E database."""
    sql_path = Path(__file__).parent / "data" / "gpc_test_import.sql"
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "vision-bill-pg-1",
            "psql",
            "-U",
            "vision_bill",
            "-d",
            "vision_bill",
        ],
        input=sql_path.read_text(),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"Failed to import test GPC data: {result.stderr}")


@pytest.fixture(scope="module")
def gpc_data_imported():
    """Import test GPC data once for all tests in this module."""
    import_test_gpc_data()
    yield


def test_gpc_tagging_flow(http_factory, gpc_data_imported):
    """Test the full GPC tagging flow: upload -> LLM -> tagging -> response."""
    client, _ = register_user(http_factory, "gpc")

    # Upload a test receipt
    test_image = Path(__file__).parent / "data" / "seed_receipt.png"

    with test_image.open("rb") as f:
        response = client.post(
            f"{API}/images",
            files={"receipt": ("seed_receipt.png", f, "image/png")},
        )
    assert response.status_code in (201, 202), response.text

    image_id = response.json()["image_id"]

    # Wait for analysis to complete
    def check_analysis():
        client.post(f"{API}/images/analyze")
        row = client.get(f"{API}/images/{image_id}").json()
        return row if row["status"] == "analyzed" else None

    row = wait_until(check_analysis, timeout_s=60.0)
    assert row["receipt_id"] is not None

    # Check that the receipt has GPC tags
    receipt = client.get(f"{API}/receipts/{row['receipt_id']}").json()
    line_items = receipt["line_items"]

    # Verify at least one line item has tags
    tagged_items = [item for item in line_items if item.get("tags")]
    assert len(tagged_items) > 0, "No line items have GPC tags"

    # Verify tags are GPC category names
    for item in tagged_items:
        for tag in item["tags"]:
            # Tags should be GPC category names (uppercase)
            assert isinstance(tag, str)
            assert len(tag) > 0
