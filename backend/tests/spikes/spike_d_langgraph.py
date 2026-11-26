import asyncio
import uuid
from typing import TypedDict

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


class SpikeDState(TypedDict):
    state_version: int
    prompt: str
    approved: bool | None
    db_written: bool


class ConflictError(Exception):
    pass


def node_assemble(state: SpikeDState) -> dict:
    return {"state_version": 1}


def node_plan(state: SpikeDState) -> dict:
    return {}


def node_human_gate(state: SpikeDState) -> dict:
    # NEVER wrap interrupt() in try...except Exception:
    decision = interrupt({"action": "approve_write", "prompt": state["prompt"]})
    return {"approved": bool(decision.get("approved", False))}


def node_execute(state: SpikeDState) -> dict:
    if not state.get("approved"):
        return {"db_written": False}
    return {"db_written": True}


def _build_graph(checkpointer: AsyncPostgresSaver):
    builder = StateGraph(SpikeDState)
    builder.add_node("assemble", node_assemble)
    builder.add_node("plan", node_plan)
    builder.add_node("human_gate", node_human_gate)
    builder.add_node("execute", node_execute)
    builder.add_edge(START, "assemble")
    builder.add_edge("assemble", "plan")
    builder.add_edge("plan", "human_gate")
    builder.add_edge("human_gate", "execute")
    builder.add_edge("execute", END)
    return builder.compile(checkpointer=checkpointer)


@pytest.mark.asyncio
async def test_spike_d_langgraph_interrupt_and_double_resume_lock():
    """
    Spike D: Prove LangGraph interrupt() + AsyncPostgresSaver + SELECT ... FOR UPDATE
    rejects concurrent double-resume with 409/ConflictError and commits once.
    """
    settings = get_settings()
    async_engine = create_async_engine(settings.DATABASE_ASYNC_URL)
    pg_conn_str = settings.DATABASE_SYNC_URL.replace("postgresql+psycopg://", "postgresql://")
    thread_id = f"spike-d-{uuid.uuid4()}"

    async with async_engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS spike_d_agent_runs (
                    thread_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    writes_count INT NOT NULL DEFAULT 0
                )
                """
            )
        )
        await conn.execute(
            text(
                "INSERT INTO spike_d_agent_runs (thread_id, status, writes_count) "
                "VALUES (:tid, 'running', 0)"
            ),
            {"tid": thread_id},
        )

    try:
        async with AsyncPostgresSaver.from_conn_string(pg_conn_str) as checkpointer:
            await checkpointer.setup()
            graph = _build_graph(checkpointer)
            config = {"configurable": {"thread_id": thread_id}}

            # 1. Run until interrupt()
            paused_state = await graph.ainvoke(
                {
                    "state_version": 1,
                    "prompt": "Create open loop",
                    "approved": None,
                    "db_written": False,
                },
                config=config,
            )
            assert "__interrupt__" in paused_state, "Graph did not pause at interrupt()"

            async with async_engine.begin() as conn:
                await conn.execute(
                    text("UPDATE spike_d_agent_runs SET status = 'interrupted' WHERE thread_id = :tid"),
                    {"tid": thread_id},
                )

            # 2. Fire 2 concurrent resume attempts protected by SELECT ... FOR UPDATE
            async def attempt_resume() -> str:
                async with async_engine.begin() as conn:
                    row = (
                        await conn.execute(
                            text(
                                "SELECT status FROM spike_d_agent_runs "
                                "WHERE thread_id = :tid FOR UPDATE"
                            ),
                            {"tid": thread_id},
                        )
                    ).fetchone()
                    if row is None or row.status != "interrupted":
                        raise ConflictError("409: Run is not in interrupted state")
                    await conn.execute(
                        text("UPDATE spike_d_agent_runs SET status = 'resuming' WHERE thread_id = :tid"),
                        {"tid": thread_id},
                    )

                final_state = await graph.ainvoke(Command(resume={"approved": True}), config=config)
                assert final_state["db_written"] is True

                async with async_engine.begin() as conn:
                    await conn.execute(
                        text(
                            "UPDATE spike_d_agent_runs "
                            "SET status = 'completed', writes_count = writes_count + 1 "
                            "WHERE thread_id = :tid"
                        ),
                        {"tid": thread_id},
                    )
                return "completed"

            results = await asyncio.gather(attempt_resume(), attempt_resume(), return_exceptions=True)

        successes = [r for r in results if r == "completed"]
        conflicts = [r for r in results if isinstance(r, ConflictError)]
        assert len(successes) == 1, f"Expected 1 success, got {results}"
        assert len(conflicts) == 1, f"Expected 1 ConflictError (409), got {results}"

        async with async_engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT status, writes_count FROM spike_d_agent_runs WHERE thread_id = :tid"),
                    {"tid": thread_id},
                )
            ).fetchone()
        assert row is not None
        assert row.status == "completed"
        assert row.writes_count == 1
    finally:
        async with async_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM spike_d_agent_runs WHERE thread_id = :tid"),
                {"tid": thread_id},
            )
        await async_engine.dispose()
