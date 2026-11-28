import math
import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Memory


def _id_of(item: Any) -> Any:
    if isinstance(item, dict):
        return item.get("id")
    return getattr(item, "id", item)


def reciprocal_rank_fusion(
    vector_ranked: Sequence[Any],
    fts_ranked: Sequence[Any],
    k: int = 60,
) -> list[tuple[Any, float]]:
    scores: dict[str, float] = {}
    objects: dict[str, Any] = {}
    for rank, item in enumerate(vector_ranked, start=1):
        item_id = _id_of(item)
        key = str(item_id)
        objects[key] = item
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    for rank, item in enumerate(fts_ranked, start=1):
        item_id = _id_of(item)
        key = str(item_id)
        objects[key] = item
        scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return [(objects[key], score) for key, score in sorted(scores.items(), key=lambda pair: -pair[1])]


def rrf(
    vector_ranked: Sequence[Any],
    fts_ranked: Sequence[Any],
    k: int = 60,
) -> list[tuple[Any, float]]:
    return reciprocal_rank_fusion(vector_ranked, fts_ranked, k)


def merge_rrf(
    vector_ranked: Sequence[Any],
    fts_ranked: Sequence[Any],
    k: int = 60,
) -> list[tuple[Any, float]]:
    return reciprocal_rank_fusion(vector_ranked, fts_ranked, k)


def deduplicate_memories(
    ranked: Iterable[Any],
    threshold: float | None = None,
) -> list[Any]:
    return deduplicate(ranked, threshold)


def detect_conflicts(
    ranked: Iterable[Any],
    threshold: float | None = None,
) -> dict[str, list[str]]:
    return find_conflicts(ranked, threshold)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def deduplicate(
    ranked: Iterable[Any],
    threshold: float | None = None,
) -> list[Any]:
    settings = get_settings()
    cutoff = settings.DEDUP_SIMILARITY_THRESHOLD if threshold is None else threshold
    kept: list[Any] = []
    for item in ranked:
        embedding = getattr(item, "embedding", None)
        if embedding is None and isinstance(item, dict):
            embedding = item.get("embedding")
        duplicate = False
        for existing in kept:
            existing_embedding = getattr(existing, "embedding", None)
            if existing_embedding is None and isinstance(existing, dict):
                existing_embedding = existing.get("embedding")
            if (
                embedding is not None
                and existing_embedding is not None
                and cosine_similarity(embedding, existing_embedding) >= cutoff
            ):
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
    return kept


def find_conflicts(
    ranked: Iterable[Any],
    threshold: float | None = None,
) -> dict[str, list[str]]:
    settings = get_settings()
    cutoff = settings.CONFLICT_SIMILARITY_THRESHOLD if threshold is None else threshold
    items = list(ranked)
    conflicts: dict[str, list[str]] = {str(_id_of(item)): [] for item in items}
    for index, left in enumerate(items):
        left_embedding = getattr(left, "embedding", None)
        if left_embedding is None and isinstance(left, dict):
            left_embedding = left.get("embedding")
        for right in items[index + 1 :]:
            right_embedding = getattr(right, "embedding", None)
            if right_embedding is None and isinstance(right, dict):
                right_embedding = right.get("embedding")
            if (
                left_embedding is not None
                and right_embedding is not None
                and cosine_similarity(left_embedding, right_embedding) >= cutoff
            ):
                left_id = str(_id_of(left))
                right_id = str(_id_of(right))
                conflicts[left_id].append(right_id)
                conflicts[right_id].append(left_id)
    return conflicts


async def hybrid_search(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    query_embedding: Sequence[float],
    limit: int = 10,
    memory_type: str | None = None,
) -> list[Memory]:
    candidate_limit = max(limit * 5, 50)
    params: dict[str, Any] = {
        "user_id": user_id,
        "query_embedding": str(list(query_embedding)),
        "candidate_limit": candidate_limit,
    }
    active_filters = [
        "m.user_id = :user_id",
        "m.superseded_by IS NULL",
        "m.deleted_at IS NULL",
    ]
    if memory_type:
        active_filters.append("m.memory_type = :memory_type")
        params["memory_type"] = memory_type

    await db.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))

    vector_sql = text(
        f"""
        SELECT m.id
        FROM memories m
        WHERE {' AND '.join(active_filters)}
        ORDER BY m.embedding <=> CAST(:query_embedding AS vector)
        LIMIT :candidate_limit
        """
    )
    fts_sql = text(
        f"""
        SELECT m.id
        FROM memories m
        WHERE {' AND '.join(active_filters)}
          AND m.search_vector @@ plainto_tsquery('english', :query)
        ORDER BY ts_rank_cd(m.search_vector, plainto_tsquery('english', :query)) DESC
        LIMIT :candidate_limit
        """
    )
    fts_params = dict(params)
    fts_params["query"] = query

    vector_rows = (await db.execute(vector_sql, params)).mappings().all()
    fts_rows = (await db.execute(fts_sql, fts_params)).mappings().all()
    vector_ids = [row["id"] for row in vector_rows]
    fts_ids = [row["id"] for row in fts_rows]
    memory_ids = list(dict.fromkeys([*vector_ids, *fts_ids]))
    if not memory_ids:
        return []

    result = await db.execute(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.superseded_by.is_(None),
            Memory.deleted_at.is_(None),
            Memory.id.in_(memory_ids),
        )
    )
    memories = {memory.id: memory for memory in result.scalars().all()}
    vector_memories = [memories[item_id] for item_id in vector_ids if item_id in memories]
    fts_memories = [memories[item_id] for item_id in fts_ids if item_id in memories]
    fused = reciprocal_rank_fusion(vector_memories, fts_memories)
    deduplicated = deduplicate([item for item, _score in fused])
    return deduplicated[:limit]