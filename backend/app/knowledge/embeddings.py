from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.crypto import decrypt_secret
from app.db.models import KnowledgeEmbeddingSettings
from app.logging import get_logger

VECTOR_STORAGE_DIMENSIONS = 1536
logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    provider: str
    model: str
    base_url: str | None
    dimensions: int
    batch_size: int
    api_key: str | None = None
    database_override: bool = False

    @property
    def enabled(self) -> bool:
        return self.provider in {"local", "remote"}

    @property
    def model_label(self) -> str:
        return f"{self.provider}:{self.model}:{self.dimensions}"


async def get_embedding_config(db: AsyncSession, organization_id: UUID) -> EmbeddingConfig:
    row = await db.get(KnowledgeEmbeddingSettings, organization_id)
    if row is not None:
        return EmbeddingConfig(
            provider=row.provider,
            model=row.model,
            base_url=row.base_url,
            dimensions=row.dimensions,
            batch_size=row.batch_size,
            api_key=decrypt_secret(row.api_key_enc) if row.api_key_enc else None,
            database_override=True,
        )

    settings = get_settings()
    provider = "remote" if settings.knowledge_embedding_enabled else "disabled"
    return EmbeddingConfig(
        provider=provider,
        model=settings.knowledge_embedding_model,
        base_url=settings.knowledge_embedding_base_url if provider == "remote" else None,
        dimensions=max(1, min(settings.knowledge_embedding_dimensions, VECTOR_STORAGE_DIMENSIONS)),
        batch_size=32,
        api_key=settings.knowledge_embedding_api_key or None,
    )


async def _request_embeddings(config: EmbeddingConfig, texts: Sequence[str]) -> list[list[float]]:
    if not config.base_url:
        raise ValueError("Embedding endpoint is not configured")
    headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
    body: dict = {"model": config.model, "input": list(texts)}
    # Local OpenAI-compatible endpoints often expose models with a fixed
    # output width and reject the OpenAI-specific dimensions parameter.
    if config.provider == "remote":
        body["dimensions"] = config.dimensions
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{config.base_url.rstrip('/')}/embeddings",
            headers=headers,
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    indexed = {int(item["index"]): item["embedding"] for item in payload.get("data", [])}
    if len(indexed) != len(texts):
        raise ValueError("Embedding provider returned an incomplete batch")
    return [indexed[index] for index in range(len(texts))]


def _storage_vector(vector: Sequence[float], expected_dimensions: int) -> list[float]:
    if len(vector) != expected_dimensions:
        raise ValueError(
            f"Embedding provider returned {len(vector)} dimensions; expected {expected_dimensions}"
        )
    if len(vector) > VECTOR_STORAGE_DIMENSIONS:
        raise ValueError(f"Embedding vectors cannot exceed {VECTOR_STORAGE_DIMENSIONS} dimensions")
    return [float(value) for value in vector] + [0.0] * (VECTOR_STORAGE_DIMENSIONS - len(vector))


async def embed_texts(
    db: AsyncSession,
    organization_id: UUID,
    texts: Sequence[str],
    *,
    config: EmbeddingConfig | None = None,
) -> list[list[float] | None]:
    """Embed only public canonical text using the organization's provider."""
    resolved = config or await get_embedding_config(db, organization_id)
    if not texts or not resolved.enabled:
        return [None for _ in texts]
    if resolved.provider == "remote" and not resolved.api_key:
        raise ValueError("Remote embedding API key is not configured")
    vectors = await _request_embeddings(resolved, texts)
    return [_storage_vector(vector, resolved.dimensions) for vector in vectors]


async def embed_query(db: AsyncSession, organization_id: UUID, text: str) -> list[float] | None:
    config = await get_embedding_config(db, organization_id)
    try:
        return (await embed_texts(db, organization_id, [text], config=config))[0]
    except (httpx.HTTPError, ValueError) as exc:
        # Search remains available through full-text/keyword ranking when an
        # embedding endpoint is temporarily unavailable.
        logger.warning("knowledge_query_embedding_failed", provider=config.provider, error=str(exc))
        return None
