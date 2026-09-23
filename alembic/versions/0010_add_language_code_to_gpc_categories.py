"""add_language_code_to_gpc_categories

Revision ID: 0010
Revises: 3394f636f5aa
Create Date: 2026-09-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "3394f636f5aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add language_code column (VARCHAR(5), NOT NULL, default 'en')
    op.add_column(
        "gpc_categories",
        sa.Column(
            "language_code",
            sa.String(5),
            nullable=False,
            server_default="en",
        ),
    )
    # Add composite unique constraint
    op.create_unique_constraint(
        "uq_gpc_code_language",
        "gpc_categories",
        ["gpc_code", "language_code"],
    )
    # Drop old unique constraint on gpc_code alone
    op.drop_constraint(
        "gpc_categories_gpc_code_key",
        "gpc_categories",
        type_="unique",
    )


def downgrade() -> None:
    # Drop composite unique constraint
    op.drop_constraint(
        "uq_gpc_code_language",
        "gpc_categories",
        type_="unique",
    )
    # Recreate old unique constraint on gpc_code alone
    op.create_unique_constraint(
        "gpc_categories_gpc_code_key",
        "gpc_categories",
        ["gpc_code"],
    )
    # Drop the language_code column
    op.drop_column("gpc_categories", "language_code")
