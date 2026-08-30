import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from ..model.db.image import ImageRow
from ..service.analysis_scheduler import AnalysisScheduler
from ..service.image_service import ImageService, UnsupportedImageTypeError
from ..service.receipt_service import ReceiptService
from .helper.helper import get_analysis_scheduler, get_image_service, get_receipt_service

logger = logging.getLogger(__name__)

router = APIRouter()

PENDING_QUEUE_WARNING = "LLM provider not available – image queued for background analysis"


def _location(image_id: int) -> str:
    """Absolute path to a single-image resource for the Location header."""
    return f"/api/v1/images/{image_id}"


@router.post("", status_code=201, response_model=None)
async def upload_image(
    receipt: UploadFile = File(...),  # noqa: B008
    model_id: str | None = None,
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
    image_service: ImageService = Depends(get_image_service),  # noqa: B008
) -> JSONResponse:
    """Create an image resource by uploading a receipt file.

    When a vision model is reachable the image is analysed synchronously, a
    receipt is persisted and a ``201`` is returned. When no model is reachable
    the image is queued as ``pending`` and a ``202`` is returned; the background
    scheduler picks it up later. Both responses carry a ``Location`` header so a
    client can poll the image and, once analysed, follow ``receipt_id`` to the
    receipt. The tmp image file is always retained so a later verify step (or a
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

    tmp_path = image_service.store_tmp_image(content)

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
            headers={"Location": _location(image_row.id)},
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

    return JSONResponse(
        status_code=201,
        headers={"Location": _location(image_row.id)},
        content={
            "image_id": image_row.id,
            "status": "analyzed",
            "receipt_id": row.id,
            "original_filename": image_row.original_filename,
            "media_type": info.media_type,
            "size_bytes": info.size_bytes,
            "image_path": image_row.image_path,
        },
    )


@router.get("")
async def list_images(
    status: str | None = Query(
        None,
        description="Comma-separated statuses to filter by, e.g. pending,failed",
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
) -> list[ImageRow]:
    """List image resources, newest first. Filter with ``?status=pending,failed``."""
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")
    statuses = [s.strip() for s in status.split(",") if s.strip()] if status else None
    return await receipt_service.list_images(status=statuses, limit=limit, offset=offset)


@router.post("/analyze")
async def analyze_pending(
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
    analysis_scheduler: AnalysisScheduler = Depends(get_analysis_scheduler),  # noqa: B008
) -> dict[str, object]:
    """Manually trigger one analysis cycle over the pending queue."""
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")
    results = await analysis_scheduler.process_pending()
    return {"results": results}


@router.get("/{image_id}")
async def get_image(
    image_id: int,
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
) -> ImageRow:
    """Fetch a single image resource by id."""
    if not receipt_service.db_ready:
        raise HTTPException(status_code=503, detail="Database not available")
    image = await receipt_service.get_image_by_id(image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return image


@router.delete("/{image_id}")
async def delete_image(
    image_id: int,
    receipt_service: ReceiptService = Depends(get_receipt_service),  # noqa: B008
    image_service: ImageService = Depends(get_image_service),  # noqa: B008
) -> dict[str, object]:
    """Remove a queued (pending or failed) image resource and its on-disk file."""
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
