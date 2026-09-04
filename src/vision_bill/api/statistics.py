from fastapi import APIRouter, Depends, HTTPException, Query

from ..model.statistics import ReceiptStatistics
from ..security.dependencies import get_current_user
from ..security.models import User
from ..service.receipt_service import ReceiptService
from .helper.helper import get_receipt_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=ReceiptStatistics)
async def get_statistics(
    weeks: int = Query(12, ge=1, le=52),
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> ReceiptStatistics:
    """Return verified-only spending aggregates for the current user."""
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")
    return await receipt_service.get_statistics(
        user_id=current_user.id,
        can_see_all=current_user.can_see_all,
        weeks=weeks,
    )
