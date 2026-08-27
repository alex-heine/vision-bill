"""Initial schema: receipts, line_items, taxes

Revision ID: 0001
Revises:
Create Date: 2026-08-27 00:50:00.000000

Baseline migration: the DDL that previously lived in
ReceiptDB.init_db() (CREATE_TABLES_SQL). Every table uses IF NOT EXISTS,
so running this on an existing dev database is a harmless no-op that just
stamps alembic_version.

Each statement is executed in its own op.execute() call: SQLAlchemy's
asyncpg dialect runs statements as prepared statements, which accept a
single SQL statement per execution.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CREATE_RECEIPTS_SQL = """
CREATE TABLE IF NOT EXISTS receipts (
    id              SERIAL PRIMARY KEY,
    merchant_name   VARCHAR(255)    NOT NULL,
    merchant_address TEXT,
    receipt_number  VARCHAR(100),
    date            DATE            NOT NULL,
    time            TIME,
    currency        VARCHAR(10)     NOT NULL DEFAULT 'USD',
    subtotal        NUMERIC(14,2)   NOT NULL DEFAULT 0,
    discount_total  NUMERIC(14,2)   NOT NULL DEFAULT 0,
    tax_total       NUMERIC(14,2)   NOT NULL DEFAULT 0,
    tip             NUMERIC(14,2),
    total           NUMERIC(14,2)   NOT NULL DEFAULT 0,
    payment_method  VARCHAR(50)     NOT NULL DEFAULT 'unknown',
    status          VARCHAR(20)     NOT NULL DEFAULT 'unverified'
                    CHECK (status IN ('unverified', 'verified')),
    image_path      TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_LINE_ITEMS_SQL = """
CREATE TABLE IF NOT EXISTS line_items (
    id          SERIAL PRIMARY KEY,
    receipt_id  INT NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    description VARCHAR(255)    NOT NULL,
    quantity    NUMERIC(10,4)   NOT NULL,
    unit_price  NUMERIC(14,2)   NOT NULL,
    total_price NUMERIC(14,2)   NOT NULL,
    category    VARCHAR(50)     NOT NULL DEFAULT 'other'
);
"""

CREATE_TAXES_SQL = """
CREATE TABLE IF NOT EXISTS taxes (
    id         SERIAL PRIMARY KEY,
    receipt_id INT NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    name       VARCHAR(100)   NOT NULL,
    rate       NUMERIC(6,4),
    amount     NUMERIC(14,2)  NOT NULL
);
"""


def upgrade() -> None:
    op.execute(CREATE_RECEIPTS_SQL)
    op.execute(CREATE_LINE_ITEMS_SQL)
    op.execute(CREATE_TAXES_SQL)


def downgrade() -> None:
    # Children first (FKs), then the parent table
    op.execute("DROP TABLE IF EXISTS taxes;")
    op.execute("DROP TABLE IF EXISTS line_items;")
    op.execute("DROP TABLE IF EXISTS receipts;")
