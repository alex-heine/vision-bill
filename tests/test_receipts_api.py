"""Endpoint wiring tests: real FastAPI app + TestClient, mocked DB and provider."""

from collections.abc import Generator
from datetime import UTC, datetime
from datetime import date as Date
from datetime import time as Time
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import vision_bill.main as main_module
from vision_bill.config import Settings
from vision_bill.model.receipt import LineItem, Receipt
from vision_bill.provider.db import image_db as image_db_module
from vision_bill.provider.db import receipt_db as receipt_db_module
from vision_bill.provider.llm.base import LLMProvider, ModelInfo

JPEG_PATH = Path(__file__).parent / "data" / "bauhaus.jpeg"
RECEIPTS_URL = "/api/v1/receipts"
IMAGES_URL = "/api/v1/images"


class ApiContext(NamedTuple):
    client: TestClient
    conn: AsyncMock
    provider: MagicMock


def _make_pool(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=None),
        )
    )
    pool.close = AsyncMock()
    return pool


def _make_provider() -> MagicMock:
    provider = MagicMock(spec=LLMProvider)
    provider.check_connection = AsyncMock(return_value=True)
    provider.get_available_models = AsyncMock(return_value=[ModelInfo(id="test-model")])
    provider.analyse_receipt_from_model = AsyncMock(return_value=_make_receipt())
    return provider


def _receipt_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": 1,
        "confidence": 88,
        "merchant_name": "Bauhaus",
        "merchant_address": "Main St 1",
        "receipt_number": "1001",
        "date": Date(2024, 1, 15),
        "time": Time(14, 30),
        "currency": "EUR",
        "subtotal": Decimal("19.98"),
        "discount_total": Decimal("0.00"),
        "tax_total": Decimal("3.80"),
        "tip": None,
        "total": Decimal("23.78"),
        "payment_method": "card",
        "status": "unverified",
        "image_id": None,
        "verified": False,
        "created_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return base


def _image_row(id: int = 11, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": id,
        "original_filename": "upload.jpeg",
        "media_type": "image/jpeg",
        "size_bytes": 1234,
        "image_path": None,
        "status": "pending",
        "error": None,
        "receipt_id": None,
        "created_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        "analyzed_at": None,
    }
    base.update(overrides)
    return base


def _make_receipt() -> Receipt:
    return Receipt(
        receipt_number="R-2024-0001",
        currency="EUR",
        merchant_name="ACME Corp",
        date=Date(2024, 1, 15),
        line_items=[
            LineItem(
                description="Widget",
                quantity=2,
                unit_price=Decimal("10.00"),
                total_price=Decimal("20.00"),
            )
        ],
        subtotal=Decimal("20.00"),
        total=Decimal("20.00"),
        confidence=95,
    )


def _patch_app(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    conn: AsyncMock,
    provider: MagicMock,
    db_down: bool = False,
) -> None:
    """Patch settings, provider factory, and asyncpg used by the DB providers."""
    monkeypatch.setattr(main_module, "settings", settings)
    monkeypatch.setattr(main_module, "get_llm_provider", lambda cfg: provider)

    fake_asyncpg = MagicMock()
    if db_down:
        fake_asyncpg.create_pool = AsyncMock(side_effect=RuntimeError("database unavailable"))
    else:
        fake_asyncpg.create_pool = AsyncMock(return_value=_make_pool(conn))

    monkeypatch.setattr(receipt_db_module, "asyncpg", fake_asyncpg)
    monkeypatch.setattr(image_db_module, "asyncpg", fake_asyncpg)


@pytest.fixture
def api_context(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Generator[ApiContext, None, None]:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"missing": False})
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    provider = _make_provider()
    _patch_app(monkeypatch, settings, conn, provider)

    with TestClient(main_module.app) as client:
        yield ApiContext(client=client, conn=conn, provider=provider)


@pytest.fixture
def broken_context(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Generator[ApiContext, None, None]:
    """DB pool unavailable -> endpoints return 503."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"missing": False})
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    provider = _make_provider()
    provider.check_connection = AsyncMock(return_value=False)
    _patch_app(monkeypatch, settings, conn, provider, db_down=True)

    with TestClient(main_module.app) as client:
        yield ApiContext(client=client, conn=conn, provider=provider)


def _upload_jpeg() -> tuple[str, bytes, str]:
    return ("bauhaus.jpeg", JPEG_PATH.read_bytes(), "image/jpeg")


# ── Image upload (POST /images) ────────────────────────────────────────


def test_upload_image_analyzes_and_returns_201(api_context: ApiContext, settings: Settings) -> None:
    """POST /images validates, runs the LLM, persists and keeps the tmp image."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(
        side_effect=[
            _image_row(id=11, original_filename="bauhaus.jpeg"),
            _receipt_row(id=7, image_id=11),
        ]
    )

    response = ctx.client.post(
        IMAGES_URL,
        params={"model_id": "test-model"},
        files={"receipt": _upload_jpeg()},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["image_id"] == 11
    assert body["receipt_id"] == 7
    assert body["status"] == "analyzed"
    assert body["media_type"] == "image/jpeg"
    assert body["size_bytes"] > 0
    assert body["original_filename"] == "bauhaus.jpeg"
    assert response.headers["Location"] == f"{IMAGES_URL}/11"

    tmp_files = list(Path(settings.images.tmp_dir).glob("*.png"))
    assert len(tmp_files) == 1
    ctx.provider.analyse_receipt_from_model.assert_awaited_once()
    llm_call = ctx.provider.analyse_receipt_from_model.call_args
    assert llm_call is not None
    assert llm_call.args[0] == "test-model"


def test_upload_image_rejects_non_image(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=_receipt_row())

    response = ctx.client.post(
        IMAGES_URL,
        params={"model_id": "test-model"},
        files={"receipt": ("notes.txt", b"plain text, not an image", "text/plain")},
    )

    assert response.status_code == 415
    assert "Unsupported image type" in response.json()["detail"]
    ctx.conn.fetchrow.assert_not_called()


def test_upload_image_returns_202_when_no_models(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.provider.get_available_models = AsyncMock(return_value=[])
    ctx.conn.fetchrow = AsyncMock(return_value=_image_row(id=21))

    response = ctx.client.post(
        IMAGES_URL,
        params={"model_id": "test-model"},
        files={"receipt": _upload_jpeg()},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["image_id"] == 21
    assert "warning" in body
    assert response.headers["Location"] == f"{IMAGES_URL}/21"
    ctx.provider.analyse_receipt_from_model.assert_not_awaited()


def test_upload_image_returns_202_when_provider_unreachable(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.provider.check_connection = AsyncMock(return_value=False)
    ctx.conn.fetchrow = AsyncMock(return_value=_image_row(id=31))

    response = ctx.client.post(
        IMAGES_URL,
        params={"model_id": "test-model"},
        files={"receipt": _upload_jpeg()},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["image_id"] == 31
    assert "warning" in body
    ctx.provider.get_available_models.assert_not_awaited()
    ctx.provider.analyse_receipt_from_model.assert_not_awaited()


# ── Image collection (GET /images) ─────────────────────────────────────


def test_list_images(api_context: ApiContext) -> None:
    """GET /images lists every image row (newest first)."""
    ctx = api_context
    ctx.conn.fetch = AsyncMock(
        return_value=[_image_row(id=2, status="analyzed"), _image_row(id=1, status="pending")]
    )

    response = ctx.client.get(IMAGES_URL)

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [2, 1]


def test_list_images_filtered(api_context: ApiContext) -> None:
    """GET /images?status=pending,failed is the queued-image view."""
    ctx = api_context
    ctx.conn.fetch = AsyncMock(
        return_value=[_image_row(id=1, status="pending"), _image_row(id=2, status="failed")]
    )

    response = ctx.client.get(IMAGES_URL, params={"status": "pending,failed"})

    assert response.status_code == 200
    body = response.json()
    assert [(item["id"], item["status"]) for item in body] == [(1, "pending"), (2, "failed")]


def test_get_image_by_id(api_context: ApiContext) -> None:
    """GET /images/{id} returns a single image row."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=_image_row(id=11, status="analyzed", receipt_id=7))

    response = ctx.client.get(f"{IMAGES_URL}/11")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 11
    assert body["status"] == "analyzed"
    assert body["receipt_id"] == 7


def test_get_image_by_id_not_found(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=None)

    response = ctx.client.get(f"{IMAGES_URL}/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Image not found"


# ── Image delete (DELETE /images/{id}) ─────────────────────────────────


def test_delete_image(api_context: ApiContext, settings: Settings) -> None:
    """DELETE /images/{id} removes the row and the on-disk file."""
    ctx = api_context
    tmp_file = Path(settings.images.tmp_dir) / "x.png"
    tmp_file.write_bytes(b"queued-image-bytes")
    ctx.conn.fetchrow = AsyncMock(
        return_value=_image_row(id=5, status="pending", image_path=str(tmp_file))
    )
    ctx.conn.execute = AsyncMock()

    response = ctx.client.delete(f"{IMAGES_URL}/5")

    assert response.status_code == 200
    assert response.json()["deleted"] == 5
    ctx.conn.execute.assert_awaited_once()
    assert not tmp_file.exists()


def test_delete_analyzed_image_conflict(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=_image_row(id=5, status="analyzed"))

    response = ctx.client.delete(f"{IMAGES_URL}/5")

    assert response.status_code == 409
    ctx.conn.execute.assert_not_awaited()


def test_delete_image_not_found(api_context: ApiContext) -> None:
    """DELETE /images/{id} -> 404 when no such image row exists."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=None)

    response = ctx.client.delete(f"{IMAGES_URL}/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Image not found"
    ctx.conn.execute.assert_not_awaited()


# ── Manual analysis trigger (POST /images/analyze) ─────────────────────


def test_analyze_images_manual_trigger(api_context: ApiContext) -> None:
    """POST /images/analyze runs one scheduler cycle; down provider -> no results."""
    ctx = api_context
    ctx.provider.get_available_models = AsyncMock(side_effect=RuntimeError("down"))

    response = ctx.client.post(f"{IMAGES_URL}/analyze")

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_analyze_images_success(api_context: ApiContext, tmp_path: Path) -> None:
    """POST /images/analyze analyzes a queued image whose file exists on disk."""
    ctx = api_context
    queued_file = tmp_path / "queued.png"
    queued_file.write_bytes(b"queued-image-bytes")
    ctx.conn.fetch = AsyncMock(
        return_value=[_image_row(id=11, status="pending", image_path=str(queued_file))]
    )
    # list_pending_images uses fetch (one pending row); persist_receipt uses fetchrow.
    ctx.conn.fetchrow = AsyncMock(return_value=_receipt_row(id=7, image_id=11))
    ctx.conn.execute = AsyncMock()

    response = ctx.client.post(f"{IMAGES_URL}/analyze")

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["image_id"] == 11
    assert results[0]["status"] == "analyzed"
    assert results[0]["receipt_id"] == 7
    ctx.conn.execute.assert_awaited()


# ── Receipts (GET /receipts, GET /receipts/{id}, verify) ───────────────


def test_get_receipt_not_found(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=None)

    response = ctx.client.get(f"{RECEIPTS_URL}/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Receipt not found"


def test_list_receipts(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.conn.fetch = AsyncMock(
        return_value=[
            _receipt_row(id=2, merchant_name="Store B"),
            _receipt_row(id=1, merchant_name="Store A"),
        ]
    )

    response = ctx.client.get(RECEIPTS_URL, params={"limit": 10, "offset": 0})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["merchant_name"] == "Store B"
    assert body[1]["merchant_name"] == "Store A"


def test_verify_receipt_moves_image(api_context: ApiContext, settings: Settings) -> None:
    """Verify moves the tmp image to permanent storage and flips status to verified."""
    ctx = api_context

    # Step 1: create an unverified receipt via POST /images
    ctx.conn.fetchrow = AsyncMock(
        side_effect=[
            _image_row(id=11, original_filename="bauhaus.jpeg"),
            _receipt_row(id=7, image_id=11),
        ]
    )
    analyze_response = ctx.client.post(
        IMAGES_URL,
        params={"model_id": "test-model"},
        files={"receipt": _upload_jpeg()},
    )
    assert analyze_response.status_code == 201
    receipt_id = analyze_response.json()["receipt_id"]

    tmp_files = list(Path(settings.images.tmp_dir).glob("*.png"))
    assert len(tmp_files) == 1
    tmp_path = str(tmp_files[0])

    # Step 2: verify -> fetchrow called for receipt, image, then the verified row
    ctx.conn.fetchrow = AsyncMock(
        side_effect=[
            _receipt_row(id=7, image_id=11, status="unverified"),
            _image_row(id=11, status="analyzed", receipt_id=7, image_path=tmp_path),
            _receipt_row(id=7, image_id=11, status="verified", verified=True),
        ]
    )
    ctx.conn.execute = AsyncMock()
    response = ctx.client.post(f"{RECEIPTS_URL}/{receipt_id}/verify")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "verified"
    assert body["verified"] is True

    assert list(Path(settings.images.tmp_dir).glob("*.png")) == []
    saved = Path(settings.images.save_dir) / "receipt_7.png"
    assert saved.exists()
    assert saved.read_bytes() == JPEG_PATH.read_bytes()


def test_verify_receipt_already_verified_conflict(api_context: ApiContext) -> None:
    """Verifying a receipt that is already verified -> 409, no state change."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(
        return_value=_receipt_row(id=7, image_id=11, status="verified", verified=True)
    )

    response = ctx.client.post(f"{RECEIPTS_URL}/7/verify")

    assert response.status_code == 409
    assert response.json()["detail"] == "Receipt already verified"
    ctx.conn.execute.assert_not_awaited()


def test_endpoints_return_503_when_db_not_ready(broken_context: ApiContext) -> None:
    ctx = broken_context

    upload = ctx.client.post(
        IMAGES_URL,
        params={"model_id": "test-model"},
        files={"receipt": _upload_jpeg()},
    )
    receipt_listing = ctx.client.get(RECEIPTS_URL)
    image_listing = ctx.client.get(IMAGES_URL)
    detail = ctx.client.get(f"{RECEIPTS_URL}/999")

    assert upload.status_code == 503
    assert receipt_listing.status_code == 503
    assert image_listing.status_code == 503
    assert detail.status_code == 503
    assert "Database not available" in upload.json()["detail"]
