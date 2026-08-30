import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from ..model.db.image import ImageRow
from ..model.db.receipt import ReceiptRow, ReceiptWithDetails
from ..model.receipt import Receipt
from ..service.analysis_scheduler import AnalysisScheduler
from ..service.image_service import ImageService, UnsupportedImageTypeError
from ..service.receipt_service import ReceiptService
from .helper.helper import get_analysis_scheduler, get_image_service, get_receipt_service

logger = logging.getLogger(__name__)

router = APIRouter()

PENDING_QUEUE_WARNING = "LLM provider not available – image queued for background analysis"


@router.get("/")
async def compare_models_endpoint(prompt: str, models: list[str] | None = None) -> None:
    return


# response_model=None: the endpoint returns either a plain dict or a JSONResponse
@router.post("/analyze-image", response_model=None)
async def analyze_image(
    receipt: UploadFile,
    model_id: str | None = None,
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
    image_service: ImageService = Depends(get_image_service),  # noqa: B008
) -> dict[str, Any] | JSONResponse:
    """Validate and store an image, then analyse it.

    When a vision model is reachable the image is analysed synchronously and a
    receipt is persisted. When no model is reachable the image is queued as
    ``pending`` and a 202 is returned; the background scheduler picks it up
    later. The tmp image file is always retained so the verify step (or a
    background retry) can still find it.
    """
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

    # The tmp image must survive: it is only moved to the save dir on verify.
    tmp_path = image_service.store_tmp_image(content)

    # Probe the provider to decide between synchronous analysis and queuing.
    if await receipt_service.check_connection():
        models = await receipt_service.get_available_models()
    else:
        logger.warning("LLM provider unreachable - queueing image for background analysis")
        models = []
    provider_available = bool(models)

    image_row = await receipt_service.store_image(
        image_path=str(tmp_path),
        original_filename=receipt.filename,
        media_type=info.media_type,
        size_bytes=info.size_bytes,
        status="pending",
    )

    if not provider_available:
        return JSONResponse(
            status_code=202,
            content={
                "image_id": image_row.id,
                "status": "pending",
                "warning": PENDING_QUEUE_WARNING,
            },
        )

    available_ids = {m.id for m in models}
    chosen_model = model_id if (model_id and model_id in available_ids) else models[0].id
    llm_response = await receipt_service.analyse_receipt_from_path(chosen_model, tmp_path)
    row = await receipt_service.persist_receipt(
        llm_response, image_id=image_row.id, status="unverified"
    )
    await receipt_service.mark_image_analyzed(image_row.id, row.id)

    return {
        "filename": receipt.filename,
        "media_type": info.media_type,
        "size_bytes": info.size_bytes,
        "image_id": image_row.id,
        "models": models,
        "prompt": Receipt.model_json_schema(),
        "llm_response": llm_response,
        "receipt_id": row.id,
        "status": row.status,
        "verified": row.verified,
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


@router.get("/pending-images")
async def list_pending_images(
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
) -> list[ImageRow]:
    """Queued TODO list: images that are pending or failed analysis."""
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")
    return await receipt_service.list_pending_images()


@router.delete("/pending-images/{image_id}")
async def delete_pending_image(
    image_id: int,
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
    image_service: ImageService = Depends(get_image_service),  # noqa: B008
) -> dict[str, Any]:
    """Remove a queued (pending or failed) image row and its on-disk file."""
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")

    image = await receipt_service.get_image_by_id(image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    if image.status not in ("pending", "failed"):
        raise HTTPException(status_code=409, detail="Only pending or failed images can be deleted")

    await receipt_service.delete_image_row(image_id)
    if image.image_path:
        image_service.delete_image(Path(image.image_path))
    return {"deleted": image_id}


@router.post("/analyze-pending")
async def analyze_pending(
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
    analysis_scheduler: AnalysisScheduler = Depends(get_analysis_scheduler),  # noqa: B008
) -> dict[str, Any]:
    """Manually trigger one scheduler cycle and return the per-image results."""
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")
    results = await analysis_scheduler.process_pending()
    return {"results": results}


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
