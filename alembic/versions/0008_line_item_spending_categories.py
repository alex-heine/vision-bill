"""Add spending categories and user-confirmed exact item history.

Revision ID: 0008
Revises: 0007
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE line_items ADD COLUMN spending_category TEXT NOT NULL DEFAULT 'unknown'")
    op.execute("ALTER TABLE line_items ADD COLUMN category_source TEXT NOT NULL DEFAULT 'unknown'")
    op.execute("ALTER TABLE line_items ADD COLUMN original_description TEXT")
    op.execute("UPDATE line_items SET original_description = description")
    op.execute("ALTER TABLE line_items ALTER COLUMN original_description SET NOT NULL")
    op.execute(
        "UPDATE line_items SET spending_category = 'deposit' "
        "WHERE 'deposit' = ANY(tags)"
    )
    op.execute(
        "ALTER TABLE line_items ADD CONSTRAINT line_items_category_source_check "
        "CHECK (category_source IN ('llm', 'history', 'user', 'unknown'))"
    )
    op.execute(
        "CREATE TABLE item_category_aliases ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "merchant_key TEXT NOT NULL, description_key TEXT NOT NULL, "
        "category TEXT NOT NULL, "
        "UNIQUE (user_id, merchant_key, description_key))"
    )


def downgrade() -> None:
    op.execute("DROP TABLE item_category_aliases")
    op.execute("ALTER TABLE line_items DROP CONSTRAINT line_items_category_source_check")
    op.execute("ALTER TABLE line_items DROP COLUMN original_description")
    op.execute("ALTER TABLE line_items DROP COLUMN category_source")
    op.execute("ALTER TABLE line_items DROP COLUMN spending_category")
