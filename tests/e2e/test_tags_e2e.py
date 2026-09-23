"""E2E: the `deposit` line-item tag is seeded in the global vocabulary (migration 0005).

Requires `make e2e-up` (the e2e stack boots a fresh DB and runs `alembic upgrade head`).
"""

import pytest

from e2e.helpers import API, register_user

pytestmark = pytest.mark.e2e


def test_deposit_tag_is_in_vocabulary(http_factory) -> None:
    client, _ = register_user(http_factory, "tags")
    response = client.get(f"{API}/tags")
    assert response.status_code == 200, response.text
    tags = response.json()
    tag_names = [tag["name"] for tag in tags]
    assert "deposit" in tag_names
