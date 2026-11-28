import math
import uuid
from types import SimpleNamespace

from app.services.rag import (
    cosine_similarity,
    deduplicate,
    find_conflicts,
    reciprocal_rank_fusion,
)


def test_reciprocal_rank_fusion_merges_and_scores():
    first = SimpleNamespace(id=uuid.uuid4())
    second = SimpleNamespace(id=uuid.uuid4())
    fused = reciprocal_rank_fusion([first, second], [second, first])

    assert len(fused) == 2
    assert {item.id for item, _score in fused} == {first.id, second.id}


def test_cosine_similarity_identical_vectors():
    assert math.isclose(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_deduplicate_removes_near_duplicates():
    first = SimpleNamespace(id=uuid.uuid4(), embedding=[1.0, 0.0])
    duplicate = SimpleNamespace(id=uuid.uuid4(), embedding=[0.99, 0.01])
    distinct = SimpleNamespace(id=uuid.uuid4(), embedding=[0.0, 1.0])

    kept = deduplicate([first, duplicate, distinct], threshold=0.92)

    assert kept == [first, distinct]


def test_find_conflicts_marks_similar_memories():
    first = SimpleNamespace(id=uuid.uuid4(), embedding=[1.0, 0.0])
    second = SimpleNamespace(id=uuid.uuid4(), embedding=[0.8, 0.6])

    conflicts = find_conflicts([first, second], threshold=0.78)

    assert str(second.id) in conflicts[str(first.id)]
    assert str(first.id) in conflicts[str(second.id)]