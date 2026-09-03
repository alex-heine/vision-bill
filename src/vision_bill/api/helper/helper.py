# TODO: Refactor namin. helper.helper :-1:
from typing import cast

from fastapi import HTTPException, Request

from ...provider.db.user_db import UserDB
from ...service.analysis_scheduler import AnalysisScheduler
from ...service.benchmark_service import BenchmarkService
from ...service.image_service import ImageService
from ...service.receipt_service import ReceiptService


def get_receipt_service(request: Request) -> ReceiptService:
    return cast("ReceiptService", request.app.state.receipt_service)


def get_user_db(request: Request) -> UserDB:
    service = getattr(request.app.state, "user_db", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Database is unavailable")
    return cast("UserDB", service)


def get_image_service(request: Request) -> ImageService:
    return cast("ImageService", request.app.state.image_service)


def get_analysis_scheduler(request: Request) -> AnalysisScheduler:
    return cast("AnalysisScheduler", request.app.state.analysis_scheduler)


def get_benchmark_service(request: Request) -> BenchmarkService:
    service = getattr(request.app.state, "benchmark_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Database is unavailable")
    return cast("BenchmarkService", service)
