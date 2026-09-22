"""Persist what the agent did, step by step.

Every tool call and node transition is written to `agent_steps` as it happens rather than
at the end, so a run that crashes or is abandoned mid-investigation still leaves a
readable trail.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import AgentStep

# Tool payloads can be large; a trace is for reading, not for replay.
MAX_RESULT_CHARS = 4000


def _truncate(value: Any) -> Any:
    text = value if isinstance(value, str) else repr(value)
    if len(text) <= MAX_RESULT_CHARS:
        return value
    return f"{text[:MAX_RESULT_CHARS]}... [{len(text) - MAX_RESULT_CHARS} more chars]"


async def record_step(
    sessionmaker: async_sessionmaker,
    agent_run_id: int,
    node: str,
    *,
    tool_name: str | None = None,
    tool_args: dict[str, Any] | None = None,
    tool_result: Any = None,
    latency_ms: int | None = None,
    error: str | None = None,
) -> None:
    async with sessionmaker() as session:
        next_seq = (
            await session.scalar(
                select(func.coalesce(func.max(AgentStep.seq), 0) + 1).where(
                    AgentStep.agent_run_id == agent_run_id
                )
            )
        ) or 1
        session.add(
            AgentStep(
                agent_run_id=agent_run_id,
                seq=next_seq,
                node=node,
                tool_name=tool_name,
                tool_args=tool_args,
                tool_result={"value": _truncate(tool_result)} if tool_result is not None else None,
                latency_ms=latency_ms,
                error=error,
            )
        )
        await session.commit()
