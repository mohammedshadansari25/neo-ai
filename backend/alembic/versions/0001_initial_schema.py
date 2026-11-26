"""Initial Neo AI V1 schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op
from app.config import get_settings

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = get_settings().EMBEDDING_DIM


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("profile_summary", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("idx_refresh_user", "refresh_tokens", ["user_id"])

    op.create_table(
        "captured_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.Enum("text", "url", "pdf", "image", "youtube", name="source_type_enum"), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("raw_uri", sa.Text(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("extracted_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("extraction_status", sa.Enum("queued", "processing", "needs_review", "completed", "failed", name="extraction_status_enum"), server_default="queued", nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)", name="ck_items_confidence_range"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_items_user_hash", "captured_items", ["user_id", "content_hash"], unique=True, postgresql_where=sa.text("extraction_status != 'failed'"))
    op.create_index("idx_items_user_status", "captured_items", ["user_id", "extraction_status", sa.text("created_at DESC")])

    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_type", sa.Enum("semantic", "episodic", "procedural", name="memory_type_enum"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("search_vector", postgresql.TSVECTOR(), sa.Computed("to_tsvector('english', content)", persisted=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("superseded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confidence", sa.Float(), server_default=sa.text("0.8"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("superseded_by IS DISTINCT FROM id", name="ck_memories_no_self_supersede"),
        sa.ForeignKeyConstraint(["superseded_by"], ["memories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_memories_emb",
        "memories",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_where=sa.text("superseded_by IS NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "idx_memories_tsv",
        "memories",
        ["search_vector"],
        postgresql_using="gin",
        postgresql_where=sa.text("superseded_by IS NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "idx_memories_user_active",
        "memories",
        ["user_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("superseded_by IS NULL AND deleted_at IS NULL"),
    )

    op.create_table(
        "memory_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["captured_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("memory_id", "item_id", "page_number", "chunk_index", name="uq_memsrc_tuple"),
    )
    op.create_index("idx_memsrc_memory", "memory_sources", ["memory_id"])
    op.create_index("idx_memsrc_item", "memory_sources", ["item_id"])

    op.create_table(
        "memory_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation_type", sa.Enum("supports", "contradicts", "extends", "prerequisite", name="relation_type_enum"), nullable=False),
        sa.Column("strength", sa.Float(), server_default=sa.text("0.5"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source_memory_id <> target_memory_id", name="ck_memlink_distinct"),
        sa.ForeignKeyConstraint(["source_memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source_memory_id", "target_memory_id", "relation_type", name="uq_memlink_unique"),
    )
    op.create_index("idx_memlink_src", "memory_links", ["source_memory_id"])
    op.create_index("idx_memlink_tgt", "memory_links", ["target_memory_id"])

    op.create_table(
        "goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Enum("active", "stalled", "completed", "archived", name="goal_status_enum"), server_default="active", nullable=False),
        sa.Column("progress_pct", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("progress_pct BETWEEN 0 AND 100", name="ck_goals_progress_pct"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_goals_user_status", "goals", ["user_id", "status", "target_date"])

    op.create_table(
        "open_loops",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=400), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("loop_type", sa.Enum("deadline", "unfinished_task", "opportunity", "knowledge_gap", name="loop_type_enum"), nullable=False),
        sa.Column("status", sa.Enum("detected", "pending_approval", "scheduled", "completed", "dismissed", name="loop_status_enum"), server_default="detected", nullable=False),
        sa.Column("priority_score", sa.Float(), server_default=sa.text("0.5"), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proposed_tool_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_item_id"], ["captured_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_loops_user_active", "open_loops", ["user_id", "status", "due_at"])

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", sa.String(length=128), nullable=False),
        sa.Column("workflow_name", sa.String(length=100), nullable=False),
        sa.Column("goal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Enum("running", "interrupted", "resuming", "completed", "rejected", "failed", name="agent_run_status_enum"), server_default="running", nullable=False),
        sa.Column("state_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("current_node", sa.String(length=100), nullable=True),
        sa.Column("pending_approval_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index("idx_runs_user_status", "agent_runs", ["user_id", "status", sa.text("created_at DESC")])

    op.create_table(
        "agent_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", sa.String(length=128), nullable=True),
        sa.Column("event_seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("workflow_name", sa.String(length=100), nullable=False),
        sa.Column("step_name", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("input_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_used", sa.String(length=100), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.Enum("success", "repaired", "interrupted", "failed", "skipped", name="trace_status_enum"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_traces_idemp", "agent_traces", ["user_id", "idempotency_key"], unique=True, postgresql_where=sa.text("idempotency_key IS NOT NULL"))
    op.create_index("idx_traces_user_thread_seq", "agent_traces", ["user_id", "thread_id", "event_seq"])


def downgrade() -> None:
    op.drop_table("agent_traces")
    op.drop_table("agent_runs")
    op.drop_table("open_loops")
    op.drop_table("goals")
    op.drop_table("memory_links")
    op.drop_table("memory_sources")
    op.drop_table("memories")
    op.drop_table("captured_items")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    for enum_name in (
        "trace_status_enum",
        "agent_run_status_enum",
        "loop_status_enum",
        "loop_type_enum",
        "goal_status_enum",
        "relation_type_enum",
        "memory_type_enum",
        "extraction_status_enum",
        "source_type_enum",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")
