from collections.abc import Sequence

import httpx

from app.config import get_settings


async def embed_texts(texts: Sequence[str]) -> list[list[float] | None]:
    """Embed public canonical text only; callers enforce that privacy boundary."""
    settings = get_settings()
    if not texts or not settings.knowledge_embedding_enabled or not settings.knowledge_embedding_api_key:
        return [None for _ in texts]
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.knowledge_embedding_base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {settings.knowledge_embedding_api_key}"},
            json={
                "model": settings.knowledge_embedding_model,
                "input": list(texts),
                "dimensions": settings.knowledge_embedding_dimensions,
            },
        )
        response.raise_for_status()
        payload = response.json()
    by_index = {int(item["index"]): item["embedding"] for item in payload.get("data", [])}
    return [by_index.get(index) for index in range(len(texts))]


async def embed_query(text: str) -> list[float] | None:
    return (await embed_texts([text]))[0]
