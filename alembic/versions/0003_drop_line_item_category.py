"""Drop the unused category column from line_items.

The receipt row keeps its own ``category``; per-line-item categories are no
longer persisted or exposed by the API.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE line_items DROP COLUMN IF EXISTS category;")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE line_items ADD COLUMN IF NOT EXISTS "
        "category VARCHAR(50) NOT NULL DEFAULT 'other';"
    )
