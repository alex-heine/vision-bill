"""Add collections and the receipt<->collection join table.

Collections are named, per-user groups a whole receipt may belong to
(many-to-many). Receipts and statistics can be scoped to a collection.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS collections (
            id           UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name         VARCHAR(100)    NOT NULL,
            color        VARCHAR(20),
            start_date   DATE,
            end_date     DATE,
            active       BOOLEAN         NOT NULL DEFAULT FALSE,
            created_at   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS receipt_collections (
            receipt_id    UUID NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
            collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
            PRIMARY KEY (receipt_id, collection_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_receipt_collections_collection_id "
        "ON receipt_collections (collection_id);"
    )
    # Guardrail: at most one active (auto-capturing) collection per user.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_collections_one_active_per_user "
        "ON collections (user_id) WHERE active = TRUE;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_collections_one_active_per_user;")
    op.execute("DROP INDEX IF EXISTS ix_receipt_collections_collection_id;")
    op.execute("DROP TABLE IF EXISTS receipt_collections;")
    op.execute("DROP TABLE IF EXISTS collections;")
