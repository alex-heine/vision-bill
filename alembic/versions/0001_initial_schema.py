"""Initial application schema.

Revision ID: 0001
Revises:
Create Date: 2026-08-27 00:50:00.000000

This project has no prior production schema, so this migration defines the
complete current database structure. Each statement is executed separately
because SQLAlchemy's asyncpg dialect prepares one statement per execution.
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
    confidence      SMALLINT        NOT NULL DEFAULT 0,
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
    verified        BOOLEAN         NOT NULL DEFAULT FALSE,
    category        VARCHAR(50)     NOT NULL DEFAULT 'other',
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
    category    VARCHAR(50)     NOT NULL DEFAULT 'other',
    tags        TEXT[]          NOT NULL DEFAULT '{}'
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
    bypass_review     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    analyzed_at       TIMESTAMP WITH TIME ZONE
);
"""

ADD_RECEIPT_IMAGE_ID_SQL = (
    "ALTER TABLE receipts ADD COLUMN image_id "
    "INT REFERENCES images(id) ON DELETE SET NULL;"
)

CREATE_BENCHMARK_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS benchmark_runs (
    id SERIAL PRIMARY KEY,
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    model_ids JSONB NOT NULL,
    receipt_ids JSONB NOT NULL,
    dataset_fingerprint TEXT NOT NULL,
    model_digests JSONB NOT NULL DEFAULT '{}',
    prompt_version TEXT NOT NULL,
    scoring_version TEXT NOT NULL,
    request_timeout_seconds INTEGER NOT NULL DEFAULT 300,
    council_policy VARCHAR(20) NOT NULL DEFAULT 'all',
    council_absolute_threshold NUMERIC,
    council_relative_threshold NUMERIC,
    apply_council_flags BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
"""

CREATE_BENCHMARK_TASKS_SQL = """
CREATE TABLE IF NOT EXISTS benchmark_tasks (
    run_id INTEGER NOT NULL REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    receipt_id INTEGER NOT NULL REFERENCES receipts(id),
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 0,
    leased_until TIMESTAMPTZ,
    retry_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    PRIMARY KEY (run_id, model_id, receipt_id)
);
"""

CREATE_BENCHMARK_SUMMARIES_SQL = """
CREATE TABLE IF NOT EXISTS benchmark_summaries (
    run_id INTEGER NOT NULL REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    model_digest TEXT,
    completed INTEGER NOT NULL DEFAULT 0,
    succeeded INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    total_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_attempts INTEGER NOT NULL DEFAULT 0,
    total_latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    council_candidates INTEGER NOT NULL DEFAULT 0,
    council_findings INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, model_id)
);
"""


def upgrade() -> None:
    op.execute(CREATE_RECEIPTS_SQL)
    op.execute(CREATE_LINE_ITEMS_SQL)
    op.execute(CREATE_TAXES_SQL)
    op.execute(CREATE_IMAGES_SQL)
    op.execute(ADD_RECEIPT_IMAGE_ID_SQL)
    op.execute(CREATE_BENCHMARK_RUNS_SQL)
    op.execute(CREATE_BENCHMARK_TASKS_SQL)
    op.execute(CREATE_BENCHMARK_SUMMARIES_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS benchmark_summaries;")
    op.execute("DROP TABLE IF EXISTS benchmark_tasks;")
    op.execute("DROP TABLE IF EXISTS benchmark_runs;")
    op.execute("DROP TABLE IF EXISTS images;")
    # Children first (FKs), then the parent table.
    op.execute("DROP TABLE IF EXISTS taxes;")
    op.execute("DROP TABLE IF EXISTS line_items;")
    op.execute("DROP TABLE IF EXISTS receipts;")
