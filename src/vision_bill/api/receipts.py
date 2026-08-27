from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile

from ..model.db.receipt import ReceiptRow, ReceiptWithDetails
from ..model.receipt import Receipt
from ..service.image_service import ImageService, UnsupportedImageTypeError
from ..service.receipt_service import ReceiptService
from .helper.helper import get_image_service, get_receipt_service

router = APIRouter()


@router.get("/")
async def compare_models_endpoint(prompt: str, models: list[str] | None = None) -> None:
    return


@router.post("/analyze-image")
async def analyze_image(
    model_id: str,
    receipt: UploadFile,
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
    image_service: ImageService = Depends(get_image_service),  # noqa: B008
) -> dict[str, Any]:
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")

    content = await receipt.read()

    try:
        info = image_service.validate_and_inspect(content)
    except UnsupportedImageTypeError as e:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type: {e.detected_type}",
        ) from e

    models = await receipt_service.get_available_models()

    # The tmp image must survive: it is only moved to the save dir on verify
    tmp_path = image_service.store_tmp_image(content)
    llm_response = await receipt_service.analyse_receipt_from_path(model_id, tmp_path)
    row = await receipt_service.persist_receipt(llm_response, image_path=str(tmp_path))

    return {
        "filename": receipt.filename,
        "media_type": info.media_type,
        "size_bytes": info.size_bytes,
        "models": models,
        "llm_response": llm_response,
        "receipt_id": row.id,
        "status": row.status,
    }


@router.get("/list")
async def list_receipts(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
) -> list[ReceiptRow]:
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")
    return await receipt_service.list_receipts(limit=limit, offset=offset)


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
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await receipt_service.get_receipt_by_id(receipt_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Receipt not found")

    if row.status == "verified":
        raise HTTPException(status_code=409, detail="Receipt already verified")

    new_path = (
        image_service.store_perm_image(Path(row.image_path), row.id) if row.image_path else None
    )
    verified = await receipt_service.verify_receipt(
        receipt_id, str(new_path) if new_path is not None else None
    )
    if verified is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return verified
