from vision_bill.model.receipt import Receipt
from vision_bill.provider.db.receipt_db import ReceiptDB
from vision_bill.service.embedding_service import EmbeddingService


class TaggingService:
    """Service for tagging receipt line items with GPC categories.

    Uses embedding similarity to find the closest General Product Classification
    category for each line item description.
    """

    SIMILARITY_THRESHOLD = 0.75

    def __init__(self, embedding_service: EmbeddingService, db: ReceiptDB):
        self.embedding_service = embedding_service
        self.db = db

    async def tag_line_item(self, description: str) -> str:
        """Tag a single line item with its closest GPC category.

        Returns the GPC category title if similarity exceeds the threshold,
        otherwise returns "OTHER".
        """
        embedding = await self.embedding_service.embed_text(description)
        gpc_match = await self.db.find_closest_gpc(embedding)

        if gpc_match and gpc_match["similarity"] > self.SIMILARITY_THRESHOLD:
            return str(gpc_match["title"])
        return "OTHER"

    async def tag_receipt(self, receipt: Receipt) -> Receipt:
        """Tag all line items in a receipt with GPC categories."""
        for item in receipt.line_items:
            tag = await self.tag_line_item(item.description)
            item.tags = [tag]
        return receipt
