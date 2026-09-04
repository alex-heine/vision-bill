from fastapi import APIRouter, Depends, HTTPException, Query

from ..model.search import ProductSearchResponse
from ..security.dependencies import get_current_user
from ..security.models import User
from ..service.receipt_service import ReceiptService
from .helper.helper import get_receipt_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=ProductSearchResponse)
async def search_products(
    query: str = Query(
        ..., min_length=1, max_length=255, description="Case-insensitive product description search"
    ),
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ProductSearchResponse:
    """Search verified line-item descriptions and return price history."""
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")

    search_term = query.strip()
    if not search_term:
        raise HTTPException(status_code=422, detail="Query must not be blank")

    return await receipt_service.search_products(
        search_term,
        user_id=current_user.id,
        can_see_all=current_user.can_see_all,
    )
