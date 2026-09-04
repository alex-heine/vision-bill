"""Endpoint wiring tests: real FastAPI app + TestClient, mocked DB and provider."""

from collections.abc import Generator
from datetime import UTC, datetime
from datetime import date as Date
from datetime import time as Time
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import asyncpg
import pytest
from fastapi.testclient import TestClient

import vision_bill.main as main_module
from vision_bill.api import images as images_api_module
from vision_bill.api.system import main as system_api_module
from vision_bill.config import Settings
from vision_bill.model.receipt import LineItem, Receipt
from vision_bill.provider.db import image_db as image_db_module
from vision_bill.provider.db import receipt_db as receipt_db_module
from vision_bill.provider.llm.base import LLMProvider, ModelInfo
from vision_bill.security.dependencies import get_current_user
from vision_bill.security.models import User

JPEG_PATH = Path(__file__).parent / "data" / "bauhaus.jpeg"
RECEIPTS_URL = "/api/v1/receipts"
IMAGES_URL = "/api/v1/images"
USER_ID = UUID("00000000-0000-4000-8000-000000000001")
RECEIPT_ID = UUID("00000000-0000-4000-8000-000000000002")
OTHER_RECEIPT_ID = UUID("00000000-0000-4000-8000-000000000003")
IMAGE_ID = UUID("00000000-0000-4000-8000-000000000004")
OTHER_IMAGE_ID = UUID("00000000-0000-4000-8000-000000000005")


class ApiContext(NamedTuple):
    client: TestClient
    conn: AsyncMock
    provider: MagicMock


def _make_pool(conn: AsyncMock) -> MagicMock:
    conn.transaction = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=None),
            __aexit__=AsyncMock(return_value=None),
        )
    )
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
        "id": RECEIPT_ID,
        "confidence": 88,
        "merchant_name": "Bauhaus",
        "merchant_address": "Main St 1",
        "receipt_number": "1001",
        "date": Date(2024, 1, 15),
        "time": Time(14, 30),
        "currency": "EUR",
        "category": "other",
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


def _image_row(id: UUID = IMAGE_ID, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": id,
        "original_filename": "upload.jpeg",
        "media_type": "image/jpeg",
        "size_bytes": 1234,
        "image_path": None,
        "status": "pending",
        "error": None,
        "receipt_id": None,
        "bypass_review": False,
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
    monkeypatch.setattr(images_api_module, "settings", settings)
    monkeypatch.setattr(system_api_module, "settings", settings)
    monkeypatch.setattr(main_module, "get_llm_provider", lambda cfg: provider)

    fake_asyncpg = MagicMock()
    if db_down:
        fake_asyncpg.create_pool = AsyncMock(side_effect=RuntimeError("database unavailable"))
    else:
        fake_asyncpg.create_pool = AsyncMock(return_value=_make_pool(conn))

    monkeypatch.setattr(receipt_db_module, "asyncpg", fake_asyncpg)
    monkeypatch.setattr(image_db_module, "asyncpg", fake_asyncpg)


def _admin_user() -> User:
    # can_see_all=True keeps these (pre-scoping) assertions on the base SQL.
    return User(id=USER_ID, username="tester", is_admin=True, can_see_all=True)


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
    main_module.app.dependency_overrides[get_current_user] = _admin_user

    with TestClient(main_module.app) as client:
        yield ApiContext(client=client, conn=conn, provider=provider)
    main_module.app.dependency_overrides.clear()


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
    main_module.app.dependency_overrides[get_current_user] = _admin_user

    with TestClient(main_module.app) as client:
        yield ApiContext(client=client, conn=conn, provider=provider)
    main_module.app.dependency_overrides.clear()


def _upload_jpeg() -> tuple[str, bytes, str]:
    return ("bauhaus.jpeg", JPEG_PATH.read_bytes(), "image/jpeg")


# ── Image upload (POST /images) ────────────────────────────────────────


def test_upload_image_analyzes_and_returns_201(api_context: ApiContext, settings: Settings) -> None:
    """POST /images validates, runs the LLM, persists and keeps the tmp image."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(
        side_effect=[
            _image_row(id=IMAGE_ID, original_filename="bauhaus.jpeg"),
            _receipt_row(id=RECEIPT_ID, image_id=IMAGE_ID),
        ]
    )

    response = ctx.client.post(
        IMAGES_URL,
        params={"model_id": "test-model"},
        files={"receipt": _upload_jpeg()},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["image_id"] == str(IMAGE_ID)
    assert body["receipt_id"] == str(RECEIPT_ID)
    assert body["status"] == "analyzed"
    assert body["media_type"] == "image/jpeg"
    assert body["size_bytes"] > 0
    assert body["original_filename"] == "bauhaus.jpeg"
    assert response.headers["Location"] == f"{IMAGES_URL}/{IMAGE_ID}"

    tmp_files = list(Path(settings.images.tmp_dir).glob("*.png"))
    assert len(tmp_files) == 1
    ctx.provider.analyse_receipt_from_model.assert_awaited_once()
    llm_call = ctx.provider.analyse_receipt_from_model.call_args
    assert llm_call is not None
    assert llm_call.args[0] == "test-model"


def test_upload_image_bypass_review_verifies_and_moves(
    api_context: ApiContext, settings: Settings
) -> None:
    """POST /images?bypass_review=true persists a verified receipt and moves the image."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(
        side_effect=[
            _image_row(id=IMAGE_ID, original_filename="bauhaus.jpeg", bypass_review=True),
            _receipt_row(
                id=RECEIPT_ID, image_id=IMAGE_ID, status="verified", verified=True
            ),
        ]
    )
    ctx.conn.execute = AsyncMock()

    response = ctx.client.post(
        IMAGES_URL,
        params={"model_id": "test-model", "bypass_review": "true"},
        files={"receipt": _upload_jpeg()},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["image_id"] == str(IMAGE_ID)
    assert body["receipt_id"] == str(RECEIPT_ID)
    assert body["status"] == "analyzed"

    # The tmp file has been moved into permanent storage under the receipt id.
    assert list(Path(settings.images.tmp_dir).glob("*.png")) == []
    assert list(Path(settings.images.save_dir).glob(f"receipt_{RECEIPT_ID}*.png")) != []

    update_calls = [
        call
        for call in ctx.conn.execute.call_args_list
        if call.args and call.args[0] == image_db_module.UPDATE_IMAGE_PATH_SQL
    ]
    assert len(update_calls) == 1
    assert update_calls[0].args[1] == IMAGE_ID
    assert str(Path(settings.images.save_dir)) in update_calls[0].args[2]


def test_upload_image_uses_configured_bypass_review_default(
    api_context: ApiContext, settings: Settings
) -> None:
    """An omitted query parameter uses the configured review default."""
    settings.images.bypass_review_default = True
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(
        side_effect=[
            _image_row(id=IMAGE_ID, original_filename="bauhaus.jpeg", bypass_review=True),
            _receipt_row(
                id=RECEIPT_ID, image_id=IMAGE_ID, status="verified", verified=True
            ),
        ]
    )

    response = ctx.client.post(IMAGES_URL, files={"receipt": _upload_jpeg()})

    assert response.status_code == 201
    store_call = next(
        call
        for call in ctx.conn.fetchrow.call_args_list
        if call.args and call.args[0] == image_db_module.INSERT_IMAGE_SQL
    )
    assert store_call.args[-1] is True


def test_upload_image_explicit_false_overrides_configured_default(
    api_context: ApiContext, settings: Settings
) -> None:
    """The browser can still request manual review when the default is enabled."""
    settings.images.bypass_review_default = True
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(
        side_effect=[
            _image_row(id=IMAGE_ID, original_filename="bauhaus.jpeg"),
            _receipt_row(id=RECEIPT_ID, image_id=IMAGE_ID),
        ]
    )

    response = ctx.client.post(
        IMAGES_URL,
        params={"bypass_review": "false"},
        files={"receipt": _upload_jpeg()},
    )

    assert response.status_code == 201
    store_call = next(
        call
        for call in ctx.conn.fetchrow.call_args_list
        if call.args and call.args[0] == image_db_module.INSERT_IMAGE_SQL
    )
    assert store_call.args[-1] is False


def test_ui_config_exposes_bypass_review_default(
    api_context: ApiContext, settings: Settings
) -> None:
    settings.images.bypass_review_default = True

    response = api_context.client.get("/api/v1/system/ui-config")

    assert response.status_code == 200
    assert response.json() == {"bypass_review_default": True, "registration_open": True}


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
    ctx.conn.fetchrow = AsyncMock(return_value=_image_row(id=IMAGE_ID))

    response = ctx.client.post(
        IMAGES_URL,
        params={"model_id": "test-model"},
        files={"receipt": _upload_jpeg()},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["image_id"] == str(IMAGE_ID)
    assert "warning" in body
    assert response.headers["Location"] == f"{IMAGES_URL}/{IMAGE_ID}"
    ctx.provider.analyse_receipt_from_model.assert_not_awaited()


def test_upload_image_returns_202_when_provider_unreachable(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.provider.check_connection = AsyncMock(return_value=False)
    ctx.conn.fetchrow = AsyncMock(return_value=_image_row(id=IMAGE_ID))

    response = ctx.client.post(
        IMAGES_URL,
        params={"model_id": "test-model"},
        files={"receipt": _upload_jpeg()},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["image_id"] == str(IMAGE_ID)
    assert "warning" in body
    ctx.provider.get_available_models.assert_not_awaited()
    ctx.provider.analyse_receipt_from_model.assert_not_awaited()


# ── Image collection (GET /images) ─────────────────────────────────────


def test_list_images(api_context: ApiContext) -> None:
    """GET /images lists every image row (newest first)."""
    ctx = api_context
    ctx.conn.fetch = AsyncMock(
        return_value=[
            _image_row(id=OTHER_IMAGE_ID, status="analyzed"),
            _image_row(id=IMAGE_ID, status="pending"),
        ]
    )

    response = ctx.client.get(IMAGES_URL)

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(OTHER_IMAGE_ID), str(IMAGE_ID)]


def test_list_images_filtered(api_context: ApiContext) -> None:
    """GET /images?status=pending,failed is the queued-image view."""
    ctx = api_context
    ctx.conn.fetch = AsyncMock(
        return_value=[
            _image_row(id=IMAGE_ID, status="pending"),
            _image_row(id=OTHER_IMAGE_ID, status="failed"),
        ]
    )

    response = ctx.client.get(IMAGES_URL, params={"status": "pending,failed"})

    assert response.status_code == 200
    body = response.json()
    assert [(item["id"], item["status"]) for item in body] == [
        (str(IMAGE_ID), "pending"),
        (str(OTHER_IMAGE_ID), "failed"),
    ]


def test_get_image_by_id(api_context: ApiContext) -> None:
    """GET /images/{id} returns a single image row."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(
        return_value=_image_row(id=IMAGE_ID, status="analyzed", receipt_id=RECEIPT_ID)
    )

    response = ctx.client.get(f"{IMAGES_URL}/{IMAGE_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(IMAGE_ID)
    assert body["status"] == "analyzed"
    assert body["receipt_id"] == str(RECEIPT_ID)


def test_get_image_by_id_not_found(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=None)

    response = ctx.client.get(f"{IMAGES_URL}/{OTHER_IMAGE_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Image not found"


# ── Image file (GET /images/{id}/file) ─────────────────────────────────


def test_get_image_file_streams_bytes(api_context: ApiContext, tmp_path: Path) -> None:
    """GET /images/{id}/file streams the stored file with its media type."""
    ctx = api_context
    image_file = tmp_path / "stored.png"
    image_file.write_bytes(b"image-bytes")
    ctx.conn.fetchrow = AsyncMock(
        return_value=_image_row(
            id=IMAGE_ID, status="analyzed", image_path=str(image_file), media_type="image/png"
        )
    )

    response = ctx.client.get(f"{IMAGES_URL}/{IMAGE_ID}/file")

    assert response.status_code == 200
    assert response.content == b"image-bytes"
    assert response.headers["content-type"] == "image/png"


def test_get_image_file_not_found_when_row_missing(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=None)

    response = ctx.client.get(f"{IMAGES_URL}/{OTHER_IMAGE_ID}/file")

    assert response.status_code == 404
    assert response.json()["detail"] == "Image file not found"


def test_get_image_file_not_found_when_path_missing(api_context: ApiContext) -> None:
    """Row exists but carries no stored path -> 404."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=_image_row(id=IMAGE_ID, image_path=None))

    response = ctx.client.get(f"{IMAGES_URL}/{IMAGE_ID}/file")

    assert response.status_code == 404
    assert response.json()["detail"] == "Image file not found"


def test_get_image_file_not_found_when_file_missing(api_context: ApiContext) -> None:
    """Row points at a path that no longer exists on disk -> 404."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(
        return_value=_image_row(id=IMAGE_ID, image_path="/nonexistent/receipt.png")
    )

    response = ctx.client.get(f"{IMAGES_URL}/{IMAGE_ID}/file")

    assert response.status_code == 404
    assert response.json()["detail"] == "Image file not found"


# ── Image delete (DELETE /images/{id}) ─────────────────────────────────


def test_delete_image(api_context: ApiContext, settings: Settings) -> None:
    """DELETE /images/{id} removes the row and the on-disk file."""
    ctx = api_context
    tmp_file = Path(settings.images.tmp_dir) / "x.png"
    tmp_file.write_bytes(b"queued-image-bytes")
    ctx.conn.fetchrow = AsyncMock(
        return_value=_image_row(id=IMAGE_ID, status="pending", image_path=str(tmp_file))
    )
    ctx.conn.execute = AsyncMock()

    response = ctx.client.delete(f"{IMAGES_URL}/{IMAGE_ID}")

    assert response.status_code == 200
    assert response.json()["deleted"] == str(IMAGE_ID)
    ctx.conn.execute.assert_awaited_once()
    assert not tmp_file.exists()


def test_delete_analyzed_image_conflict(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=_image_row(id=IMAGE_ID, status="analyzed"))

    response = ctx.client.delete(f"{IMAGES_URL}/{IMAGE_ID}")

    assert response.status_code == 409
    ctx.conn.execute.assert_not_awaited()


def test_delete_image_not_found(api_context: ApiContext) -> None:
    """DELETE /images/{id} -> 404 when no such image row exists."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=None)

    response = ctx.client.delete(f"{IMAGES_URL}/{OTHER_IMAGE_ID}")

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

    # Both list_pending_images and the tag lookup for the prompt use fetch, so
    # dispatch on the SQL to keep the two from clobbering each other.
    def fetch_side_effect(sql: str, *args: object) -> list[dict[str, object]]:
        if sql == receipt_db_module.LIST_TAGS_SQL:
            return [{"name": "coffee"}, {"name": "food"}]
        return [_image_row(id=IMAGE_ID, status="pending", image_path=str(queued_file))]

    ctx.conn.fetch = AsyncMock(side_effect=fetch_side_effect)
    # list_pending_images uses fetch (one pending row); persist_receipt uses fetchrow.
    ctx.conn.fetchrow = AsyncMock(
        return_value=_receipt_row(id=RECEIPT_ID, image_id=IMAGE_ID)
    )
    ctx.conn.execute = AsyncMock()

    response = ctx.client.post(f"{IMAGES_URL}/analyze")

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["image_id"] == str(IMAGE_ID)
    assert results[0]["status"] == "analyzed"
    assert results[0]["receipt_id"] == str(RECEIPT_ID)
    ctx.conn.execute.assert_awaited()
    # The tag vocabulary was passed into the extraction prompt.
    llm_call = ctx.provider.analyse_receipt_from_model.call_args
    assert llm_call is not None
    assert llm_call.kwargs.get("tags") == ["coffee", "food"]


# ── Tags (GET /tags, POST /tags) ──────────────────────────────────────

TAGS_URL = "/api/v1/tags"


def test_list_tags_endpoint(api_context: ApiContext) -> None:
    """GET /tags returns the vocabulary, ordered by name."""
    ctx = api_context
    ctx.conn.fetch = AsyncMock(return_value=[{"name": "coffee"}, {"name": "food"}])

    response = ctx.client.get(TAGS_URL)

    assert response.status_code == 200
    assert response.json() == ["coffee", "food"]


def test_create_tag_endpoint_new(api_context: ApiContext) -> None:
    """POST /tags creates a tag (201) and returns the normalized name."""
    ctx = api_context
    # create_tag issues INSERT ... RETURNING name via fetchrow.
    ctx.conn.fetchrow = AsyncMock(return_value={"name": "hot drink"})

    response = ctx.client.post(
        TAGS_URL, json={"name": "  Hot   Drink "}, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 201
    assert response.json() == {"name": "hot drink", "created": True}
    insert_call = ctx.conn.fetchrow.await_args
    assert insert_call is not None
    assert insert_call.args[0] == receipt_db_module.INSERT_TAG_SQL
    assert insert_call.args[1] == "hot drink"


def test_create_tag_endpoint_existing_is_idempotent(api_context: ApiContext) -> None:
    """POST /tags for a known name is a no-op (200, created=false), not an error.

    ON CONFLICT DO NOTHING yields no RETURNING row, which the service maps to
    created=False.
    """
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=None)

    response = ctx.client.post(TAGS_URL, json={"name": "coffee"})

    assert response.status_code == 200
    assert response.json() == {"name": "coffee", "created": False}


def test_create_tag_endpoint_blank_rejected(api_context: ApiContext) -> None:
    """A blank name is a 422 and never reaches the DB."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock()

    response = ctx.client.post(TAGS_URL, json={"name": "   "})

    assert response.status_code == 422
    assert "must not be blank" in response.json()["detail"]
    ctx.conn.fetchrow.assert_not_awaited()


def test_update_receipt_accepts_suggested_tags(api_context: ApiContext) -> None:
    """PUT /receipts/{id} stores tags that are not yet in the vocabulary.

    LLM-suggested tags must persist (the UI marks them for review); only the
    model normalizes them, it does not reject them.
    """
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(
        return_value=_receipt_row(id=RECEIPT_ID, merchant_name="ACME")
    )
    ctx.conn.execute = AsyncMock()

    body = {
        "confidence": 95,
        "merchant_name": "ACME",
        "date": "2024-01-15",
        "line_items": [
            {"description": "Widget", "quantity": 1, "unit_price": "10.00", "total_price": "10.00"}
        ],
        "subtotal": "10.00",
        "total": "10.00",
    }
    body["line_items"][0]["tags"] = ["brunch", "  Brunch  ", ""]

    response = ctx.client.put(
        f"{RECEIPTS_URL}/{RECEIPT_ID}",
        json=body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    insert_calls = [
        call
        for call in ctx.conn.execute.call_args_list
        if call.args and call.args[0] == receipt_db_module.INSERT_LINE_ITEM_SQL
    ]
    assert len(insert_calls) == 1
    # The last bound parameter is the tags array: normalized + deduped.
    assert insert_calls[0].args[-1] == ["brunch"]


# ── Receipts (GET /receipts, GET /receipts/{id}, verify) ───────────────


def test_get_receipt_not_found(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=None)

    response = ctx.client.get(f"{RECEIPTS_URL}/{OTHER_RECEIPT_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Receipt not found"


def test_list_receipts(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.conn.fetch = AsyncMock(
        return_value=[
            _receipt_row(id=OTHER_RECEIPT_ID, merchant_name="Store B"),
            _receipt_row(id=RECEIPT_ID, merchant_name="Store A"),
        ]
    )

    response = ctx.client.get(RECEIPTS_URL, params={"limit": 10, "offset": 0})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["merchant_name"] == "Store B"
    assert body[1]["merchant_name"] == "Store A"


def test_list_receipts_without_filters_keeps_base_sql(api_context: ApiContext) -> None:
    """No filters -> plain paged query, no WHERE clause."""
    ctx = api_context
    ctx.conn.fetch = AsyncMock(return_value=[])

    response = ctx.client.get(RECEIPTS_URL)

    assert response.status_code == 200
    fetch_call = ctx.conn.fetch.await_args
    assert fetch_call is not None
    sql = fetch_call.args[0]
    assert sql == "SELECT * FROM receipts ORDER BY date DESC LIMIT $1 OFFSET $2"
    assert fetch_call.args[1] == 50
    assert fetch_call.args[2] == 0


def test_list_receipts_passes_filters_to_db(api_context: ApiContext) -> None:
    """Status, date range and search are forwarded to the DB query."""
    ctx = api_context
    ctx.conn.fetch = AsyncMock(return_value=[])

    response = ctx.client.get(
        RECEIPTS_URL,
        params={
            "status": "verified",
            "date_from": "2024-01-01",
            "date_to": "2024-12-31",
            "search": "acme",
            "limit": 10,
            "offset": 5,
        },
    )

    assert response.status_code == 200
    assert response.json() == []

    fetch_call = ctx.conn.fetch.await_args
    assert fetch_call is not None
    sql = fetch_call.args[0]
    assert "status = ANY($1)" in sql
    assert "date >= $2" in sql
    assert "date <= $3" in sql
    assert "merchant_name ILIKE $4" in sql
    assert "receipt_number ILIKE $4" in sql
    assert "ORDER BY date DESC LIMIT $5 OFFSET $6" in sql
    args = fetch_call.args[1:]
    assert args[0] == ["verified"]
    assert args[1] == Date(2024, 1, 1)
    assert args[2] == Date(2024, 12, 31)
    assert args[3] == "%acme%"
    assert args[4] == 10
    assert args[5] == 5


def test_verify_receipt_moves_image(api_context: ApiContext, settings: Settings) -> None:
    """Verify moves the tmp image to permanent storage and flips status to verified."""
    ctx = api_context

    # Step 1: create an unverified receipt via POST /images
    ctx.conn.fetchrow = AsyncMock(
        side_effect=[
            _image_row(id=IMAGE_ID, original_filename="bauhaus.jpeg"),
            _receipt_row(id=RECEIPT_ID, image_id=IMAGE_ID),
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
            _receipt_row(id=RECEIPT_ID, image_id=IMAGE_ID, status="unverified"),
            _image_row(
                id=IMAGE_ID,
                status="analyzed",
                receipt_id=RECEIPT_ID,
                image_path=tmp_path,
            ),
            _receipt_row(
                id=RECEIPT_ID, image_id=IMAGE_ID, status="verified", verified=True
            ),
        ]
    )
    ctx.conn.execute = AsyncMock()
    response = ctx.client.post(f"{RECEIPTS_URL}/{receipt_id}/verify")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "verified"
    assert body["verified"] is True

    assert list(Path(settings.images.tmp_dir).glob("*.png")) == []
    saved = Path(settings.images.save_dir) / f"receipt_{RECEIPT_ID}.png"
    assert saved.exists()
    assert saved.read_bytes() == JPEG_PATH.read_bytes()


def test_verify_receipt_already_verified_conflict(api_context: ApiContext) -> None:
    """Verifying a receipt that is already verified -> 409, no state change."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(
        return_value=_receipt_row(
            id=RECEIPT_ID, image_id=IMAGE_ID, status="verified", verified=True
        )
    )

    response = ctx.client.post(f"{RECEIPTS_URL}/{RECEIPT_ID}/verify")

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
    detail = ctx.client.get(f"{RECEIPTS_URL}/{OTHER_RECEIPT_ID}")
    image_file = ctx.client.get(f"{IMAGES_URL}/{IMAGE_ID}/file")
    tag_listing = ctx.client.get(TAGS_URL)
    tag_create = ctx.client.post(TAGS_URL, json={"name": "coffee"})

    assert upload.status_code == 503
    assert receipt_listing.status_code == 503
    assert image_listing.status_code == 503
    assert detail.status_code == 503
    assert image_file.status_code == 503
    assert tag_listing.status_code == 503
    assert tag_create.status_code == 503
    assert "Database not available" in upload.json()["detail"]


# ── Receipt delete (DELETE /receipts/{id}) ────────────────────────────


def test_delete_receipt(api_context: ApiContext, settings: Settings) -> None:
    """DELETE /receipts/{id} removes the row, its image row and the on-disk file."""
    ctx = api_context
    tmp_file = Path(settings.images.tmp_dir) / "img.png"
    tmp_file.write_bytes(b"receipt-image-bytes")
    ctx.conn.fetchrow = AsyncMock(
        side_effect=[
            _receipt_row(id=RECEIPT_ID, image_id=IMAGE_ID, merchant_name="Doomed Store"),
            _image_row(
                id=IMAGE_ID,
                status="analyzed",
                receipt_id=RECEIPT_ID,
                image_path=str(tmp_file),
            ),
        ]
    )
    ctx.conn.execute = AsyncMock()

    response = ctx.client.delete(f"{RECEIPTS_URL}/{RECEIPT_ID}")

    assert response.status_code == 200
    assert response.json()["deleted"] == str(RECEIPT_ID)
    executed = [call.args[0] for call in ctx.conn.execute.call_args_list]
    assert image_db_module.DELETE_IMAGE_SQL in executed
    assert not tmp_file.exists()


def test_delete_receipt_not_found(api_context: ApiContext) -> None:
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(return_value=None)

    response = ctx.client.delete(f"{RECEIPTS_URL}/{OTHER_RECEIPT_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Receipt not found"
    ctx.conn.execute.assert_not_awaited()


def test_delete_receipt_referenced_conflict(api_context: ApiContext) -> None:
    """A receipt still referenced by a benchmark run cannot be deleted -> 409."""
    ctx = api_context
    ctx.conn.fetchrow = AsyncMock(side_effect=asyncpg.ForeignKeyViolationError("fk"))

    response = ctx.client.delete(f"{RECEIPTS_URL}/{RECEIPT_ID}")

    assert response.status_code == 409
    assert "benchmark" in response.json()["detail"]
    ctx.conn.execute.assert_not_awaited()
