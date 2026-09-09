"""Shared helpers for the e2e suite (requires `make e2e-up`)."""

import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx

API = "http://localhost:53625/api/v1"
STUB_BASE = "http://localhost:9123"


def register_user(
    http_factory: Callable[[], httpx.Client], prefix: str
) -> tuple[httpx.Client, dict[str, Any]]:
    """Register a fresh, isolated user; returns (logged-in client, user JSON)."""
    client = http_factory()
    username = f"e2e-{prefix}-{uuid.uuid4().hex[:8]}"
    response = client.post(
        f"{API}/auth/register", json={"username": username, "password": "e2e-pw-12345"}
    )
    assert response.status_code == 201, response.text
    return client, response.json()


class Stub:
    """Thin client for the LLM stub control API (host port 9123)."""

    def __init__(self) -> None:
        self._http = httpx.Client(base_url=STUB_BASE, timeout=10.0)

    def set_mode(self, mode: str) -> None:
        response = self._http.post("/__mode", json={"mode": mode})
        assert response.status_code == 200, response.text

    def get_requests(self) -> list[dict[str, Any]]:
        response = self._http.get("/__requests")
        assert response.status_code == 200, response.text
        return response.json()["requests"]

    def close(self) -> None:
        self._http.close()


def wait_until(fn: Callable[[], Any], timeout_s: float = 30.0, interval_s: float = 0.5) -> Any:
    """Poll fn() until it returns a truthy value; returns that value or raises."""
    deadline = time.monotonic() + timeout_s
    while True:
        result = fn()
        if result:
            return result
        if time.monotonic() > deadline:
            raise AssertionError(f"wait_until timed out after {timeout_s}s")
        time.sleep(interval_s)
