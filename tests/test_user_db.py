"""Tests for UserDB — pool lifecycle and SQL behaviour with mocked asyncpg."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from vision_bill.config import Settings
from vision_bill.provider.db.user_db import (
    COUNT_USERS_SQL,
    CREATE_USER_SQL,
    SET_ORPHAN_OWNER_IMAGES_SQL,
    SET_ORPHAN_OWNER_RECEIPTS_SQL,
    UserDB,
)
from vision_bill.security import hash_password, verify_password
from vision_bill.security.models import User

PATCH_TARGET = "vision_bill.provider.db.user_db.asyncpg"


def _make_pool(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=None),
        )
    )
    return pool


def _user_row(user_id: int = 1, username: str = "alice", is_admin: bool = False) -> dict[str, Any]:
    return {
        "id": user_id,
        "username": username,
        "hashed_password": "$argon2id$some-hash",
        "is_admin": is_admin,
    }


@pytest.fixture
def db(settings: Settings) -> UserDB:
    return UserDB(settings.pg)


@pytest.mark.asyncio
async def test_user_create_fetch_verify_round_trip(db: UserDB, settings: Settings) -> None:
    """create_user -> get_user_by_username -> verify_password all line up."""
    conn = AsyncMock()
    db._pool = _make_pool(conn)
    auth = settings.auth
    hashed = hash_password("s3cret-pw", auth)

    conn.fetchrow = AsyncMock(return_value=_user_row(username="alice", is_admin=True))
    created = await db.create_user("alice", hashed, is_admin=True)
    assert created.id == 1
    assert created.username == "alice"
    assert created.is_admin is True
    assert conn.fetchrow.await_args.args[0] == CREATE_USER_SQL
    # The peppered Argon2id hash must never be exposed on the User model.
    assert "hashed_password" not in User.model_fields

    conn.fetchrow = AsyncMock(return_value=_user_row(username="alice", is_admin=True))
    fetched = await db.get_user_by_username("alice")
    assert fetched is not None
    assert fetched.username == "alice"

    assert verify_password(hashed, "s3cret-pw", auth) is True
    assert verify_password(hashed, "wrong", auth) is False


@pytest.mark.asyncio
async def test_get_user_by_username_not_found(db: UserDB) -> None:
    conn = AsyncMock()
    db._pool = _make_pool(conn)
    conn.fetchrow = AsyncMock(return_value=None)
    assert await db.get_user_by_username("nobody") is None


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(db: UserDB) -> None:
    conn = AsyncMock()
    db._pool = _make_pool(conn)
    conn.fetchrow = AsyncMock(return_value=None)
    assert await db.get_user_by_id(999) is None


@pytest.mark.asyncio
async def test_count_users(db: UserDB) -> None:
    conn = AsyncMock()
    db._pool = _make_pool(conn)
    conn.fetchrow = AsyncMock(return_value={"count": 3})
    assert await db.count_users() == 3
    fetch_call = conn.fetchrow.await_args
    assert fetch_call is not None
    assert fetch_call.args[0] == COUNT_USERS_SQL


@pytest.mark.asyncio
async def test_set_owner_of_orphan_rows(db: UserDB) -> None:
    """Legacy rows with no owner are assigned to the given user (both tables)."""
    conn = AsyncMock()
    db._pool = _make_pool(conn)
    conn.execute = AsyncMock()
    await db.set_owner_of_orphan_rows(5)
    executed = [call.args for call in conn.execute.call_args_list]
    assert (SET_ORPHAN_OWNER_RECEIPTS_SQL, 5) in executed
    assert (SET_ORPHAN_OWNER_IMAGES_SQL, 5) in executed
