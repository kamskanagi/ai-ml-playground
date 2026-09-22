"""Structured output the agent must produce, and the review it waits for."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain import Action, RootCause

EvidenceSource = Literal[
    "sensor", "equipment", "recipe_change", "incident", "lot_history", "recipe"
]


class Evidence(BaseModel):
    """One fact the recommendation rests on.

    `ref` names the thing observed (a signal key, an incident id) so a reviewer can go
    look at it. A hypothesis with no resolvable evidence is not reviewable, which is why
    the proposal requires at least two.
    """

    source: EvidenceSource
    ref: str = Field(description="what was observed, e.g. 'chamber_pressure' or 'incident:12'")
    detail: str = Field(description="the observation itself, with numbers where they exist")


class Disposition(BaseModel):
    """The agent's recommendation. Never applied without a human decision."""

    root_cause: RootCause | None = Field(
        default=None, description="best-supported cause, or null if undetermined"
    )
    action: Action = Field(description="recommended disposition for the lot")
    confidence: float = Field(ge=0.0, le=1.0, description="0-1 confidence in the action")
    hypothesis: str = Field(description="two or three sentences: what happened and why")
    evidence: list[Evidence] = Field(default_factory=list)


class ReviewOutcome(BaseModel):
    """What the engineer decided. This is the value the interrupt is resumed with."""

    decision: Literal["approve", "edit", "reject"]
    engineer: str
    final_action: Action | None = None
    note: str = ""
