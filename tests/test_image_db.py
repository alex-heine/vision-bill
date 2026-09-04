"""Tests for ImageDB — pool lifecycle and SQL behaviour with mocked asyncpg."""

import logging
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from vision_bill.config import Settings
from vision_bill.model.db.image import ImageRow
from vision_bill.provider.db.image_db import (
    DELETE_IMAGE_SQL,
    GET_IMAGE_SQL,
    INSERT_IMAGE_SQL,
    LIST_PENDING_IMAGES_SQL,
    MARK_ANALYZED_SQL,
    MARK_FAILED_SQL,
    UPDATE_IMAGE_PATH_SQL,
    ImageDB,
)

PATCH_TARGET = "vision_bill.provider.db.image_db.asyncpg"
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000001")
OTHER_IMAGE_ID = UUID("00000000-0000-4000-8000-000000000002")
RECEIPT_ID = UUID("00000000-0000-4000-8000-000000000003")
USER_ID = UUID("00000000-0000-4000-8000-000000000004")


def _make_pool(conn: AsyncMock) -> MagicMock:
    """Build a mock pool whose acquire() yields the given conn."""
    pool = MagicMock()
    pool.acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=None),
        )
    )
    return pool


def _image_row(image_id: UUID = IMAGE_ID, **overrides: object) -> dict[str, Any]:
    """A realistic asyncpg images row (driver types, not strings)."""
    row: dict[str, Any] = {
        "id": image_id,
        "original_filename": "a.png",
        "media_type": "image/png",
        "size_bytes": 123,
        "image_path": "/tmp/a.png",
        "status": "pending",
        "error": None,
        "receipt_id": None,
        "bypass_review": False,
        "created_at": datetime(2024, 1, 15, 14, 30, tzinfo=UTC),
        "analyzed_at": None,
    }
    row.update(overrides)
    return row


@pytest.fixture
def db(settings: Settings) -> ImageDB:
    return ImageDB(settings.pg)


# ── Connection pool lifecycle tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_init_db_creates_pool(db: ImageDB, caplog: pytest.LogCaptureFixture) -> None:
    """init_db should create the pool and run the to_regclass('images') check."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"missing": False})
    mock_pool = _make_pool(mock_conn)

    with (
        patch(PATCH_TARGET) as mock_asyncpg,
        caplog.at_level(logging.INFO, logger="vision_bill.provider.db.image_db"),
    ):
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
        await db.init_db()

    mock_asyncpg.create_pool.assert_called_once()
    assert db._pool is mock_pool
    mock_conn.execute.assert_not_called()
    # The to_regclass sanity check IS executed against the acquired connection.
    mock_conn.fetchrow.assert_called_once()
    assert "to_regclass('images')" in mock_conn.fetchrow.call_args.args[0]
    # Table present -> no "schema not initialised" warning.
    assert not any("Images schema not initialised" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_init_db_warns_when_schema_missing(
    db: ImageDB, caplog: pytest.LogCaptureFixture
) -> None:
    """init_db should warn (not raise) when the images table is missing."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"missing": True})
    mock_pool = _make_pool(mock_conn)

    with (
        patch(PATCH_TARGET) as mock_asyncpg,
        caplog.at_level(logging.INFO, logger="vision_bill.provider.db.image_db"),
    ):
        mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
        await db.init_db()

    assert db._pool is mock_pool
    mock_conn.execute.assert_not_called()
    assert any("Images schema not initialised" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_destroy_db_closes_pool(db: ImageDB) -> None:
    """destroy_db should close the pool and set it to None."""
    mock_pool = MagicMock()
    mock_pool.close = AsyncMock()
    db._pool = mock_pool

    await db.destroy_db()

    mock_pool.close.assert_called_once()
    assert db._pool is None


@pytest.mark.asyncio
async def test_init_db_skips_when_already_init(db: ImageDB) -> None:
    """init_db should skip if the pool already exists."""
    db._pool = MagicMock()

    with patch(PATCH_TARGET) as mock_asyncpg:
        mock_asyncpg.create_pool = AsyncMock()
        await db.init_db()

    mock_asyncpg.create_pool.assert_not_called()


def test_pool_property_raises_when_not_init(db: ImageDB) -> None:
    """pool property should raise RuntimeError if not initialised."""
    with pytest.raises(RuntimeError, match="Image database pool not initialised"):
        _ = db.pool


# ── DML tests (mocked pool) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_store_image(db: ImageDB) -> None:
    """store_image should INSERT with the right params and map the RETURNING row."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value=_image_row(bypass_review=True))

    result = await db.store_image(
        "/tmp/a.png",
        original_filename="a.png",
        media_type="image/png",
        size_bytes=123,
        status="pending",
        user_id=USER_ID,
        bypass_review=True,
    )

    assert isinstance(result, ImageRow)
    assert result.id == IMAGE_ID
    assert result.image_path == "/tmp/a.png"
    assert result.status == "pending"
    assert result.bypass_review is True

    fetchrow_call = mock_conn.fetchrow.call_args
    assert fetchrow_call is not None
    assert fetchrow_call.args[0] == INSERT_IMAGE_SQL
    # original_filename, media_type, size_bytes, image_path ($4), status ($5),
    # user_id ($6), bypass_review ($7)
    assert fetchrow_call.args[1] == "a.png"
    assert fetchrow_call.args[2] == "image/png"
    assert fetchrow_call.args[3] == 123
    assert fetchrow_call.args[4] == "/tmp/a.png"
    assert fetchrow_call.args[5] == "pending"
    assert fetchrow_call.args[6] == USER_ID
    assert fetchrow_call.args[7] is True


@pytest.mark.asyncio
async def test_get_image_by_found(db: ImageDB) -> None:
    """get_image_by_id should return an ImageRow when found."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value=_image_row(status="analyzed"))

    result = await db.get_image_by_id(IMAGE_ID)

    assert result is not None
    assert result.id == IMAGE_ID
    assert result.status == "analyzed"

    fetchrow_call = mock_conn.fetchrow.call_args
    assert fetchrow_call is not None
    assert fetchrow_call.args[0] == GET_IMAGE_SQL
    assert fetchrow_call.args[1] == IMAGE_ID


@pytest.mark.asyncio
async def test_get_image_by_not_found(db: ImageDB) -> None:
    """get_image_by_id should return None when the image doesn't exist."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetchrow = AsyncMock(return_value=None)

    result = await db.get_image_by_id(OTHER_IMAGE_ID)

    assert result is None


@pytest.mark.asyncio
async def test_list_pending_images(db: ImageDB) -> None:
    """list_pending_images should select the pending/failed queue and map rows."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.fetch = AsyncMock(
        return_value=[
            _image_row(image_id=IMAGE_ID, status="pending"),
            _image_row(image_id=OTHER_IMAGE_ID, status="failed"),
        ]
    )

    results = await db.list_pending_images()

    assert [row.id for row in results] == [IMAGE_ID, OTHER_IMAGE_ID]
    assert [row.status for row in results] == ["pending", "failed"]

    fetch_call = mock_conn.fetch.call_args
    assert fetch_call is not None
    assert fetch_call.args[0] == LIST_PENDING_IMAGES_SQL
    assert "status IN ('pending', 'failed')" in fetch_call.args[0]


@pytest.mark.asyncio
async def test_mark_analyzed(db: ImageDB) -> None:
    """mark_analyzed should UPDATE status='analyzed' and bind (id, receipt_id)."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.execute = AsyncMock()

    await db.mark_analyzed(IMAGE_ID, RECEIPT_ID)

    mock_conn.execute.assert_awaited_once_with(MARK_ANALYZED_SQL, IMAGE_ID, RECEIPT_ID)
    assert "status = 'analyzed'" in MARK_ANALYZED_SQL
    assert "receipt_id = $2" in MARK_ANALYZED_SQL


@pytest.mark.asyncio
async def test_mark_failed(db: ImageDB) -> None:
    """mark_failed should UPDATE status='failed' and bind (id, error)."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.execute = AsyncMock()

    await db.mark_failed(IMAGE_ID, "boom")

    mock_conn.execute.assert_awaited_once_with(MARK_FAILED_SQL, IMAGE_ID, "boom")
    assert "status = 'failed'" in MARK_FAILED_SQL
    assert "error = $2" in MARK_FAILED_SQL


@pytest.mark.asyncio
async def test_update_image_path(db: ImageDB) -> None:
    """update_image_path should bind (id, new path)."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.execute = AsyncMock()

    await db.update_image_path(IMAGE_ID, "/save/receipt.png")

    mock_conn.execute.assert_awaited_once_with(UPDATE_IMAGE_PATH_SQL, IMAGE_ID, "/save/receipt.png")
    assert "image_path = $2" in UPDATE_IMAGE_PATH_SQL


@pytest.mark.asyncio
async def test_delete_image(db: ImageDB) -> None:
    """delete_image should DELETE by id."""
    mock_conn = AsyncMock()
    db._pool = _make_pool(mock_conn)
    mock_conn.execute = AsyncMock()

    await db.delete_image(IMAGE_ID)

    mock_conn.execute.assert_awaited_once_with(DELETE_IMAGE_SQL, IMAGE_ID)
    assert "DELETE FROM images" in DELETE_IMAGE_SQL
