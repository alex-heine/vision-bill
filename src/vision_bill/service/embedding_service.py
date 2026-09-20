import hashlib
import os
from collections.abc import Sequence

from ollama import AsyncClient


class EmbeddingService:
    """Service for generating text embeddings using Ollama."""

    def __init__(self, ollama_host: str, model: str = "nomic-embed-text"):
        self.client = AsyncClient(host=ollama_host)
        self.model = model
        self.mock = os.environ.get("EMBEDDING__MOCK", "").lower() == "true"

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        if self.mock:
            return self._mock_embed(text)
        response = await self.client.embeddings(model=self.model, prompt=text)
        return list(response.embedding)

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        embeddings = []
        for text in texts:
            embedding = await self.embed_text(text)
            embeddings.append(embedding)
        return embeddings

    def _mock_embed(self, text: str) -> list[float]:
        """Generate a deterministic mock embedding based on text hash."""
        # Generate 768-dimensional embedding (same as nomic-embed-text)
        dim = 768
        embedding = [0.0] * dim
        text_bytes = text.encode("utf-8")
        for i in range(dim):
            h = hashlib.sha256(text_bytes + f"-{i}".encode()).digest()
            # Use first 4 bytes as a float in [0, 1)
            val = int.from_bytes(h[:4], "little") / 0xFFFFFFFF
            embedding[i] = (val - 0.5) * 2.0  # Scale to [-1, 1]
        return embedding
