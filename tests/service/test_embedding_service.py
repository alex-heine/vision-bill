import pytest
from vision_bill.service.embedding_service import EmbeddingService


@pytest.mark.asyncio
async def test_embed_text_returns_vector():
    service = EmbeddingService("http://localhost:11434")
    embedding = await service.embed_text("test text")
    assert isinstance(embedding, list)
    assert len(embedding) == 768  # nomic-embed-text dimension


@pytest.mark.asyncio
async def test_embed_texts_returns_vectors():
    service = EmbeddingService("http://localhost:11434")
    embeddings = await service.embed_texts(["test 1", "test 2"])
    assert len(embeddings) == 2
    assert all(len(e) == 768 for e in embeddings)
