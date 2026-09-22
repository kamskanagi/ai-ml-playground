"""Request and response models for triage.

As with the MES schemas, fields are listed explicitly — the alarm's ground-truth columns
must not reach the dashboard or the agent through this surface either.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain import Action, ReviewDecision


class TriageStarted(BaseModel):
    agent_run_id: int
    thread_id: str
    alarm_id: int


class DispositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alarm_id: int
    recommended_action: Action
    root_cause_category: str | None
    confidence: float
    hypothesis: str
    evidence: list[dict[str, Any]]
    status: str
    engineer_name: str | None
    engineer_note: str | None
    final_action: Action | None
    decided_at: datetime | None
    created_at: datetime


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    node: str
    tool_name: str | None
    tool_args: dict[str, Any] | None
    tool_result: dict[str, Any] | None
    latency_ms: int | None
    error: str | None
    created_at: datetime


class AgentRunOut(BaseModel):
    id: int
    alarm_id: int
    thread_id: str
    status: str
    model: str
    started_at: datetime
    ended_at: datetime | None
    error: str | None
    disposition: DispositionOut | None


class ReviewRequest(BaseModel):
    """What the engineer submits. Resumed into the paused graph verbatim."""

    decision: ReviewDecision
    engineer: str = Field(min_length=1, max_length=64)
    final_action: Action | None = Field(
        default=None, description="required when decision is 'edit'"
    )
    note: str = ""
