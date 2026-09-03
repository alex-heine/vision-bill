import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..security.dependencies import get_current_user
from ..service.receipt_service import ReceiptService
from .helper.helper import get_receipt_service

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


class TagCreate(BaseModel):
    """Body for creating (or confirming) a tag in the vocabulary."""

    name: str = Field(min_length=1, max_length=100)


@router.get("")
async def list_tags(
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
) -> list[str]:
    """Return the allowed line-item tag vocabulary, ordered by name.

    This is the source of truth behind the tag <select> in the UI.
    """
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")
    return await receipt_service.list_tags()


@router.post("", response_model=None)
async def create_tag(
    body: TagCreate,
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
) -> JSONResponse:
    """Create a tag, idempotently.

    Names are normalized (trimmed, lower-cased). A tag that already exists is
    returned as-is (200); a newly created one returns 201. This lets the UI
    "promote" an LLM-suggested tag without racing a duplicate insert.
    """
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        name, created = await receipt_service.create_tag(body.name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return JSONResponse(
        status_code=201 if created else 200,
        content={"name": name, "created": created},
    )
