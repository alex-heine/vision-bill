"""FastAPI dependencies that resolve the authenticated user.

``get_current_user`` turns the signed session cookie into a :class:`User`;
``require_admin`` gates admin-only (see-all) routes.
"""

from fastapi import Depends, HTTPException, Request

from ..api.helper.helper import get_user_db
from ..config import settings
from .models import User
from .session import decode_token

_UNAUTHENTICATED = HTTPException(status_code=401, detail="Not authenticated")


async def get_current_user(request: Request) -> User:
    """Resolve the authenticated user from the session cookie.

    Reads the signed session cookie, decodes it, loads the user, and derives
    the effective ``can_see_all`` privilege. Raises ``401`` on any failure
    (missing/invalid/expired cookie or unknown user) and ``503`` when the user
    store is unavailable.
    """
    user_db = get_user_db(request)
    if not user_db.is_ready:
        raise HTTPException(status_code=503, detail="Authentication is unavailable")

    token = request.cookies.get(settings.auth.session_cookie_name)
    if not token:
        raise _UNAUTHENTICATED

    user_id = decode_token(token, settings.auth.secret_key)
    if user_id is None:
        raise _UNAUTHENTICATED

    user = await user_db.get_user_by_id(user_id)
    if user is None:
        raise _UNAUTHENTICATED

    user.can_see_all = user.is_admin and settings.auth.admin_can_see_all
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:  # noqa: B008
    """Allow only users with the effective see-all (admin) privilege; else 403."""
    if not user.can_see_all:
        raise HTTPException(status_code=403, detail="Administrator privileges required")
    return user
