"""Harden analysis retries and add indexes for verified receipt reporting."""

from typing import Sequence, Union

from alembic import op


revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DROP_IMAGE_STATUS_CHECK_SQL = "ALTER TABLE images DROP CONSTRAINT IF EXISTS images_status_check;"
ADD_IMAGE_STATUS_CHECK_SQL = """
ALTER TABLE images
    ADD CONSTRAINT images_status_check
    CHECK (status IN ('pending', 'processing', 'analyzed', 'failed'));
"""

CREATE_IMAGE_UNIQUE_INDEX_SQL = """
DO $migration$
BEGIN
    -- Do not rewrite historical duplicate rows. If they exist, the trigger
    -- below protects all future inserts and updates instead.
    IF EXISTS (
        SELECT image_id
        FROM receipts
        WHERE image_id IS NOT NULL
        GROUP BY image_id
        HAVING COUNT(*) > 1
    ) THEN
        CREATE INDEX IF NOT EXISTS ix_receipts_image_id
            ON receipts (image_id)
            WHERE image_id IS NOT NULL;
    ELSE
        CREATE UNIQUE INDEX IF NOT EXISTS ux_receipts_image_id
            ON receipts (image_id)
            WHERE image_id IS NOT NULL;
    END IF;
END
$migration$;
"""

CREATE_IMAGE_UNIQUE_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION vision_bill_check_receipt_image_id()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF NEW.image_id IS NULL
       OR (TG_OP = 'UPDATE' AND NEW.image_id IS NOT DISTINCT FROM OLD.image_id) THEN
        RETURN NEW;
    END IF;

    -- Serialize concurrent receipt writes for the same image even when
    -- historical duplicates prevent creation of the partial unique index.
    PERFORM pg_advisory_xact_lock(hashtextextended(NEW.image_id::text, 0));

    IF EXISTS (
        SELECT 1 FROM receipts WHERE image_id = NEW.image_id AND id <> NEW.id
    ) THEN
        RAISE EXCEPTION 'image_id % is already linked to a receipt', NEW.image_id
            USING ERRCODE = 'unique_violation';
    END IF;
    RETURN NEW;
END
$function$;
"""

DROP_IMAGE_UNIQUE_TRIGGER_SQL = "DROP TRIGGER IF EXISTS receipts_image_id_unique ON receipts;"
CREATE_IMAGE_UNIQUE_TRIGGER_SQL = """
CREATE TRIGGER receipts_image_id_unique
    BEFORE INSERT OR UPDATE OF image_id ON receipts
    FOR EACH ROW EXECUTE FUNCTION vision_bill_check_receipt_image_id();
"""

REPORTING_INDEXES_SQL = (
    """
CREATE INDEX IF NOT EXISTS ix_receipts_verified_date_currency
    ON receipts (date DESC, currency)
    WHERE status = 'verified' AND verified = TRUE;
""",
    """
CREATE INDEX IF NOT EXISTS ix_receipts_verified_merchant
    ON receipts (merchant_name, currency)
    WHERE status = 'verified' AND verified = TRUE;
""",
    """
CREATE INDEX IF NOT EXISTS ix_receipts_verified_category
    ON receipts (category, currency)
    WHERE status = 'verified' AND verified = TRUE;
""",
    """
CREATE INDEX IF NOT EXISTS ix_receipts_verified_payment
    ON receipts (payment_method, currency)
    WHERE status = 'verified' AND verified = TRUE;
""",
    """
CREATE INDEX IF NOT EXISTS ix_line_items_receipt_id
    ON line_items (receipt_id);
""",
    """
CREATE INDEX IF NOT EXISTS ix_images_status_created_at
    ON images (status, created_at);
""",
)


def upgrade() -> None:
    op.execute("ALTER TABLE images ADD COLUMN IF NOT EXISTS processing_at TIMESTAMPTZ;")
    op.execute(DROP_IMAGE_STATUS_CHECK_SQL)
    op.execute(ADD_IMAGE_STATUS_CHECK_SQL)
    op.execute(CREATE_IMAGE_UNIQUE_INDEX_SQL)
    op.execute(DROP_IMAGE_UNIQUE_TRIGGER_SQL)
    op.execute(CREATE_IMAGE_UNIQUE_FUNCTION_SQL)
    op.execute(CREATE_IMAGE_UNIQUE_TRIGGER_SQL)
    for index_sql in REPORTING_INDEXES_SQL:
        op.execute(index_sql)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_images_status_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_line_items_receipt_id;")
    op.execute("DROP INDEX IF EXISTS ix_receipts_verified_payment;")
    op.execute("DROP INDEX IF EXISTS ix_receipts_verified_category;")
    op.execute("DROP INDEX IF EXISTS ix_receipts_verified_merchant;")
    op.execute("DROP INDEX IF EXISTS ix_receipts_verified_date_currency;")
    op.execute("DROP INDEX IF EXISTS ix_receipts_image_id;")
    op.execute("DROP INDEX IF EXISTS ux_receipts_image_id;")
    op.execute("DROP TRIGGER IF EXISTS receipts_image_id_unique ON receipts;")
    op.execute("DROP FUNCTION IF EXISTS vision_bill_check_receipt_image_id();")
    op.execute("ALTER TABLE images DROP COLUMN IF EXISTS processing_at;")
    op.execute("ALTER TABLE images DROP CONSTRAINT IF EXISTS images_status_check;")
    op.execute(
        "ALTER TABLE images ADD CONSTRAINT images_status_check "
        "CHECK (status IN ('pending', 'analyzed', 'failed'));"
    )
