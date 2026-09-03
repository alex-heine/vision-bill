"""Add the tags table (line-item tag vocabulary).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-02 00:00:00.000000

Line-item tags become a controlled vocabulary stored in the database. The
migration seeds a starter set of tags and backfills every tag already in use
on existing line items so no stored data is orphaned.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_TAGS_SQL = """
CREATE TABLE IF NOT EXISTS tags (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);
"""

# Starter vocabulary; the table is the single source of truth from here on.
SEED_TAGS_SQL = """
INSERT INTO tags (name) VALUES
    ('alcohol'),
    ('beverage'),
    ('coffee'),
    ('food'),
    ('fresh'),
    ('household'),
    ('hygiene'),
    ('office'),
    ('electronics'),
    ('gift'),
    ('pet'),
    ('travel'),
    ('subscription'),
    ('service'),
    ('other')
ON CONFLICT (name) DO NOTHING;
"""

# Register every tag already in use on line items so existing receipts stay valid.
BACKFILL_TAGS_SQL = """
INSERT INTO tags (name)
SELECT DISTINCT tag
FROM line_items, unnest(line_items.tags) AS tag
WHERE tag IS NOT NULL AND trim(tag) <> ''
ON CONFLICT (name) DO NOTHING;
"""


def upgrade() -> None:
    op.execute(CREATE_TAGS_SQL)
    op.execute(SEED_TAGS_SQL)
    op.execute(BACKFILL_TAGS_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tags;")
