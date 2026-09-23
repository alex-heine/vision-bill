import logging
from typing import Any

from vision_bill.model.receipt import LineItem, Receipt
from vision_bill.provider.db.receipt_db import ReceiptDB
from vision_bill.service.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class TaggingService:
    """Service for tagging receipt line items with GPC categories.

    Uses embedding similarity to find the closest General Product Classification
    category for each line item description.
    """

    SIMILARITY_THRESHOLD = 0.55
    SUGGESTION_THRESHOLD = 0.50

    def __init__(self, embedding_service: EmbeddingService, db: ReceiptDB):
        self.embedding_service = embedding_service
        self.db = db

    async def tag_line_item(self, item: LineItem, language: str = "en") -> str:
        """Tag a single line item with its closest GPC category.

        Uses the receipt language for language-appropriate GPC matching.
        Returns the GPC category title if similarity exceeds the threshold,
        otherwise returns "OTHER".
        """
        text_to_embed = item.description
        embedding = await self.embedding_service.embed_text(text_to_embed)
        suggestions = await self.db.find_gpc_suggestions(
            embedding,
            language_code=language,
            threshold=self.SIMILARITY_THRESHOLD,
            limit=1,
        )
        logger.debug("GPC suggestions for item '%s': %s", item.description, suggestions)

        if suggestions:
            return str(suggestions[0]["title"])
        return "OTHER"

    async def get_tag_suggestions(self, item: LineItem, limit: int = 10) -> list[dict[str, Any]]:
        """Get multiple GPC tag suggestions for a line item.

        Returns a list of dicts with title and similarity score for categories
        above the suggestion threshold (lower than the auto-tag threshold).
        """
        text_to_embed = item.description
        embedding = await self.embedding_service.embed_text(text_to_embed)
        return await self.db.find_gpc_suggestions(
            embedding,
            language_code="en",
            threshold=self.SUGGESTION_THRESHOLD,
            limit=limit,
        )

    async def tag_receipt(self, receipt: Receipt) -> Receipt:
        """Tag all line items in a receipt with GPC categories.

        Preserves existing tags and adds the GPC category tag if not already present.
        Uses the receipt's detected language for GPC matching.
        """
        for item in receipt.line_items:
            tag = await self.tag_line_item(item, language=receipt.language)
            # Preserve existing tags, add GPC tag if not already present
            if tag not in item.tags:
                item.tags.append(tag)
        return receipt
