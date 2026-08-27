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
from vision_bill.model.receipt import LineItem, Receipt, TaxLine
from vision_bill.provider.llm.base import LLMProvider, ModelInfo

JPEG_PATH = Path(__file__).parent / "data" / "bauhaus.jpeg"
RECEIPTS_URL = "/api/v1/receipts"


class ApiContext(NamedTuple):
    client: TestClient
    conn: AsyncMock
    provider: MagicMock


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


def _make_provider() -> MagicMock:
    provider = MagicMock(spec=LLMProvider)
    provider.get_available_models = AsyncMock(return_value=[ModelInfo(id="test-model")])
    provider.analyse_receipt_from_model = AsyncMock(return_value=_make_receipt())
    return provider


def _receipt_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": 7,
        "confidence": 95,
        "merchant_name": "Bauhaus",
        "merchant_address": "Musterstr. 1",
        "receipt_number": "B-1",
        "date": Date(2024, 1, 15),
        "time": Time(14, 30),
        "currency": "EUR",
        "subtotal": Decimal("50.00"),
        "discount_total": Decimal("0.00"),
        "tax_total": Decimal("4.50"),
        "tip": None,
        "total": Decimal("54.50"),
        "payment_method": "card",
        "status": "unverified",
        "image_path": None,
        "created_at": datetime(2024, 1, 15, 14, 30, tzinfo=UTC),
        "verified": False,
    }
    row.update(overrides)
    return row


def _make_receipt() -> Receipt:
    return Receipt(
        confidence=95,
        merchant_name="Bauhaus",
        merchant_address="Musterstr. 1",
        receipt_number="B-1",
        date=Date(2024, 1, 15),
        time="14:30",
        currency="EUR",
        line_items=[
            LineItem(
                description="Mug",
                quantity=1,
                unit_price=Decimal("10.00"),
                total_price=Decimal("10.00"),
            )
        ],
        taxes=[TaxLine(name="VAT", rate=0.19, amount=Decimal("1.90"))],
        subtotal=Decimal("10.00"),
        discount_total=Decimal(0),
        tax_total=Decimal("1.90"),
        total=Decimal("11.90"),
        payment_method="credit_card",
    )


def _patch_app(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    conn: AsyncMock,
    provider: MagicMock,
    db_down: bool,
) -> None:
    monkeypatch.setattr(main_module, "settings", settings)
    monkeypatch.setattr(main_module, "get_llm_provider", MagicMock(return_value=provider))

    mock_asyncpg = MagicMock()
    if db_down:
        mock_asyncpg.create_pool = AsyncMock(side_effect=RuntimeError("db down"))
    else:
        mock_asyncpg.create_pool = AsyncMock(return_value=_make_pool(conn))
    monkeypatch.setattr("vision_bill.provider.db.receipt_db.asyncpg", mock_asyncpg)


@pytest.fixture
def api_context(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Generator[ApiContext, None, None]:
    conn = AsyncMock()
    conn.execute = AsyncMock()
    provider = _make_provider()
    _patch_app(settings, monkeypatch, conn, provider, db_down=False)

    with TestClient(main_module.app) as client:
        yield ApiContext(client=client, conn=conn, provider=provider)


@pytest.fixture
def broken_context(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Generator[ApiContext, None, None]:
    conn = AsyncMock()
    provider = _make_provider()
    _patch_app(settings, monkeypatch, conn, provider, db_down=True)

    with TestClient(main_module.app) as client:
        yield ApiContext(client=client, conn=conn, provider=provider)


def _upload_jpeg() -> tuple[str, bytes, str]:
    return ("bauhaus.jpeg", JPEG_PATH.read_bytes(), "image/jpeg")


def test_analyze_image_persists_and_returns_receipt_id(
    api_context: ApiContext, settings: Settings
) -> None:
    """analyze-image validates, runs the LLM, persists and keeps the tmp image."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=_receipt_row())

    response = ctx.client.post(
        f"{RECEIPTS_URL}/analyze-image",
        params={"model_id": "test-model"},
        files={"receipt": _upload_jpeg()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["receipt_id"] == 7
    assert body["status"] == "unverified"
    assert body["verified"] is False
    assert body["filename"] == "bauhaus.jpeg"
    assert body["media_type"] == "image/jpeg"
    assert body["size_bytes"] > 0
    assert len(body["models"]) == 1
    assert body["llm_response"]["merchant_name"] == "Bauhaus"

    # The tmp image must survive for the later verify step
    tmp_files = list(Path(settings.images.tmp_dir).glob("*.png"))
    assert len(tmp_files) == 1
    ctx.provider.analyse_receipt_from_model.assert_awaited_once()
    llm_call = ctx.provider.analyse_receipt_from_model.call_args
    assert llm_call is not None
    assert llm_call.args[0] == "test-model"


def test_analyze_image_rejects_non_image(api_context: ApiContext) -> None:
    """Non-image uploads are rejected with 415 before touching the DB."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=_receipt_row())

    response = ctx.client.post(
        f"{RECEIPTS_URL}/analyze-image",
        params={"model_id": "test-model"},
        files={"receipt": ("notes.txt", b"plain text, not an image", "text/plain")},
    )

    assert response.status_code == 415
    assert "Unsupported image type" in response.json()["detail"]
    ctx.conn.fetchrow.assert_not_called()


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

    response = ctx.client.get(f"{RECEIPTS_URL}/list", params={"limit": 10, "offset": 0})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["merchant_name"] == "Store B"
    assert body[1]["merchant_name"] == "Store A"


def test_verify_receipt_moves_image(api_context: ApiContext, settings: Settings) -> None:
    """verify marks the receipt verified and moves the tmp image to the save dir."""
    ctx = api_context

    # Step 1: create an unverified receipt via analyze-image
    ctx.conn.fetchrow = AsyncMock(return_value=_receipt_row())
    analyze_response = ctx.client.post(
        f"{RECEIPTS_URL}/analyze-image",
        params={"model_id": "test-model"},
        files={"receipt": _upload_jpeg()},
    )
    assert analyze_response.status_code == 200
    receipt_id = analyze_response.json()["receipt_id"]

    tmp_files = list(Path(settings.images.tmp_dir).glob("*.png"))
    assert len(tmp_files) == 1
    tmp_path = str(tmp_files[0])

    # Step 2: verify it
    ctx.conn.fetchrow = AsyncMock(
        side_effect=[
            _receipt_row(image_path=tmp_path),
            _receipt_row(
                status="verified",
                verified=True,
                image_path=f"{settings.images.save_dir}/receipt_7.png",
            ),
        ]
    )
    response = ctx.client.post(f"{RECEIPTS_URL}/{receipt_id}/verify")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "verified"
    assert body["verified"] is True
    assert body["image_path"] == f"{settings.images.save_dir}/receipt_7.png"

    # The image was moved: tmp dir empty, save dir has the file
    assert list(Path(settings.images.tmp_dir).glob("*.png")) == []
    saved = Path(settings.images.save_dir) / "receipt_7.png"
    assert saved.exists()
    assert saved.read_bytes() == JPEG_PATH.read_bytes()


def test_endpoints_return_503_when_db_not_ready(broken_context: ApiContext) -> None:
    """If the pool failed to initialise at startup, endpoints answer 503."""
    ctx = broken_context

    analyze = ctx.client.post(
        f"{RECEIPTS_URL}/analyze-image",
        params={"model_id": "test-model"},
        files={"receipt": _upload_jpeg()},
    )
    listing = ctx.client.get(f"{RECEIPTS_URL}/list")
    detail = ctx.client.get(f"{RECEIPTS_URL}/999")

    assert analyze.status_code == 503
    assert listing.status_code == 503
    assert detail.status_code == 503
    assert "Database not available" in analyze.json()["detail"]
