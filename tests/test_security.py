"""Unit tests for the pure security helpers (password hashing + session tokens).

No database is involved: these exercise the Argon2id hashing and HMAC session
token logic directly.
"""

from uuid import UUID

from vision_bill.config import AuthSettings
from vision_bill.security import (
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from vision_bill.security.password import effective_pepper

SECRET = "unit-test-secret-key"
PASSWORD = "correct horse battery staple"
USER_ID = UUID("00000000-0000-4000-8000-000000000042")
OTHER_USER_ID = UUID("00000000-0000-4000-8000-000000000043")


def _auth(secret_key: str = SECRET, pepper: str | None = None) -> AuthSettings:
    return AuthSettings(secret_key=secret_key, pepper=pepper)


# ── Password hashing ───────────────────────────────────────────────────


def test_hash_verify_round_trip() -> None:
    auth = _auth()
    hashed = hash_password(PASSWORD, auth)
    assert verify_password(hashed, PASSWORD, auth) is True


def test_verify_wrong_password_is_false() -> None:
    auth = _auth()
    hashed = hash_password(PASSWORD, auth)
    assert verify_password(hashed, "wrong-password", auth) is False


def test_verify_malformed_hash_is_false() -> None:
    auth = _auth()
    assert verify_password("not-a-valid-argon2-hash", PASSWORD, auth) is False


def test_hash_is_not_the_raw_password() -> None:
    auth = _auth()
    hashed = hash_password(PASSWORD, auth)
    assert hashed != PASSWORD
    assert PASSWORD not in hashed


def test_pepper_changes_the_hash() -> None:
    # The effective pepper is the explicit pepper, else the secret key.
    pepper_a = _auth(pepper="pepper-a")
    pepper_b = _auth(pepper="pepper-b")
    plain = _auth()  # falls back to the secret key as the pepper

    hashed_a = hash_password(PASSWORD, pepper_a)
    hashed_b = hash_password(PASSWORD, pepper_b)
    hashed_plain = hash_password(PASSWORD, plain)

    assert hashed_a != hashed_b  # different peppers -> different digests
    assert verify_password(hashed_a, PASSWORD, pepper_a) is True
    # Verifying with a different pepper fails (the pre-digest differs).
    assert verify_password(hashed_a, PASSWORD, pepper_b) is False
    # The no-explicit-pepper case uses the secret key, distinct from both.
    assert hashed_plain != hashed_a
    assert verify_password(hashed_plain, PASSWORD, plain) is True


def test_effective_pepper_falls_back_to_secret_key() -> None:
    assert effective_pepper(_auth()) == SECRET
    assert effective_pepper(_auth(pepper="explicit")) == "explicit"


def test_needs_rehash_false_for_current_parameters() -> None:
    auth = _auth()
    hashed = hash_password(PASSWORD, auth)
    assert needs_rehash(hashed) is False


# ── Session tokens ─────────────────────────────────────────────────────


def test_token_round_trip() -> None:
    token = create_token(USER_ID, 3600, SECRET)
    assert decode_token(token, SECRET) == USER_ID


def test_token_rejects_wrong_secret() -> None:
    token = create_token(USER_ID, 3600, SECRET)
    assert decode_token(token, "a-different-secret") is None


def test_token_rejects_tampered_user_id() -> None:
    token = create_token(USER_ID, 3600, SECRET)
    user_id_s, exp_s, sig = token.split(".")
    forged = f"{OTHER_USER_ID}.{exp_s}.{sig}"
    assert decode_token(forged, SECRET) is None


def test_token_rejects_tampered_signature() -> None:
    token = create_token(USER_ID, 3600, SECRET)
    user_id_s, exp_s, _sig = token.split(".")
    forged = f"{user_id_s}.{exp_s}." + ("0" * 64)
    assert decode_token(forged, SECRET) is None


def test_token_rejects_expired() -> None:
    token = create_token(USER_ID, -1, SECRET)  # expiry in the past
    assert decode_token(token, SECRET) is None


def test_token_rejects_malformed() -> None:
    assert decode_token("", SECRET) is None
    assert decode_token("only.two", SECRET) is None
    assert decode_token("not.a.uuid", SECRET) is None
