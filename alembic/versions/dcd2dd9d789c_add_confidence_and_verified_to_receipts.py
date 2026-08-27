"""Add confidence and verified columns to receipts

Revision ID: dcd2dd9d789c
Revises: 0001
Create Date: 2026-08-28 00:14:18.828871

The 0001 baseline only creates missing tables (IF NOT EXISTS), so on
existing dev databases these two columns would never appear. Both are
added with NOT NULL DEFAULT so existing rows get confidence = 0 and
verified = FALSE.

Each statement is executed in its own op.execute() call (one SQL
statement per prepared-statement execution).
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dcd2dd9d789c"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE receipts ADD COLUMN IF NOT EXISTS confidence SMALLINT NOT NULL DEFAULT 0;"
    )
    op.execute(
        "ALTER TABLE receipts ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT FALSE;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE receipts DROP COLUMN IF EXISTS verified;")
    op.execute("ALTER TABLE receipts DROP COLUMN IF EXISTS confidence;")
