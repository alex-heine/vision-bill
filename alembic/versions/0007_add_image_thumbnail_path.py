"""Add a thumbnail_path column to images.

Revision ID: 0007
Revises: 0006
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE images ADD COLUMN IF NOT EXISTS thumbnail_path TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE images DROP COLUMN IF EXISTS thumbnail_path;")
