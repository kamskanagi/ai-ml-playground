"""Triage endpoints: start a run, watch it, and decide on it."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.domain import ReviewDecision
from app.schemas.triage import AgentRunOut, ReviewRequest, StepOut, TriageStarted
from app.services import triage

router = APIRouter(prefix="/api", tags=["triage"])


@router.post("/alarms/{alarm_id}/triage", response_model=TriageStarted, status_code=202)
async def start_triage(
    alarm_id: int,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Start an investigation. Returns immediately; the graph runs in the background.

    202 rather than 200: the work has been accepted, not completed. Poll the run to see
    when it reaches `awaiting_review`.
    """
    started = await triage.start_run(session, alarm_id)
    if started is None:
        raise HTTPException(status_code=404, detail=f"No alarm {alarm_id}")

    background.add_task(triage.execute, started.agent_run_id, started.alarm_id, started.thread_id)
    return started


@router.get("/agent-runs/{agent_run_id}", response_model=AgentRunOut)
async def get_agent_run(agent_run_id: int, session: AsyncSession = Depends(get_session)):
    run = await triage.get_run(session, agent_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No agent run {agent_run_id}")
    return run


@router.get("/agent-runs/{agent_run_id}/trace", response_model=list[StepOut])
async def get_trace(agent_run_id: int, session: AsyncSession = Depends(get_session)):
    return await triage.get_trace(session, agent_run_id)


@router.get("/alarms/{alarm_id}/agent-runs", response_model=list[AgentRunOut])
async def runs_for_alarm(alarm_id: int, session: AsyncSession = Depends(get_session)):
    return await triage.list_runs_for_alarm(session, alarm_id)


@router.post("/agent-runs/{agent_run_id}/review", response_model=AgentRunOut)
async def submit_review(
    agent_run_id: int,
    body: ReviewRequest,
    session: AsyncSession = Depends(get_session),
):
    """Approve, edit or reject a pending recommendation, resuming the paused run."""
    if body.decision == ReviewDecision.EDIT and body.final_action is None:
        raise HTTPException(
            status_code=422, detail="final_action is required when decision is 'edit'"
        )

    try:
        run = await triage.submit_review(session, agent_run_id, body.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if run is None:
        raise HTTPException(status_code=404, detail=f"No agent run {agent_run_id}")
    return run
