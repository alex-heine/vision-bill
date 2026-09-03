"""Tests for AnalysisScheduler.process_pending with fully mocked collaborators."""

import asyncio
from collections.abc import Generator
from datetime import date as Date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from vision_bill.config import Settings
from vision_bill.model.db.image import ImageRow
from vision_bill.model.db.receipt import ReceiptRow
from vision_bill.model.receipt import Receipt
from vision_bill.provider.llm.base import ModelInfo
from vision_bill.service.analysis_scheduler import AnalysisScheduler, PendingImageResult

SchedulerContext = tuple[AnalysisScheduler, MagicMock, MagicMock, MagicMock]


def _make_receipt() -> Receipt:
    return Receipt(
        confidence=95,
        merchant_name="Test Store",
        date=Date(2024, 1, 15),
        currency="USD",
        line_items=[],
        subtotal=Decimal("10.00"),
        total=Decimal("10.00"),
    )


def _receipt_row(receipt_id: int = 7) -> ReceiptRow:
    return ReceiptRow(
        id=receipt_id,
        confidence=95,
        merchant_name="Test Store",
        date=Date(2024, 1, 15),
        subtotal=Decimal("10.00"),
        total=Decimal("10.00"),
    )


def _pending_image(image_id: int, image_path: Path, bypass_review: bool = False) -> ImageRow:
    return ImageRow(
        id=image_id, image_path=str(image_path), status="pending", bypass_review=bypass_review
    )


@pytest.fixture
def scheduler_context(settings: Settings) -> Generator[SchedulerContext, None, None]:
    """AnalysisScheduler with mocked provider, receipt service and image DB.

    No real pools are created; collaborators are plain mocks so process_pending
    can be exercised directly (start()/stop() are never called).
    """
    provider = MagicMock()
    provider.get_available_models = AsyncMock(return_value=[ModelInfo(id="test-model")])

    receipt_service = MagicMock()
    receipt_service.db_ready = True
    receipt_service.analyse_receipt_from_path = AsyncMock(return_value=_make_receipt())
    receipt_service.persist_receipt = AsyncMock(return_value=_receipt_row(7))

    image_db = MagicMock()
    image_db.is_ready = True
    image_db.list_pending_images = AsyncMock(return_value=[])
    image_db.mark_analyzed = AsyncMock()
    image_db.mark_failed = AsyncMock()
    image_db.update_image_path = AsyncMock()

    image_service = MagicMock()
    image_service.store_perm_image = MagicMock(return_value=None)

    scheduler = AnalysisScheduler(settings, provider, receipt_service, image_db, image_service)
    yield scheduler, provider, receipt_service, image_db


@pytest.mark.asyncio
async def test_unavailable_provider_keeps_queue(
    scheduler_context: SchedulerContext,
) -> None:
    """A raising provider yields no results and leaves the queue untouched."""
    scheduler, provider, _, image_db = scheduler_context
    provider.get_available_models = AsyncMock(side_effect=RuntimeError("down"))
    image_db.list_pending_images = AsyncMock(return_value=[_pending_image(11, Path("/tmp/a.png"))])

    result = await scheduler.process_pending()

    assert result == []
    image_db.list_pending_images.assert_not_awaited()
    image_db.mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_models_keeps_queue(scheduler_context: SchedulerContext) -> None:
    """An empty model list yields no results and drains nothing."""
    scheduler, provider, _, image_db = scheduler_context
    provider.get_available_models = AsyncMock(return_value=[])

    result = await scheduler.process_pending()

    assert result == []
    image_db.list_pending_images.assert_not_awaited()
    image_db.mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_success_analyzes_and_links(
    scheduler_context: SchedulerContext, tmp_path: Path
) -> None:
    """A pending image with an existing file is analyzed, persisted and marked."""
    scheduler, _, receipt_service, image_db = scheduler_context
    image_file = tmp_path / "a.png"
    image_file.write_bytes(b"image-bytes")
    image_db.list_pending_images = AsyncMock(return_value=[_pending_image(11, image_file)])
    receipt = _make_receipt()
    receipt_service.analyse_receipt_from_path = AsyncMock(return_value=receipt)

    result = await scheduler.process_pending()

    assert result == [PendingImageResult(image_id=11, status="analyzed", receipt_id=7)]
    # The configured model is unavailable, so the first available one is used.
    receipt_service.analyse_receipt_from_path.assert_awaited_once_with("test-model", image_file)
    receipt_service.persist_receipt.assert_awaited_once_with(
        receipt, image_id=11, status="unverified", verified=False
    )
    image_db.mark_analyzed.assert_awaited_once_with(11, 7)
    image_db.mark_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_bypass_review_auto_verifies(
    scheduler_context: SchedulerContext, tmp_path: Path
) -> None:
    """A bypass-reviewed image is persisted as verified and moved to permanent storage."""
    scheduler, _, receipt_service, image_db = scheduler_context
    image_file = tmp_path / "bypass.png"
    image_file.write_bytes(b"image-bytes")
    perm_file = tmp_path / "receipt_7.png"
    scheduler._image_service.store_perm_image = MagicMock(return_value=perm_file)
    image_db.list_pending_images = AsyncMock(
        return_value=[_pending_image(11, image_file, bypass_review=True)]
    )
    receipt = _make_receipt()
    receipt_service.analyse_receipt_from_path = AsyncMock(return_value=receipt)

    result = await scheduler.process_pending()

    assert result == [PendingImageResult(image_id=11, status="analyzed", receipt_id=7)]
    receipt_service.persist_receipt.assert_awaited_once_with(
        receipt, image_id=11, status="verified", verified=True
    )
    image_db.mark_analyzed.assert_awaited_once_with(11, 7)
    scheduler._image_service.store_perm_image.assert_called_once_with(image_file, 7)
    image_db.update_image_path.assert_awaited_once_with(11, str(perm_file))


@pytest.mark.asyncio
async def test_analysis_failure_marks_failed(
    scheduler_context: SchedulerContext, tmp_path: Path
) -> None:
    """A parsing/extraction failure marks the image failed with the error."""
    scheduler, _, receipt_service, image_db = scheduler_context
    image_file = tmp_path / "a.png"
    image_file.write_bytes(b"image-bytes")
    image_db.list_pending_images = AsyncMock(return_value=[_pending_image(11, image_file)])
    receipt_service.analyse_receipt_from_path = AsyncMock(side_effect=ValueError("bad json"))

    result = await scheduler.process_pending()

    assert result == [PendingImageResult(image_id=11, status="failed", error="bad json")]
    image_db.mark_failed.assert_awaited_once_with(11, "bad json")
    receipt_service.persist_receipt.assert_not_awaited()
    image_db.mark_analyzed.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_file_marks_failed(
    scheduler_context: SchedulerContext, tmp_path: Path
) -> None:
    """A queue row whose on-disk file vanished is marked failed, not analysed."""
    scheduler, _, receipt_service, image_db = scheduler_context
    missing = tmp_path / "gone.png"
    image_db.list_pending_images = AsyncMock(return_value=[_pending_image(11, missing)])

    result = await scheduler.process_pending()

    assert len(result) == 1
    assert result[0].status == "failed"
    assert "gone.png" in (result[0].error or "")
    image_db.mark_failed.assert_awaited_once()
    receipt_service.analyse_receipt_from_path.assert_not_awaited()


@pytest.mark.asyncio
async def test_model_fallback_uses_first_available(
    settings: Settings, scheduler_context: SchedulerContext, tmp_path: Path
) -> None:
    """When the configured model is absent, the first available model is used."""
    scheduler, provider, receipt_service, image_db = scheduler_context
    # Sanity guard: this only proves a fallback if the preferred model differs.
    assert settings.llm.model_name not in {"other-model", "third-model"}
    provider.get_available_models = AsyncMock(
        return_value=[ModelInfo(id="other-model"), ModelInfo(id="third-model")]
    )
    image_file = tmp_path / "a.png"
    image_file.write_bytes(b"image-bytes")
    image_db.list_pending_images = AsyncMock(return_value=[_pending_image(11, image_file)])

    result = await scheduler.process_pending()

    assert result == [PendingImageResult(image_id=11, status="analyzed", receipt_id=7)]
    receipt_service.analyse_receipt_from_path.assert_awaited_once_with("other-model", image_file)


@pytest.mark.asyncio
async def test_db_not_ready_skips_cycle(scheduler_context: SchedulerContext) -> None:
    """Without a ready receipt DB the cycle is skipped without probing the provider."""
    scheduler, provider, receipt_service, _ = scheduler_context
    receipt_service.db_ready = False

    result = await scheduler.process_pending()

    assert result == []
    provider.get_available_models.assert_not_awaited()


def test_check_interval_from_settings(scheduler_context: SchedulerContext) -> None:
    """The cycle interval comes from the worker settings section."""
    scheduler = scheduler_context[0]

    assert scheduler.check_interval_seconds == 300


@pytest.mark.asyncio
async def test_process_pending_lock_serializes(scheduler_context: SchedulerContext) -> None:
    """A second concurrent cycle waits on the lock instead of overlapping."""
    scheduler, _, _, image_db = scheduler_context
    release = asyncio.Event()
    state = {"entered": False}

    async def fake_list_pending() -> list[ImageRow]:
        if not state["entered"]:
            state["entered"] = True
            await release.wait()  # first cycle blocks while holding the lock
        return []

    image_db.list_pending_images = fake_list_pending

    first = asyncio.create_task(scheduler.process_pending())
    second = asyncio.create_task(scheduler.process_pending())

    for _ in range(100):
        if state["entered"]:
            break
        await asyncio.sleep(0)

    # The first cycle holds the lock; the second must still be waiting for it.
    assert state["entered"] is True
    assert not second.done()

    release.set()
    await asyncio.wait([first, second])

    assert (await first) == []
    assert (await second) == []


@pytest.mark.asyncio
async def test_start_stop_lifecycle(scheduler_context: SchedulerContext) -> None:
    """start() spawns a background task; a second start is a no-op; stop() clears it."""
    scheduler = scheduler_context[0]

    await scheduler.start()
    assert scheduler._task is not None
    assert not scheduler._task.done()

    await scheduler.start()  # idempotent: must not spawn a second task
    await scheduler.stop()
    assert scheduler._task is None
