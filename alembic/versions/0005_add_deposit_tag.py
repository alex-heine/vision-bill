"""Seed the `deposit` line-item tag into the global vocabulary.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("INSERT INTO tags (name) VALUES ('deposit') ON CONFLICT (name) DO NOTHING;")


def downgrade() -> None:
    op.execute("DELETE FROM tags WHERE name = 'deposit';")
