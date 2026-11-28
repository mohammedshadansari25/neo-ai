"""Add memory embedding validation.

Revision ID: 0002_memory_embedding_trigger
Revises: 0001_initial_schema
"""

from collections.abc import Sequence

from alembic import op
from app.config import get_settings

revision: str = "0002_memory_embedding_trigger"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = get_settings().EMBEDDING_DIM


def upgrade() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION validate_memory_embedding_dimension()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.embedding IS NULL THEN
                RAISE EXCEPTION 'memory embedding must not be null';
            END IF;
            IF vector_dims(NEW.embedding) <> {EMBEDDING_DIM} THEN
                RAISE EXCEPTION 'memory embedding dimension must be {EMBEDDING_DIM}, got %',
                    vector_dims(NEW.embedding);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_memories_embedding_dimension
        BEFORE INSERT OR UPDATE OF embedding ON memories
        FOR EACH ROW
        EXECUTE FUNCTION validate_memory_embedding_dimension();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_memories_embedding_dimension ON memories;")
    op.execute("DROP FUNCTION IF EXISTS validate_memory_embedding_dimension();")