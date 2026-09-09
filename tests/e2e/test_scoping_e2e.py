"""Multi-user isolation + admin see-all over live HTTP."""

import pytest

from e2e.discovery import first_case
from e2e.helpers import API, register_user, wait_until

pytestmark = pytest.mark.e2e


def _receipt_id_for(client) -> str:
    case = first_case()
    assert case is not None, "no e2e fixtures registered"
    with case.image_path.open("rb") as fh:
        response = client.post(
            f"{API}/images", files={"receipt": (case.image_path.name, fh, "image/png")}
        )
    assert response.status_code in (201, 202)
    image_id = response.json()["image_id"]

    def check():
        client.post(f"{API}/images/analyze")
        row = client.get(f"{API}/images/{image_id}").json()
        return row["receipt_id"] if row["status"] == "analyzed" else None

    return wait_until(check, timeout_s=60.0)


def test_users_cannot_see_each_others_data(http_factory) -> None:
    alice, _ = register_user(http_factory, "scope-a")
    bob, _ = register_user(http_factory, "scope-b")
    alice_receipt = _receipt_id_for(alice)

    # Bob cannot read or list Alice's receipt.
    assert bob.get(f"{API}/receipts/{alice_receipt}").status_code == 404
    bob_list = bob.get(f"{API}/receipts").json()
    assert all(r["id"] != alice_receipt for r in bob_list)

    # Bob cannot verify or delete Alice's receipt.
    assert bob.post(f"{API}/receipts/{alice_receipt}/verify").status_code == 404
    assert bob.delete(f"{API}/receipts/{alice_receipt}").status_code == 404

    # Alice still owns it.
    assert alice.get(f"{API}/receipts/{alice_receipt}").status_code == 200


def test_admin_sees_all(http_factory) -> None:
    carol, _ = register_user(http_factory, "scope-c")
    carol_receipt = _receipt_id_for(carol)

    admin = http_factory()
    login = admin.post(
        f"{API}/auth/login", json={"username": "admin", "password": "admin-e2e-pass"}
    )
    assert login.status_code == 200
    admin_list = admin.get(f"{API}/receipts").json()
    assert any(r["id"] == carol_receipt for r in admin_list)
    assert admin.get(f"{API}/receipts/{carol_receipt}").status_code == 200
