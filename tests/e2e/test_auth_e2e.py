"""Auth lifecycle over live HTTP (fresh stack, real Postgres)."""

import pytest

from e2e.helpers import API, register_user

pytestmark = pytest.mark.e2e


def test_register_login_me_logout(http_factory) -> None:
    client, user = register_user(http_factory, "auth")
    assert user["username"].startswith("e2e-auth-")
    assert user["is_admin"] is False
    assert client.cookies.get("vb_session") is not None

    me = client.get(f"{API}/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == user["username"]

    logout = client.post(f"{API}/auth/logout")
    assert logout.status_code == 200
    assert logout.json() == {"ok": True}

    me_after = client.get(f"{API}/auth/me")
    assert me_after.status_code == 401


def test_register_duplicate_conflict(http_factory) -> None:
    _, user = register_user(http_factory, "dup")
    client2 = http_factory()
    response = client2.post(
        f"{API}/auth/register",
        json={"username": user["username"], "password": "other-pw-1"},
    )
    assert response.status_code == 409
    assert "already taken" in response.json()["detail"]


def test_login_wrong_password_401(http_factory) -> None:
    _, user = register_user(http_factory, "badpw")
    client = http_factory()
    response = client.post(
        f"{API}/auth/login",
        json={"username": user["username"], "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert client.cookies.get("vb_session") is None


def test_bootstrap_admin_login(http_factory) -> None:
    client = http_factory()
    response = client.post(
        f"{API}/auth/login",
        json={"username": "admin", "password": "admin-e2e-pass"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_admin"] is True
    assert body["username"] == "admin"
