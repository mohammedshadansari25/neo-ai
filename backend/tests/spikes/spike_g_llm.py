import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.services.llm_gateway import call_structured_llm


class SpikeGResult(BaseModel):
    summary: str


@pytest.mark.asyncio
async def test_spike_g_llm_gateway_observability_and_redaction():
    """
    Spike G: Prove llm_gateway.py logs both success and forced-failure rows
    with latency, model, redacted payloads, and nullable tokens/cost.
    """
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_ASYNC_URL)
    user_id = str(uuid.uuid4())
    thread_id = f"spike-g-{uuid.uuid4()}"

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS spike_g_agent_traces (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL,
                    thread_id VARCHAR(128) NULL,
                    event_seq BIGINT GENERATED ALWAYS AS IDENTITY,
                    workflow_name VARCHAR(100) NOT NULL,
                    step_name VARCHAR(100) NOT NULL,
                    idempotency_key CHAR(64) NULL,
                    input_summary JSONB NULL,
                    output_summary JSONB NULL,
                    model_used VARCHAR(100) NULL,
                    tokens_in INT NULL,
                    tokens_out INT NULL,
                    cost_usd NUMERIC(10,6) NULL,
                    latency_ms INT NULL,
                    status VARCHAR(32) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )

    try:
        use_real_key = (
            settings.OPENAI_API_KEY != "sk-placeholder" and bool(settings.OPENAI_API_KEY.strip())
        )
        if use_real_key:
            res = await call_structured_llm(
                engine,
                user_id=user_id,
                thread_id=thread_id,
                workflow_name="spike_g",
                step_name="valid_call",
                prompt="Reply with summary: Neo AI V1 Spike G OK.",
                response_model=SpikeGResult,
                trace_table="spike_g_agent_traces",
            )
            assert isinstance(res, SpikeGResult)
        else:
            fake_resp = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(parsed=SpikeGResult(summary="OK")))],
                usage=SimpleNamespace(prompt_tokens=12, completion_tokens=5),
            )
            with (
                patch("app.services.llm_gateway.get_settings") as mock_settings,
                patch("app.services.llm_gateway.AsyncOpenAI") as mock_openai_cls,
            ):
                mock_settings.return_value = SimpleNamespace(
                    OPENAI_API_KEY="sk-mocked-for-spike-test",
                    PRIMARY_LLM_MODEL="gpt-4o-mini",
                )
                mock_client = mock_openai_cls.return_value
                mock_client.beta.chat.completions.parse = AsyncMock(return_value=fake_resp)

                res = await call_structured_llm(
                    engine,
                    user_id=user_id,
                    thread_id=thread_id,
                    workflow_name="spike_g",
                    step_name="valid_call",
                    prompt="Summarize Spike G.",
                    response_model=SpikeGResult,
                    trace_table="spike_g_agent_traces",
                )
                assert res.summary == "OK"

        # 2. Forced failure with a secret in prompt -> must redact & persist nullable tokens
        with pytest.raises(RuntimeError, match="Forced gateway failure"):
            await call_structured_llm(
                engine,
                user_id=user_id,
                thread_id=thread_id,
                workflow_name="spike_g",
                step_name="forced_fail",
                prompt="Use key sk-secret1234567890abcdef in request",
                response_model=SpikeGResult,
                force_fail=True,
                trace_table="spike_g_agent_traces",
            )

        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT step_name, status, model_used, tokens_in, tokens_out, "
                        "cost_usd, latency_ms, input_summary "
                        "FROM spike_g_agent_traces WHERE thread_id = :tid ORDER BY event_seq ASC"
                    ),
                    {"tid": thread_id},
                )
            ).fetchall()

        assert len(rows) == 2
        ok_row, fail_row = rows[0], rows[1]
        assert ok_row.status == "success"
        assert ok_row.tokens_in is not None and ok_row.tokens_out is not None
        assert ok_row.latency_ms >= 0

        assert fail_row.status == "failed"
        assert fail_row.tokens_in is None
        assert fail_row.cost_usd is None
        assert "sk-secret" not in str(fail_row.input_summary)
        assert "[REDACTED]" in str(fail_row.input_summary)
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM spike_g_agent_traces WHERE thread_id = :tid"),
                {"tid": thread_id},
            )
        await engine.dispose()
