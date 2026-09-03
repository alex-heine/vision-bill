import logging
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from ..model.db.receipt import ReceiptRow, ReceiptWithDetails
from ..model.receipt import Receipt
from ..security.dependencies import get_current_user
from ..service.image_service import ImageService
from ..service.receipt_service import ReceiptReferencedError, ReceiptService
from .helper.helper import get_image_service, get_receipt_service

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("")
async def list_receipts(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(
        None, description="Comma-separated statuses, e.g. unverified,verified"
    ),
    date_from: date | None = Query(  # noqa: B008
        None, description="Only receipts dated on or after this date"
    ),
    date_to: date | None = Query(  # noqa: B008
        None, description="Only receipts dated on or before this date"
    ),
    search: str | None = Query(
        None, description="Case-insensitive match on merchant name or receipt number"
    ),
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
) -> list[ReceiptRow]:
    """List persisted receipts (the collection resource).

    Optional filters: ``status`` (comma-separated), an inclusive
    ``date_from``/``date_to`` range, and ``search`` over merchant name or
    receipt number.
    """
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return await receipt_service.list_receipts(
        limit=limit,
        offset=offset,
        status=statuses,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )


@router.get("/{receipt_id}")
async def get_receipt(
    receipt_id: int,
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
) -> ReceiptWithDetails:
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")
    details = await receipt_service.get_receipt_with_details(receipt_id)
    if details is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return details


@router.put("/{receipt_id}")
async def update_receipt(
    receipt_id: int,
    receipt: Receipt,
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
) -> ReceiptRow:
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")
    row = await receipt_service.update_receipt(receipt_id, receipt)
    if row is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return row


@router.post("/{receipt_id}/verify")
async def verify_receipt(
    receipt_id: int,
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
    image_service: ImageService = Depends(get_image_service),  # noqa: B008
) -> ReceiptRow:
    """Verify a receipt, moving its image from tmp to permanent storage.

    Flow: receipt -> image row -> store_perm_image -> update_image_path ->
    verify_receipt. The path now lives on the images row, not the receipt.
    """
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await receipt_service.get_receipt_by_id(receipt_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Receipt not found")

    if row.status == "verified":
        raise HTTPException(status_code=409, detail="Receipt already verified")

    if row.image_id is not None:
        image = await receipt_service.get_image_by_id(row.image_id)
        if image is not None and image.image_path:
            new_path = image_service.store_perm_image(Path(image.image_path), receipt_id)
            if new_path is not None:
                await receipt_service.update_image_path(row.image_id, str(new_path))

    verified = await receipt_service.verify_receipt(receipt_id)
    if verified is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return verified


@router.delete("/{receipt_id}")
async def delete_receipt(
    receipt_id: int,
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
    image_service: ImageService = Depends(get_image_service),  # noqa: B008
) -> dict[str, object]:
    """Delete a receipt (its line items and taxes cascade) plus its stored image."""
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        row = await receipt_service.delete_receipt(receipt_id)
    except ReceiptReferencedError:
        raise HTTPException(
            status_code=409,
            detail="Receipt is referenced by a benchmark run and cannot be deleted",
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Receipt not found")

    if row.image_id is not None:
        image = await receipt_service.get_image_by_id(row.image_id)
        if image is not None:
            await receipt_service.delete_image_row(image.id)
            if image.image_path:
                image_service.delete_image(Path(image.image_path))
    return {"deleted": receipt_id}
