"""Ordered receipt photos and explicit terminal extraction outcomes."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE images ADD COLUMN additional_images JSONB NOT NULL DEFAULT '[]'")
    op.execute("ALTER TABLE images ADD COLUMN model_id TEXT")
    op.execute("ALTER TABLE images DROP CONSTRAINT images_status_check")
    op.execute(
        "ALTER TABLE images ADD CONSTRAINT images_status_check CHECK "
        "(status IN ('pending', 'processing', 'analyzed', 'failed', 'timed_out', 'unreadable'))"
    )


def downgrade() -> None:
    op.execute("UPDATE images SET status = 'failed' WHERE status IN ('timed_out', 'unreadable')")
    op.execute("ALTER TABLE images DROP CONSTRAINT images_status_check")
    op.execute(
        "ALTER TABLE images ADD CONSTRAINT images_status_check CHECK "
        "(status IN ('pending', 'processing', 'analyzed', 'failed'))"
    )
    op.execute("ALTER TABLE images DROP COLUMN model_id")
    op.execute("ALTER TABLE images DROP COLUMN additional_images")
