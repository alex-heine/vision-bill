import logging

from .api.receipts import router as receipt_router
from .api.system.llm import router as llm_router
from .api.system.main import router as system_router
from .helper.logging_config import setup_logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

setup_logging()

logger = logging.getLogger(__name__)


app = FastAPI(title="Receipt Tracker API")

# JSON API routes
app.include_router(receipt_router, prefix="/api/v1/receipts", tags=["Receipts"])
# System routes
app.include_router(system_router, prefix="/api/v1/system", tags=["System"])
# LLM routes
app.include_router(llm_router, prefix="/api/v1/llm", tags=["LLM"])

# Static frontend — mounted last so it doesn't shadow /api routes
app.mount("/", StaticFiles(directory="src/vision_bill/static", html=True), name="static")
