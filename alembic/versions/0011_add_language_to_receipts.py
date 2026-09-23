"""add_language_to_receipts

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add language column (VARCHAR(5), NOT NULL, default 'en')
    op.add_column(
        "receipts",
        sa.Column(
            "language",
            sa.String(5),
            nullable=False,
            server_default="en",
        ),
    )


def downgrade() -> None:
    op.drop_column("receipts", "language")
