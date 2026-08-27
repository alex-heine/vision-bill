# TODO: Refactor namin. helper.helper :-1:
from typing import cast

from fastapi import Request

from ...service.image_service import ImageService
from ...service.receipt_service import ReceiptService


def get_receipt_service(request: Request) -> ReceiptService:
    return cast("ReceiptService", request.app.state.receipt_service)


def get_image_service(request: Request) -> ImageService:
    return cast("ImageService", request.app.state.image_service)
