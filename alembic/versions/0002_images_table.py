"""Images table + receipts reference images by FK

Revision ID: 0002
Revises: dcd2dd9d789c
Create Date: 2026-08-29 00:00:00.000000

Introduces an `images` table that owns the on-disk image path and the
analysis workflow (pending / analyzed / failed). Receipts then reference an
image via a foreign key (`receipts.image_id`) instead of storing a raw
`image_path` string.

Upgrade steps (one SQL statement per op.execute, as the asyncpg dialect runs
each statement as a prepared statement):
  1. CREATE the images table.
  2. Backfill: insert an `analyzed` images row for every existing receipt that
     has a non-NULL image_path, linked back to that receipt via images.receipt_id.
  3. ADD receipts.image_id (FK -> images.id, ON DELETE SET NULL).
  4. Link: copy the backfilled images id onto receipts.image_id.
  5. DROP the now-redundant receipts.image_path column.

Downgrade restores image_path from the images table, drops the FK column and
drops the images table.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "dcd2dd9d789c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_IMAGES_SQL = """
CREATE TABLE IF NOT EXISTS images (
    id                SERIAL PRIMARY KEY,
    original_filename VARCHAR(255),
    media_type        VARCHAR(100),
    size_bytes        BIGINT,
    image_path        TEXT,
    status            VARCHAR(20) NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'analyzed', 'failed')),
    error             TEXT,
    receipt_id        INT REFERENCES receipts(id) ON DELETE SET NULL,
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    analyzed_at       TIMESTAMP WITH TIME ZONE
);
"""

# Backfill: one analyzed row per receipt that already has an image_path.
# split_part(path, '/', -1) recovers the file name for original_filename.
# The NOT EXISTS guard keeps the backfill idempotent on re-runs.
BACKFILL_IMAGES_SQL = """
INSERT INTO images
    (original_filename, media_type, size_bytes, image_path, status,
     receipt_id, created_at, analyzed_at)
SELECT
    split_part(r.image_path, '/', -1),
    NULL,
    NULL,
    r.image_path,
    'analyzed',
    r.id,
    r.created_at,
    CURRENT_TIMESTAMP
FROM receipts r
WHERE r.image_path IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM images i WHERE i.receipt_id = r.id
  );
"""

ADD_IMAGE_ID_SQL = (
    "ALTER TABLE receipts ADD COLUMN IF NOT EXISTS image_id "
    "INT REFERENCES images(id) ON DELETE SET NULL;"
)

LINK_IMAGE_ID_SQL = "UPDATE receipts r SET image_id = i.id FROM images i WHERE i.receipt_id = r.id;"

DROP_IMAGE_PATH_SQL = "ALTER TABLE receipts DROP COLUMN IF EXISTS image_path;"


def upgrade() -> None:
    op.execute(CREATE_IMAGES_SQL)
    op.execute(BACKFILL_IMAGES_SQL)
    op.execute(ADD_IMAGE_ID_SQL)
    op.execute(LINK_IMAGE_ID_SQL)
    op.execute(DROP_IMAGE_PATH_SQL)


def downgrade() -> None:
    # Restore the raw path from the images table before dropping the FK.
    op.execute("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS image_path TEXT;")
    op.execute(
        "UPDATE receipts r SET image_path = i.image_path FROM images i WHERE i.id = r.image_id;"
    )
    op.execute("ALTER TABLE receipts DROP COLUMN IF EXISTS image_id;")
    op.execute("DROP TABLE IF EXISTS images;")
