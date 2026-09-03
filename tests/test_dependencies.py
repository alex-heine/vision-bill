"""Unit tests for the get_current_user / require_admin FastAPI dependencies."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import vision_bill.security.dependencies as deps_module
from vision_bill.config import Settings
from vision_bill.security import create_token
from vision_bill.security.dependencies import get_current_user, require_admin
from vision_bill.security.models import User


def _fake_request(token: str | None, user_db: Any, cookie_name: str) -> MagicMock:
    request = MagicMock()
    request.cookies = {} if token is None else {cookie_name: token}
    request.app.state.user_db = user_db
    return request


def _ready_user_db(user: User | None) -> MagicMock:
    user_db = MagicMock()
    user_db.is_ready = True
    user_db.get_user_by_id = AsyncMock(return_value=user)
    return user_db


@pytest.mark.asyncio
async def test_resolves_valid_cookie(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps_module, "settings", settings)
    user_db = _ready_user_db(User(id=7, username="alice", is_admin=False))
    token = create_token(7, 3600, settings.auth.secret_key)
    request = _fake_request(token, user_db, settings.auth.session_cookie_name)

    user = await get_current_user(request)

    assert user.id == 7
    assert user.username == "alice"
    user_db.get_user_by_id.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_can_see_all_derived_from_admin_and_flag(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(deps_module, "settings", settings)
    settings.auth.admin_can_see_all = True
    for is_admin, expected in [(True, True), (False, False)]:
        user_db = _ready_user_db(User(id=1, username="u", is_admin=is_admin))
        token = create_token(1, 3600, settings.auth.secret_key)
        request = _fake_request(token, user_db, settings.auth.session_cookie_name)
        user = await get_current_user(request)
        assert user.is_admin is is_admin
        assert user.can_see_all is expected


@pytest.mark.asyncio
async def test_missing_cookie_is_401(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps_module, "settings", settings)
    user_db = _ready_user_db(User(id=1, username="u"))
    request = _fake_request(None, user_db, settings.auth.session_cookie_name)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request)
    assert exc.value.status_code == 401
    user_db.get_user_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_tampered_token_is_401(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps_module, "settings", settings)
    user_db = _ready_user_db(User(id=7, username="u"))
    token = create_token(7, 3600, "a-different-secret")  # signed with the wrong secret
    request = _fake_request(token, user_db, settings.auth.session_cookie_name)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request)
    assert exc.value.status_code == 401
    user_db.get_user_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_user_is_401(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps_module, "settings", settings)
    user_db = _ready_user_db(None)  # valid token, but no such user row
    token = create_token(999, 3600, settings.auth.secret_key)
    request = _fake_request(token, user_db, settings.auth.session_cookie_name)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_user_store_down_is_503(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps_module, "settings", settings)
    user_db = MagicMock()
    user_db.is_ready = False
    token = create_token(1, 3600, settings.auth.secret_key)
    request = _fake_request(token, user_db, settings.auth.session_cookie_name)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request)
    assert exc.value.status_code == 503


def test_require_admin_blocks_without_see_all() -> None:
    with pytest.raises(HTTPException) as exc:
        require_admin(User(id=1, username="u", is_admin=False, can_see_all=False))
    assert exc.value.status_code == 403


def test_require_admin_allows_see_all() -> None:
    user = User(id=1, username="u", is_admin=True, can_see_all=True)
    assert require_admin(user) is user
