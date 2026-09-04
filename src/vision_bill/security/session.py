"""Stateless HMAC-signed session tokens.

A token is ``"{user_id}.{exp}.{sig}"`` where ``exp`` is a UNIX expiry and
``sig`` is ``hmac_sha256(secret, "{user_id}.{exp}")``. No server-side session
state is stored; the cookie is self-authenticating.
"""

import hashlib
import hmac
import time
from uuid import UUID


def _sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def create_token(user_id: UUID, max_age: int, secret: str) -> str:
    """Create a signed session token for ``user_id`` valid for ``max_age`` seconds."""
    exp = int(time.time()) + max_age
    message = f"{user_id}.{exp}"
    return f"{message}.{_sign(secret, message)}"


def decode_token(token: str, secret: str) -> UUID | None:
    """Return the ``user_id`` encoded in a valid token, or ``None``.

    ``None`` is returned for a malformed token, a signature mismatch (compared
    in constant time), or an expired token.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None
    user_id_s, exp_s, sig = parts
    try:
        user_id = UUID(user_id_s)
        exp = int(exp_s)
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sign(secret, f"{user_id}.{exp}")):
        return None
    if time.time() > exp:
        return None
    return user_id
