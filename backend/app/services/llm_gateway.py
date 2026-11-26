import json
import re
import time
import uuid
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)

_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|tvly-[A-Za-z0-9_\-]{8,}|AIza[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9\-._~+/]+=*)"
)

# Static per-1M token USD pricing estimates for V1 observability
_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.5-flash": (0.15, 0.60),
}


def redact_value(value: object, max_len: int = 500) -> object:
    """Recursively mask secrets and truncate long strings before persisting traces."""
    if isinstance(value, str):
        masked = _SECRET_PATTERN.sub("[REDACTED]", value)
        return masked[:max_len] + ("..." if len(masked) > max_len else "")
    if isinstance(value, dict):
        return {str(k): redact_value(v, max_len=max_len) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v, max_len=max_len) for v in value[:20]]
    return value


def estimate_cost_usd(model: str, tokens_in: int | None, tokens_out: int | None) -> float | None:
    if tokens_in is None or tokens_out is None:
        return None
    in_rate, out_rate = _PRICING_PER_1M.get(model, (0.0, 0.0))
    return round((tokens_in * in_rate + tokens_out * out_rate) / 1_000_000.0, 6)


async def _write_trace(
    engine: AsyncEngine,
    *,
    user_id: str,
    thread_id: str | None,
    workflow_name: str,
    step_name: str,
    model_used: str,
    input_summary: dict[str, object],
    output_summary: dict[str, object],
    tokens_in: int | None,
    tokens_out: int | None,
    cost_usd: float | None,
    latency_ms: int,
    status: str,
    trace_table: str = "agent_traces",
) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                f"""
                INSERT INTO {trace_table} (
                    id, user_id, thread_id, workflow_name, step_name,
                    input_summary, output_summary, model_used,
                    tokens_in, tokens_out, cost_usd, latency_ms, status
                ) VALUES (
                    :id, :user_id, :thread_id, :workflow_name, :step_name,
                    CAST(:input_summary AS jsonb), CAST(:output_summary AS jsonb), :model_used,
                    :tokens_in, :tokens_out, :cost_usd, :latency_ms, :status
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "thread_id": thread_id,
                "workflow_name": workflow_name,
                "step_name": step_name,
                "input_summary": json.dumps(redact_value(input_summary)),
                "output_summary": json.dumps(redact_value(output_summary)),
                "model_used": model_used,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
                "latency_ms": latency_ms,
                "status": status,
            },
        )


async def call_structured_llm(
    engine: AsyncEngine,
    *,
    user_id: str,
    workflow_name: str,
    step_name: str,
    prompt: str,
    response_model: type[T],
    thread_id: str | None = None,
    model: str | None = None,
    force_fail: bool = False,
    trace_table: str = "agent_traces",
) -> T:
    """Single LLM Gateway enforcing Pydantic output, secret redaction, and trace persistence."""
    settings = get_settings()
    chosen_model = model or settings.PRIMARY_LLM_MODEL
    t0 = time.perf_counter()

    tokens_in: int | None = None
    tokens_out: int | None = None

    try:
        if force_fail:
            raise RuntimeError("Forced gateway failure for observability verification")

        if settings.OPENAI_API_KEY == "sk-placeholder" or not settings.OPENAI_API_KEY.strip():
            # Deterministic offline fallback when API key is placeholder
            raise ValueError("OPENAI_API_KEY is placeholder")

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=30.0)
        resp = await client.beta.chat.completions.parse(
            model=chosen_model,
            messages=[{"role": "user", "content": prompt}],
            response_format=response_model,
        )
        parsed = resp.choices[0].message.parsed
        if parsed is None:
            raise ValueError("Model returned empty parsed payload")

        if resp.usage is not None:
            tokens_in = resp.usage.prompt_tokens
            tokens_out = resp.usage.completion_tokens

        latency_ms = int((time.perf_counter() - t0) * 1000)
        await _write_trace(
            engine,
            user_id=user_id,
            thread_id=thread_id,
            workflow_name=workflow_name,
            step_name=step_name,
            model_used=chosen_model,
            input_summary={"prompt": prompt},
            output_summary=parsed.model_dump(),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=estimate_cost_usd(chosen_model, tokens_in, tokens_out),
            latency_ms=latency_ms,
            status="success",
            trace_table=trace_table,
        )
        return parsed
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        await _write_trace(
            engine,
            user_id=user_id,
            thread_id=thread_id,
            workflow_name=workflow_name,
            step_name=step_name,
            model_used=chosen_model,
            input_summary={"prompt": prompt},
            output_summary={"error": str(exc)},
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=estimate_cost_usd(chosen_model, tokens_in, tokens_out),
            latency_ms=latency_ms,
            status="failed",
            trace_table=trace_table,
        )
        raise
