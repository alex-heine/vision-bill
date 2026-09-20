"""Tests for GPC import check and import scripts."""

import tempfile
from pathlib import Path

import pytest

from vision_bill.gpc_check import extract_source_date


@pytest.fixture
def sample_sql_file():
    """Create a temporary SQL file with GPC import content."""
    content = """BEGIN;
DROP TABLE IF EXISTS gpc_categories CASCADE;
DROP TABLE IF EXISTS gpc_import_metadata CASCADE;

CREATE TABLE gpc_import_metadata (
    id INTEGER PRIMARY KEY DEFAULT 1,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_date TEXT NOT NULL,
    category_count INTEGER NOT NULL,
    embedding_model TEXT NOT NULL
);

INSERT INTO gpc_import_metadata (source_date, category_count, embedding_model)
VALUES ('20/5/2026', 10188, 'nomic-embed-text');
COMMIT;
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
        f.write(content)
        f.flush()
        yield Path(f.name)
    f.close()
    Path(f.name).unlink()


def test_extract_source_date(sample_sql_file):
    """Test that source_date is correctly extracted from SQL file."""
    source_date = extract_source_date(sample_sql_file)
    assert source_date == "20/5/2026"


def test_extract_source_date_missing(sample_sql_file):
    """Test that ValueError is raised when source_date is not found."""
    # Write content without the INSERT statement
    sample_sql_file.write_text("BEGIN; COMMIT;")
    with pytest.raises(ValueError, match="Could not find source_date"):
        extract_source_date(sample_sql_file)
