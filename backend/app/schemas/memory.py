from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    memory_type: MemoryType = MemoryType.SEMANTIC
    valid_from: datetime | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=10, ge=1, le=100)
    memory_type: MemoryType | None = None


class MemorySourceResponse(BaseModel):
    id: UUID
    item_id: UUID
    page_number: int | None = None
    chunk_index: int | None = None
    excerpt: str | None = None


class MemoryResponse(BaseModel):
    id: UUID
    user_id: UUID
    memory_type: MemoryType
    content: str
    valid_from: datetime
    superseded_by: UUID | None = None
    confidence: float
    metadata: dict[str, Any]
    deleted_at: datetime | None = None
    created_at: datetime
    rrf_score: float | None = None
    conflicts: list[UUID] = Field(default_factory=list)
    sources: list[MemorySourceResponse] = Field(default_factory=list)


class MemorySearchResponse(BaseModel):
    query: str
    results: list[MemoryResponse]


MemoryTypeEnum = MemoryType
MemoryCreate = MemoryCreateRequest
MemorySearch = MemorySearchRequest
MemoryResult = MemoryResponse