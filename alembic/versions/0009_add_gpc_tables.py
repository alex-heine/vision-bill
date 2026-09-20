"""add_gpc_tables

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-19
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS gpc_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gpc_code INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    definition TEXT,
    level INTEGER NOT NULL DEFAULT 5,
    embedding vector(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
""")

    op.execute("""
CREATE INDEX IF NOT EXISTS idx_gpc_embedding ON gpc_categories
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
""")

    op.execute("""
CREATE TABLE IF NOT EXISTS gpc_import_metadata (
    id INTEGER PRIMARY KEY DEFAULT 1,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_date TEXT NOT NULL,
    category_count INTEGER NOT NULL,
    embedding_model TEXT NOT NULL
);
""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gpc_import_metadata CASCADE")
    op.execute("DROP TABLE IF EXISTS gpc_categories CASCADE")
