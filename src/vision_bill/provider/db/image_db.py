import logging
from collections.abc import Mapping
from typing import Any

import asyncpg

from ...config import PGSettings
from ...model.db.image import ImageRow

# ── SQL (DML; DDL lives in alembic/versions/0002_images_table.py) ──

INSERT_IMAGE_SQL = """
    INSERT INTO images
        (original_filename, media_type, size_bytes, image_path, status)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING *
"""

GET_IMAGE_SQL = "SELECT * FROM images WHERE id = $1"

# The "queue": images that still need analysis (pending) or that failed and
# should be retried (failed). Oldest first so the backlog drains FIFO.
LIST_PENDING_IMAGES_SQL = (
    "SELECT * FROM images WHERE status IN ('pending', 'failed') ORDER BY created_at ASC, id ASC"
)

LIST_IMAGES_SQL = "SELECT * FROM images ORDER BY created_at DESC, id DESC LIMIT $1 OFFSET $2"

LIST_IMAGES_BY_STATUS_SQL = (
    "SELECT * FROM images WHERE status = ANY($1) ORDER BY created_at DESC, id DESC "
    "LIMIT $2 OFFSET $3"
)

MARK_ANALYZED_SQL = (
    "UPDATE images SET status = 'analyzed', receipt_id = $2, error = NULL, "
    "analyzed_at = CURRENT_TIMESTAMP WHERE id = $1"
)

MARK_FAILED_SQL = "UPDATE images SET status = 'failed', error = $2 WHERE id = $1"

UPDATE_IMAGE_PATH_SQL = "UPDATE images SET image_path = $2 WHERE id = $1"

DELETE_IMAGE_SQL = "DELETE FROM images WHERE id = $1"


logger = logging.getLogger(__name__)


class ImageDB:
    """Owns the asyncpg pool and all SQL for the images table.

    Mirrors :class:`ReceiptDB`'s pool lifecycle but manages the ``images``
    table independently so the analysis pipeline can read/write it without
    touching receipt SQL.
    """

    def __init__(self, settings: PGSettings):
        self._settings = settings
        self._pool: asyncpg.Pool | None = None

    # ── Connection pool lifecycle ────────────────────────────────────
    async def init_db(self) -> None:
        """Create the connection pool and check that the schema is migrated."""
        if self._pool is not None:
            logger.warning("Image database pool already initialised - skipping")
            return

        dsn = self._settings.pg_dsn
        logger.info("Creating asyncpg image connection pool (dsn=%s…)", dsn[:30])
        self._pool = await asyncpg.create_pool(dsn=dsn)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT to_regclass('images') IS NULL AS missing")
        if row["missing"]:
            logger.warning(
                "Images schema not initialised - run 'uv run alembic upgrade head' before starting the app"
            )

    async def destroy_db(self) -> None:
        """Close the connection pool and release all resources."""
        if self._pool is not None:
            logger.info("Closing image database connection pool")
            await self._pool.close()
            self._pool = None
            logger.info("Image database pool closed")

    @property
    def is_ready(self) -> bool:
        """Whether the connection pool has been initialised."""
        return self._pool is not None

    # ── Helpers ──────────────────────────────────────────────────────

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Image database pool not initialised. Call init_db() first.")
        return self._pool

    @staticmethod
    def _image_row_from_record(row: Mapping[str, Any]) -> ImageRow:
        """Map a raw images row to an ImageRow."""
        return ImageRow(**dict(row))

    # ── DML ──────────────────────────────────────────────────────────

    async def store_image(
        self,
        image_path: str,
        original_filename: str | None = None,
        media_type: str | None = None,
        size_bytes: int | None = None,
        status: str = "pending",
    ) -> ImageRow:
        """Insert a new images row (default status ``pending``) and return it."""
        logger.info("Storing image row for %s (status=%s)", image_path, status)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                INSERT_IMAGE_SQL,
                original_filename,
                media_type,
                size_bytes,
                image_path,
                status,
            )
        return self._image_row_from_record(row)

    async def get_image_by_id(self, image_id: int) -> ImageRow | None:
        """Fetch a single image row by its primary key."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(GET_IMAGE_SQL, image_id)
        if row is None:
            return None
        return self._image_row_from_record(row)

    async def list_pending_images(self) -> list[ImageRow]:
        """Return the analysis queue: pending and failed images, oldest first."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(LIST_PENDING_IMAGES_SQL)
        return [self._image_row_from_record(row) for row in rows]

    async def list_images(
        self,
        status: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ImageRow]:
        """List image rows (newest first), optionally filtered by status."""
        async with self.pool.acquire() as conn:
            if status:
                rows = await conn.fetch(LIST_IMAGES_BY_STATUS_SQL, status, limit, offset)
            else:
                rows = await conn.fetch(LIST_IMAGES_SQL, limit, offset)
        return [self._image_row_from_record(row) for row in rows]

    async def mark_analyzed(self, image_id: int, receipt_id: int) -> None:
        """Mark an image analyzed and link it to its receipt."""
        logger.info("Marking image %d analyzed (receipt %d)", image_id, receipt_id)
        async with self.pool.acquire() as conn:
            await conn.execute(MARK_ANALYZED_SQL, image_id, receipt_id)

    async def mark_failed(self, image_id: int, error: str) -> None:
        """Mark an image failed, recording the error for the next retry."""
        logger.warning("Marking image %d failed: %s", image_id, error)
        async with self.pool.acquire() as conn:
            await conn.execute(MARK_FAILED_SQL, image_id, error)

    async def update_image_path(self, image_id: int, image_path: str) -> None:
        """Update the on-disk path of an image (e.g. tmp -> permanent on verify)."""
        async with self.pool.acquire() as conn:
            await conn.execute(UPDATE_IMAGE_PATH_SQL, image_id, image_path)

    async def delete_image(self, image_id: int) -> None:
        """Delete an image row (the on-disk file is removed by the caller)."""
        async with self.pool.acquire() as conn:
            await conn.execute(DELETE_IMAGE_SQL, image_id)
