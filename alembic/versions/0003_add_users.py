"""Add the multi-user authentication schema.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-03 00:00:00.000000

Introduces the ``users`` table plus a nullable per-row ``user_id`` owner
column on ``receipts`` and ``images``. The new columns are nullable so the
application keeps booting and behaving exactly as before until later parts of
the authentication work wire up per-user ownership.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL        PRIMARY KEY,
    username        VARCHAR(100)  NOT NULL UNIQUE,
    hashed_password TEXT          NOT NULL,
    is_admin        BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ   DEFAULT now()
);
"""

# Owner column on each resource table. Nullable: legacy rows stay valid and the
# app is unchanged until ownership is enforced in a later migration's consumers.
ADD_RECEIPT_USER_ID_SQL = (
    "ALTER TABLE receipts ADD COLUMN user_id INT REFERENCES users(id) ON DELETE CASCADE;"
)

ADD_IMAGE_USER_ID_SQL = (
    "ALTER TABLE images ADD COLUMN user_id INT REFERENCES users(id) ON DELETE CASCADE;"
)

CREATE_RECEIPT_USER_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS ix_receipts_user_id ON receipts (user_id);"
)

CREATE_IMAGE_USER_INDEX_SQL = "CREATE INDEX IF NOT EXISTS ix_images_user_id ON images (user_id);"


def upgrade() -> None:
    op.execute(CREATE_USERS_SQL)
    op.execute(ADD_RECEIPT_USER_ID_SQL)
    op.execute(ADD_IMAGE_USER_ID_SQL)
    op.execute(CREATE_RECEIPT_USER_INDEX_SQL)
    op.execute(CREATE_IMAGE_USER_INDEX_SQL)


def downgrade() -> None:
    # Drop the indexes, then the owner columns, then the users table.
    op.execute("DROP INDEX IF EXISTS ix_images_user_id;")
    op.execute("DROP INDEX IF EXISTS ix_receipts_user_id;")
    op.execute("ALTER TABLE images DROP COLUMN IF EXISTS user_id;")
    op.execute("ALTER TABLE receipts DROP COLUMN IF EXISTS user_id;")
    op.execute("DROP TABLE IF EXISTS users;")
