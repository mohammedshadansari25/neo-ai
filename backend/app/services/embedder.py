from openai import AsyncOpenAI

from app.config import get_settings


class Embedder:
    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.EMBEDDING_MODEL
        self.dimensions = settings.EMBEDDING_DIM
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def embed_text(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimensions,
        )
        embedding = response.data[0].embedding
        if len(embedding) != self.dimensions:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {self.dimensions}, got {len(embedding)}"
            )
        return embedding

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
        )
        embeddings = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        if any(len(embedding) != self.dimensions for embedding in embeddings):
            raise RuntimeError("Embedding dimension mismatch")
        return embeddings

    async def embed(self, text: str) -> list[float]:
        return await self.embed_text(text)

    async def get_embedding(self, text: str) -> list[float]:
        return await self.embed_text(text)


EmbeddingService = Embedder


_embedder: Embedder | None = None


def _get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


async def embed_text(text: str) -> list[float]:
    return await _get_embedder().embed_text(text)