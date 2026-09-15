"""Add a position column to line_items for deterministic ordering.

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE line_items ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0;"
    )
    op.execute(
        """
        UPDATE line_items li
            SET position = sub.n
            FROM (
                SELECT id, ROW_NUMBER() OVER (PARTITION BY receipt_id ORDER BY id) - 1 AS n
                FROM line_items
            ) sub
            WHERE li.id = sub.id;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE line_items DROP COLUMN IF EXISTS position;")
