from fastapi import APIRouter, HTTPException, UploadFile

from ..config import Settings
from ..provider.factory import get_llm_provider
from ..service.image_service import UnsupportedImageTypeError, ImageService
from ..service.receipt_service import ReceiptService

router = APIRouter()

@router.get("/")
async def compare_models_endpoint(prompt: str, models: list[str] | None = None):
    return


@router.post("/analyze-image")
async def analyze_image(model_id: str, receipt: UploadFile):
    settings = Settings()
    provider = get_llm_provider(settings.llm)

    content = await receipt.read()

    image_service = ImageService(settings)
    try:
        info = image_service.validate_and_inspect(content)
    except UnsupportedImageTypeError as e:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type: {e.detected_type}",
        )

    receipt_service = ReceiptService(settings)
    models = await receipt_service.get_available_models()

    llm_response = await receipt_service.analyse_receipt_from_model(model_id, content)

    return {
        "filename": receipt.filename,
        "media_type": info.media_type,
        "size_bytes": info.size_bytes,
        "models": models,
        "llm_response": llm_response,
    }
