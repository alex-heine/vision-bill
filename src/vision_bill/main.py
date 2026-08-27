import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.receipts import router as receipt_router
from .api.system.llm import router as llm_router
from .api.system.main import router as system_router
from .config import settings
from .helper.logging_config import setup_logging
from .provider.factory import get_llm_provider
from .service.image_service import ImageService
from .service.receipt_service import ReceiptService

setup_logging()

logger = logging.getLogger(__name__)

# ── Startup / shutdown handlers ──────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    provider = get_llm_provider(settings.llm)
    receipt_service = ReceiptService(settings.images, settings.pg, provider)
    try:
        await receipt_service.init_db()
    except Exception:
        logger.exception("Failed to initialise database - continuing without it")

    app.state.receipt_service = receipt_service
    app.state.image_service = ImageService(settings.images)

    yield

    try:
        await app.state.receipt_service.destroy_db()
    except Exception:
        logger.exception("Error while closing database pool")


app = FastAPI(title="Receipt Tracker API", lifespan=lifespan)

# JSON API routes
app.include_router(receipt_router, prefix="/api/v1/receipts", tags=["Receipts"])
# System routes
app.include_router(system_router, prefix="/api/v1/system", tags=["System"])
# LLM routes
app.include_router(llm_router, prefix="/api/v1/llm", tags=["LLM"])

# Static frontend — mounted last so it doesn't shadow /api routes
app.mount("/", StaticFiles(directory="src/vision_bill/static", html=True), name="static")
