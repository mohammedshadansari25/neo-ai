import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import Memory, User
from app.db.session import get_db
from app.schemas.memory import (
    MemoryCreateRequest,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResponse,
)
from app.services.embedder import embed_text
from app.services.rag import find_conflicts, hybrid_search

router = APIRouter(prefix="/api/memories", tags=["memories"])


def _serialize_memory(memory: Memory, conflicts: list[uuid.UUID] | None = None) -> MemoryResponse:
    return MemoryResponse(
        id=memory.id,
        user_id=memory.user_id,
        memory_type=memory.memory_type,
        content=memory.content,
        valid_from=memory.valid_from,
        superseded_by=memory.superseded_by,
        confidence=memory.confidence,
        metadata=memory.metadata_json,
        deleted_at=memory.deleted_at,
        created_at=memory.created_at,
        conflicts=conflicts or [],
    )


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    body: MemoryCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    embedding = await embed_text(body.content)
    memory_values = {
        "user_id": current_user.id,
        "memory_type": body.memory_type.value,
        "content": body.content,
        "embedding": embedding,
        "confidence": body.confidence,
        "metadata_json": body.metadata,
    }
    if body.valid_from is not None:
        memory_values["valid_from"] = body.valid_from
    memory = Memory(**memory_values)
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    return _serialize_memory(memory)


@router.post("/search", response_model=MemorySearchResponse)
async def search_memories(
    body: MemorySearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemorySearchResponse:
    embedding = await embed_text(body.query)
    memories = await hybrid_search(
        db=db,
        user_id=current_user.id,
        query=body.query,
        query_embedding=embedding,
        limit=body.limit,
        memory_type=body.memory_type.value if body.memory_type else None,
    )
    conflict_map = find_conflicts(memories)
    return MemorySearchResponse(
        query=body.query,
        results=[
            _serialize_memory(
                memory,
                conflicts=[
                    uuid.UUID(conflict_id)
                    for conflict_id in conflict_map.get(str(memory.id), [])
                ],
            )
            for memory in memories
        ],
    )


@router.get("", response_model=list[MemoryResponse])
async def list_memories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemoryResponse]:
    result = await db.execute(
        select(Memory)
        .where(
            Memory.user_id == current_user.id,
            Memory.superseded_by.is_(None),
            Memory.deleted_at.is_(None),
        )
        .order_by(Memory.created_at.desc())
    )
    return [_serialize_memory(memory) for memory in result.scalars().all()]


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryResponse:
    result = await db.execute(
        select(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == current_user.id,
            Memory.deleted_at.is_(None),
        )
    )
    memory = result.scalar_one_or_none()
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _serialize_memory(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == current_user.id,
            Memory.deleted_at.is_(None),
        )
    )
    memory = result.scalar_one_or_none()
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory.deleted_at = datetime.now(UTC)
    await db.commit()