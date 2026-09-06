"""/api/v1/collections endpoint wiring (real TestClient, mocked pool + service)."""

from collections.abc import Generator
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import vision_bill.main as main_module
from vision_bill.api import images as images_api_module
from vision_bill.api.system import main as system_api_module
from vision_bill.config import Settings
from vision_bill.provider.db import image_db as image_db_module
from vision_bill.provider.db import receipt_db as receipt_db_module
from vision_bill.provider.llm.base import ModelInfo
from vision_bill.security.dependencies import get_current_user
from vision_bill.security.models import User

COLLECTIONS_URL = "/api/v1/collections"
CID = "00000000-0000-4000-8000-0000000000c1"
UID = "00000000-0000-4000-8000-00000000000a"


def _user() -> User:
    return User(id=UUID(UID), username="alice", is_admin=False, can_see_all=False)


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
            __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=None)
        )
    )
    pool.close = AsyncMock()
    return pool


def _patch_app(monkeypatch: pytest.MonkeyPatch, settings: Settings, conn: AsyncMock) -> None:
    provider = MagicMock()
    provider.check_connection = AsyncMock(return_value=True)
    provider.get_available_models = AsyncMock(return_value=[ModelInfo(id="test-model")])
    monkeypatch.setattr(main_module, "settings", settings)
    monkeypatch.setattr(images_api_module, "settings", settings)
    monkeypatch.setattr(system_api_module, "settings", settings)
    monkeypatch.setattr(main_module, "get_llm_provider", lambda cfg: provider)
    fake_asyncpg = MagicMock()
    fake_asyncpg.create_pool = AsyncMock(return_value=_make_pool(conn))
    monkeypatch.setattr(receipt_db_module, "asyncpg", fake_asyncpg)
    monkeypatch.setattr(image_db_module, "asyncpg", fake_asyncpg)


@pytest.fixture
def client_and_service(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[TestClient, MagicMock], None, None]:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"missing": False})
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    _patch_app(monkeypatch, settings, conn)
    main_module.app.dependency_overrides[get_current_user] = lambda: _user()
    svc = MagicMock()
    svc.db_ready = True
    with TestClient(main_module.app) as client:
        # After the lifespan: replace the real (pool-backed) service with a mock.
        main_module.app.state.collection_service = svc
        yield client, svc
    main_module.app.dependency_overrides.clear()


def _collection_payload(active: bool = False) -> dict:
    return {
        "id": CID,
        "name": "Berlin",
        "color": "#3B82F6",
        "start_date": None,
        "end_date": None,
        "active": active,
        "created_at": date(2026, 6, 3),
    }


def test_list_collections(client_and_service: tuple[TestClient, MagicMock]) -> None:
    client, svc = client_and_service
    svc.list_summaries = AsyncMock(return_value=[])
    r = client.get(COLLECTIONS_URL)
    assert r.status_code == 200
    assert r.json() == []
    svc.list_summaries.assert_awaited_once()


def test_create_collection_conflict(client_and_service: tuple[TestClient, MagicMock]) -> None:
    client, svc = client_and_service
    from vision_bill.service.collection_service import NameConflictError

    svc.create = AsyncMock(side_effect=NameConflictError("dup"))
    r = client.post(COLLECTIONS_URL, json={"name": "Berlin"})
    assert r.status_code == 409


def test_create_collection_bad_color(client_and_service: tuple[TestClient, MagicMock]) -> None:
    client, svc = client_and_service
    svc.create = AsyncMock(side_effect=ValueError("color must be a hex value like #RGB or #RRGGBB"))
    r = client.post(COLLECTIONS_URL, json={"name": "Berlin", "color": "red"})
    assert r.status_code == 422


def test_get_collection_not_found(client_and_service: tuple[TestClient, MagicMock]) -> None:
    client, svc = client_and_service
    svc.get_detail = AsyncMock(return_value=None)
    r = client.get(f"{COLLECTIONS_URL}/{CID}")
    assert r.status_code == 404


def test_get_active_returns_204_when_none(client_and_service: tuple[TestClient, MagicMock]) -> None:
    client, svc = client_and_service
    svc.active_collection = AsyncMock(return_value=None)
    r = client.get(f"{COLLECTIONS_URL}/active")
    assert r.status_code == 204


def test_activate_delegates(client_and_service: tuple[TestClient, MagicMock]) -> None:
    client, svc = client_and_service
    svc.activate = AsyncMock(return_value=_collection_payload(active=True))
    r = client.post(f"{COLLECTIONS_URL}/{CID}/activate")
    assert r.status_code == 200
    svc.activate.assert_awaited_once()


def test_deactivate_not_found(client_and_service: tuple[TestClient, MagicMock]) -> None:
    client, svc = client_and_service
    from vision_bill.service.collection_service import NotFoundError

    svc.deactivate = AsyncMock(side_effect=NotFoundError("nope"))
    r = client.post(f"{COLLECTIONS_URL}/{CID}/deactivate")
    assert r.status_code == 404
