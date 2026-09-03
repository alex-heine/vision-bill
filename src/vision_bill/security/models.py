"""Pydantic models for authentication.

Kept separate from the DB row models: this is the authenticated principal as
seen by the API layer, not a raw table row.
"""

from pydantic import BaseModel


class User(BaseModel):
    """An authenticated user with the resolved effective privilege.

    ``can_see_all`` is the *effective* admin-see-all privilege: ``True`` only
    when the user is an admin AND the global ``admin_can_see_all`` flag is on.
    Handlers use it to decide whether to scope data queries to this user.
    """

    id: int
    username: str
    is_admin: bool = False
    can_see_all: bool = False
