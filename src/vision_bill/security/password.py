"""Argon2id password hashing with an always-on HMAC-SHA256 pepper.

The effective pepper is ``AuthSettings.pepper`` when set, otherwise the
``secret_key`` — so a pepper is always in play. The password is pre-digested
with ``hmac_sha256(pepper, password)`` before Argon2id hashing, so a leaked
hash store alone is not enough to forge a valid credential.
"""

import hashlib
import hmac

from argon2 import PasswordHasher, Type
from argon2.exceptions import Argon2Error, InvalidHashError

from ..config import AuthSettings

# Package parameters requested by the auth plan: m=64MiB, t=3, p=4.
_hasher = PasswordHasher(type=Type.ID, memory_cost=65536, time_cost=3, parallelism=4)


def effective_pepper(auth: AuthSettings) -> str:
    """The pepper in play: an explicit pepper, else the secret key."""
    return auth.pepper or auth.secret_key


def _peppered(auth: AuthSettings, password: str) -> str:
    """Pre-digest the password with the pepper (hash directly if the pepper is empty)."""
    pepper = effective_pepper(auth)
    if not pepper:
        return password
    digest = hmac.new(pepper.encode("utf-8"), password.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


def hash_password(password: str, auth: AuthSettings) -> str:
    """Hash a password for storage in the ``users`` table."""
    return _hasher.hash(_peppered(auth, password))


def verify_password(hashed: str, password: str, auth: AuthSettings) -> bool:
    """Return ``True`` when ``password`` matches ``hashed``; ``False`` otherwise.

    Any Argon2 verification error (wrong password or malformed stored hash) is
    treated as a failed credential — we fail closed rather than raise.
    """
    try:
        return _hasher.verify(hashed, _peppered(auth, password))
    except (Argon2Error, InvalidHashError):
        # VerifyMismatchError (wrong password) and InvalidHashError (malformed
        # stored hash) both mean "not a valid credential" — fail closed.
        return False


def needs_rehash(hashed: str) -> bool:
    """Whether a stored hash should be re-created with the current parameters."""
    return _hasher.check_needs_rehash(hashed)
