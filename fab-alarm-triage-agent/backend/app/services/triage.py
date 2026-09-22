"""Starting, pausing and resuming triage runs.

The graph calls `on_propose` before it pauses and `on_decision` after it resumes. Both
live here rather than in the graph so that every database write sits outside the node
holding `interrupt()` — a write in that node would run a second time on resume, because
LangGraph replays from the checkpoint boundary rather than the paused line.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import Disposition
from app.config import get_settings
from app.db.models import AgentRun, Alarm, Lot
from app.db.models import Disposition as DispositionRow
from app.db.session import get_sessionmaker
from app.domain import (
    Action,
    AgentRunStatus,
    AlarmStatus,
    DispositionStatus,
    LotStatus,
    ReviewDecision,
)
from app.schemas.triage import AgentRunOut, DispositionOut, StepOut, TriageStarted


async def start_run(session: AsyncSession, alarm_id: int) -> TriageStarted | None:
    """Create the bookkeeping row for a run. Does not execute the graph."""
    alarm = await session.get(Alarm, alarm_id)
    if alarm is None:
        return None

    run = AgentRun(
        alarm_id=alarm_id,
        thread_id=str(uuid.uuid4()),
        status=AgentRunStatus.RUNNING,
        model=get_settings().groq_model,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return TriageStarted(agent_run_id=run.id, thread_id=run.thread_id, alarm_id=alarm_id)


async def execute(agent_run_id: int, alarm_id: int, thread_id: str) -> None:
    """Run the graph until it pauses for review, or fails.

    Called as a background task. A run that pauses is not an error: the graph stops
    inside `human_review` and stays checkpointed until a decision arrives.
    """
    from app.agent.runtime import get_graph

    sessionmaker = get_sessionmaker()
    try:
        graph = await get_graph()
        await graph.ainvoke(
            {"alarm_id": alarm_id, "agent_run_id": agent_run_id, "tool_calls_made": 0},
            {"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:  # noqa: BLE001 - recorded so the UI can show why
        async with sessionmaker() as session:
            run = await session.get(AgentRun, agent_run_id)
            if run is not None:
                run.status = AgentRunStatus.FAILED
                run.error = f"{type(exc).__name__}: {exc}"[:2000]
                run.ended_at = datetime.now(UTC)
                await session.commit()


# --- graph callbacks ------------------------------------------------------


async def on_propose(state: dict[str, Any], disposition: Disposition, fallback: str | None) -> None:
    """Persist the recommendation, then mark the run as awaiting review.

    Runs in `propose`, before the interrupt, so it happens exactly once.
    """
    agent_run_id = state.get("agent_run_id")
    if not agent_run_id:
        return

    async with get_sessionmaker()() as session:
        run = await session.get(AgentRun, agent_run_id)
        if run is None:
            return

        existing = await session.scalar(
            select(DispositionRow).where(DispositionRow.agent_run_id == agent_run_id)
        )
        if existing is None:
            session.add(
                DispositionRow(
                    alarm_id=state["alarm_id"],
                    agent_run_id=agent_run_id,
                    recommended_action=disposition.action,
                    root_cause_category=disposition.root_cause,
                    confidence=disposition.confidence,
                    hypothesis=disposition.hypothesis,
                    evidence=[e.model_dump() for e in disposition.evidence],
                    status=DispositionStatus.PENDING,
                )
            )

        run.status = AgentRunStatus.AWAITING_REVIEW
        if fallback:
            run.error = f"structured output fallback: {fallback}"[:2000]
        await session.commit()


async def on_decision(state: dict[str, Any], review: dict[str, Any]) -> None:
    """Apply the engineer's decision. Runs in `record_decision`, after the interrupt."""
    agent_run_id = state.get("agent_run_id")
    if not agent_run_id:
        return

    decision = review.get("decision")
    engineer = review.get("engineer") or "unknown"

    async with get_sessionmaker()() as session:
        row = await session.scalar(
            select(DispositionRow).where(DispositionRow.agent_run_id == agent_run_id)
        )
        run = await session.get(AgentRun, agent_run_id)
        if row is None or run is None:
            return

        if decision == ReviewDecision.APPROVE:
            row.status = DispositionStatus.APPROVED
            row.final_action = row.recommended_action
        elif decision == ReviewDecision.EDIT:
            row.status = DispositionStatus.EDITED
            row.final_action = review.get("final_action") or row.recommended_action
        else:
            row.status = DispositionStatus.REJECTED
            row.final_action = None

        row.engineer_name = engineer
        row.engineer_note = review.get("note") or ""
        row.decided_at = datetime.now(UTC)

        alarm = await session.get(Alarm, row.alarm_id)
        if alarm is not None:
            # A rejected recommendation leaves the alarm open: the agent's answer was
            # thrown out, so nothing has actually been decided about the lot.
            alarm.status = (
                AlarmStatus.OPEN
                if row.status == DispositionStatus.REJECTED
                else AlarmStatus.TRIAGED
            )
            if row.final_action == Action.HOLD_LOT and alarm.lot_id:
                lot = await session.get(Lot, alarm.lot_id)
                if lot is not None:
                    lot.status = LotStatus.HOLD

        run.status = AgentRunStatus.COMPLETED
        run.ended_at = datetime.now(UTC)
        await session.commit()


# --- resume ---------------------------------------------------------------


async def submit_review(
    session: AsyncSession, agent_run_id: int, review: dict[str, Any]
) -> AgentRunOut | None:
    """Resume a paused run with the engineer's decision.

    The graph picks up inside `human_review`, which returns the value passed here, and
    carries on to `record_decision`.
    """
    from langgraph.types import Command

    from app.agent.runtime import get_graph

    run = await session.get(AgentRun, agent_run_id)
    if run is None:
        return None
    if run.status != AgentRunStatus.AWAITING_REVIEW:
        raise ValueError(f"Run {agent_run_id} is {run.status}, not awaiting review")

    graph = await get_graph()
    await graph.ainvoke(Command(resume=review), {"configurable": {"thread_id": run.thread_id}})
    session.expire_all()
    return await get_run(session, agent_run_id)


# --- reads ----------------------------------------------------------------


async def get_run(session: AsyncSession, agent_run_id: int) -> AgentRunOut | None:
    run = await session.get(AgentRun, agent_run_id)
    if run is None:
        return None

    row = await session.scalar(
        select(DispositionRow).where(DispositionRow.agent_run_id == agent_run_id)
    )
    return AgentRunOut(
        id=run.id,
        alarm_id=run.alarm_id,
        thread_id=run.thread_id,
        status=run.status,
        model=run.model,
        started_at=run.started_at,
        ended_at=run.ended_at,
        error=run.error,
        disposition=DispositionOut.model_validate(row) if row else None,
    )


async def get_trace(session: AsyncSession, agent_run_id: int) -> list[StepOut]:
    from app.db.models import AgentStep

    rows = (
        await session.execute(
            select(AgentStep).where(AgentStep.agent_run_id == agent_run_id).order_by(AgentStep.seq)
        )
    ).scalars()
    return [StepOut.model_validate(r) for r in rows]


async def list_runs_for_alarm(session: AsyncSession, alarm_id: int) -> list[AgentRunOut]:
    ids = list(
        (
            await session.execute(
                select(AgentRun.id)
                .where(AgentRun.alarm_id == alarm_id)
                .order_by(AgentRun.started_at.desc())
            )
        ).scalars()
    )
    runs = [await get_run(session, pk) for pk in ids]
    return [r for r in runs if r is not None]
