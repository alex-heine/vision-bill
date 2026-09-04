"""Asynchronous, restart-safe local benchmark execution."""
import asyncio
import json
import logging
from contextlib import suppress
from pathlib import Path
from typing import Any
from uuid import UUID

from ..model.benchmark import BenchmarkCreate, BenchmarkRun, BenchmarkStatus
from ..model.receipt import LineItem, Receipt, TaxLine
from ..provider.db.benchmark_db import BenchmarkDB
from ..provider.llm.base import LLMProvider
from .benchmark_scoring import PROMPT_VERSION, SCORING_VERSION, dataset_fingerprint, score_receipts
from .receipt_service import ReceiptService

logger = logging.getLogger(__name__)


class BenchmarkService:
    """Owns benchmark task execution; normal receipt/image records are read-only."""

    def __init__(self, provider: LLMProvider, receipt_service: ReceiptService):
        self._provider = provider
        self._receipts = receipt_service
        self._db = BenchmarkDB(receipt_service.pool)
        self._worker: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._worker is None:
            self._stopping.clear()
            self._worker = asyncio.create_task(self._work(), name="benchmark-worker")

    async def stop(self) -> None:
        self._stopping.set()
        if self._worker:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def create_run(self, request: BenchmarkCreate) -> BenchmarkRun:
        models = await self._provider.get_available_models()
        available = {m.id: m for m in models}
        selected_models = request.model_ids or list(available)
        if not selected_models:
            raise ValueError("No vision models are available")
        unknown = set(selected_models) - set(available)
        if unknown:
            raise ValueError(f"Selected model(s) unavailable: {', '.join(sorted(unknown))}")
        selected_ids = await self._select_receipts(request)
        if not selected_ids:
            raise ValueError("No verified receipts match the selection")
        expected = [await self._expected_receipt(receipt_id) for receipt_id in selected_ids]
        return await self._db.create_run(
            model_ids=selected_models, receipt_ids=selected_ids, fingerprint=dataset_fingerprint(expected),
            model_digests={m.id: m.digest for m in models}, timeout=request.request_timeout_seconds,
            policy=request.council_policy, absolute=request.council_absolute_threshold,
            relative=request.council_relative_threshold, apply_flags=request.apply_council_flags,
            prompt_version=PROMPT_VERSION, scoring_version=SCORING_VERSION,
        )

    async def get_status(self, run_id: UUID) -> BenchmarkStatus | None:
        run = await self._db.run(run_id)
        if not run:
            return None
        counts = await self._db.task_counts(run_id)
        return BenchmarkStatus(run=run, summaries=await self._db.summaries(run_id), **counts)

    async def list_runs(self) -> list[BenchmarkRun]:
        return await self._db.runs()

    async def reevaluate(self, run_id: UUID, receipt_id: UUID, model_id: str) -> dict[str, Any]:
        """Transient inspection: extraction and field diff are returned, never stored."""
        run = await self._db.run(run_id)
        if not run or receipt_id not in run.receipt_ids or model_id not in run.model_ids:
            raise ValueError("Receipt/model is not part of this benchmark run")
        expected, image_path = await self._expected_receipt_and_path(receipt_id)
        if not image_path or not Path(image_path).is_file():
            raise FileNotFoundError("Verified receipt image is unavailable")
        result = await self._provider.analyse_receipt_with_metadata(model_id, Path(image_path))
        actual = result.receipt
        scores = score_receipts(expected, actual)
        expected_dump, actual_dump = expected.model_dump(mode="json"), actual.model_dump(mode="json")
        diff = {key: {"expected": expected_dump[key], "actual": actual_dump[key]} for key in expected_dump if expected_dump[key] != actual_dump[key]}
        return {"receipt_id": receipt_id, "model_id": model_id, "scores": scores, "expected": expected_dump, "actual": actual_dump, "diff": diff}

    async def _select_receipts(self, request: BenchmarkCreate) -> list[UUID]:
        if request.receipt_ids is not None:
            result = []
            for receipt_id in request.receipt_ids:
                row = await self._receipts.get_receipt_by_id(receipt_id)
                if row is not None and row.verified:
                    result.append(receipt_id)
            return result
        rows = await self._receipts.list_receipts(limit=request.limit or 10_000, status=["verified"])
        return [r.id for r in rows if (request.category is None or r.category == request.category) and (request.max_source_confidence is None or r.confidence <= request.max_source_confidence)]

    async def _expected_receipt_and_path(self, receipt_id: UUID) -> tuple[Receipt, str | None]:
        details = await self._receipts.get_receipt_with_details(receipt_id)
        if details is None or not details.receipt.verified:
            raise ValueError("Benchmark data must be a verified receipt")
        r = details.receipt
        return Receipt.model_validate({"confidence": r.confidence, "merchant_name": r.merchant_name, "merchant_address": r.merchant_address, "receipt_number": r.receipt_number, "date": r.date, "time": r.time, "currency": r.currency, "category": r.category, "line_items": [LineItem.model_validate(x.model_dump()) for x in details.line_items], "taxes": [TaxLine.model_validate(x.model_dump()) for x in details.taxes], "subtotal": r.subtotal, "discount_total": r.discount_total, "tax_total": r.tax_total, "tip": r.tip, "total": r.total, "payment_method": r.payment_method}), details.image_path

    async def _expected_receipt(self, receipt_id: UUID) -> Receipt:
        return (await self._expected_receipt_and_path(receipt_id))[0]

    async def _work(self) -> None:
        while not self._stopping.is_set():
            try:
                task = await self._db.lease_task()
                if task is None:
                    await asyncio.sleep(1)
                    continue
                await self._execute(dict(task))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Benchmark worker iteration failed")
                await asyncio.sleep(5)

    async def _execute(self, task: dict[str, Any]) -> None:
        try:
            models = {m.id: m for m in await self._provider.get_available_models()}
        except Exception:  # noqa: BLE001 - provider SDK exception types vary by transport version
            await self._db.retry_task(task)
            return
        run = await self._db.run(task["run_id"])
        model = models.get(task["model_id"])
        if run is None:
            return
        expected_digest = (await self._run_digests(run)).get(task["model_id"])
        if model is None:
            await self._db.retry_task(task, waiting=True)
            return
        if expected_digest and model.digest and expected_digest != model.digest:
            await self._db.retry_task(task, waiting=True)
            return
        try:
            expected, image_path = await self._expected_receipt_and_path(task["receipt_id"])
            if not image_path or not Path(image_path).is_file():
                raise FileNotFoundError("Image missing")
            result = await asyncio.wait_for(self._provider.analyse_receipt_with_metadata(task["model_id"], Path(image_path)), timeout=await self._timeout(run))
            await self._db.finish_task(task, success=True, score=score_receipts(expected, result.receipt)["overall"], confidence=result.receipt.confidence, attempts=result.attempts, latency_ms=result.elapsed_ms)
        except (ValueError, FileNotFoundError):
            await self._db.finish_task(task, success=False)
        except Exception:
            logger.warning("Transient benchmark failure for run=%s model=%s receipt=%s", task["run_id"], task["model_id"], task["receipt_id"], exc_info=True)
            await self._db.retry_task(task)

    async def _run_digests(self, run: BenchmarkRun) -> dict[str, str | None]:
        async with self._receipts.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT model_digests FROM benchmark_runs WHERE id=$1", run.id)
        if not row:
            return {}
        value = row["model_digests"]
        return dict(json.loads(value) if isinstance(value, str) else value)

    async def _timeout(self, run: BenchmarkRun) -> int:
        async with self._receipts.pool.acquire() as conn:
            return int(await conn.fetchval("SELECT request_timeout_seconds FROM benchmark_runs WHERE id=$1", run.id))
