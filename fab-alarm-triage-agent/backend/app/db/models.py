"""SQLAlchemy models for the mock MES plus agent bookkeeping.

Enum columns are stored as native VARCHAR rather than PG ENUM types: the taxonomy in
`app.domain` is expected to grow, and adding a value to a PG ENUM needs a migration
while adding one here does not.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSONB on Postgres, plain JSON elsewhere (keeps SQLite usable for fast unit tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def _ts(**kw: Any) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), **kw)


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    chamber: Mapped[str] = mapped_column(String(16))
    tool_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="up")
    last_pm_at: Mapped[datetime | None] = _ts(nullable=True)
    pm_interval_days: Mapped[int] = mapped_column(Integer, default=30)

    runs: Mapped[list[ProcessRun]] = relationship(back_populates="equipment")


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    params: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = _ts(server_default=func.now())

    __table_args__ = (Index("ix_recipes_name_version", "name", "version", unique=True),)


class RecipeChange(Base):
    __tablename__ = "recipe_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), index=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"), index=True)
    changed_by: Mapped[str] = mapped_column(String(64))
    changed_at: Mapped[datetime] = _ts(index=True)
    param: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str] = mapped_column(String(64))
    new_value: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, default="")


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    product: Mapped[str] = mapped_column(String(64))
    route_step: Mapped[str] = mapped_column(String(64))
    wafer_count: Mapped[int] = mapped_column(Integer, default=25)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = _ts()

    runs: Mapped[list[ProcessRun]] = relationship(back_populates="lot")


class ProcessRun(Base):
    __tablename__ = "process_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"), index=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"), index=True)
    started_at: Mapped[datetime] = _ts(index=True)
    ended_at: Mapped[datetime | None] = _ts(nullable=True)
    secom_row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yield_label: Mapped[str | None] = mapped_column(String(8), nullable=True)  # pass | fail

    lot: Mapped[Lot] = relationship(back_populates="runs")
    equipment: Mapped[Equipment] = relationship(back_populates="runs")
    sensors: Mapped[list[SensorReading]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("process_runs.id"), index=True)
    signal_key: Mapped[str] = mapped_column(String(48), index=True)
    label: Mapped[str] = mapped_column(String(64))
    raw_value: Mapped[float] = mapped_column(Float)
    z_score: Mapped[float] = mapped_column(Float)
    lcl: Mapped[float] = mapped_column(Float)
    ucl: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))

    run: Mapped[ProcessRun] = relationship(back_populates="sensors")

    @property
    def out_of_limit(self) -> bool:
        return self.raw_value < self.lcl or self.raw_value > self.ucl


class Alarm(Base):
    __tablename__ = "alarms"

    id: Mapped[int] = mapped_column(primary_key=True)
    alarm_code: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"), index=True)
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("lots.id"), nullable=True, index=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("process_runs.id"), nullable=True, index=True
    )
    message: Mapped[str] = mapped_column(Text)
    raised_at: Mapped[datetime] = _ts(index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)

    # Ground truth from the scenario generator. Never exposed through any MCP tool or
    # any endpoint the agent can reach — eval reads it directly from the database.
    truth_root_cause: Mapped[str | None] = mapped_column(String(32), nullable=True)
    truth_action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scenario: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_eval_case: Mapped[bool] = mapped_column(default=False, index=True)

    equipment: Mapped[Equipment] = relationship()
    lot: Mapped[Lot | None] = relationship()
    run: Mapped[ProcessRun | None] = relationship()


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    alarm_code: Mapped[str] = mapped_column(String(32), index=True)
    equipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipment.id"), nullable=True, index=True
    )
    signature: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    root_cause_category: Mapped[str] = mapped_column(String(32), index=True)
    root_cause_text: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str] = mapped_column(String(16))
    closed_at: Mapped[datetime] = _ts(index=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    alarm_id: Mapped[int] = mapped_column(ForeignKey("alarms.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    started_at: Mapped[datetime] = _ts(server_default=func.now())
    ended_at: Mapped[datetime | None] = _ts(nullable=True)
    model: Mapped[str] = mapped_column(String(64), default="")
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    steps: Mapped[list[AgentStep]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan", order_by="AgentStep.seq"
    )
    disposition: Mapped[Disposition | None] = relationship(back_populates="agent_run")


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    node: Mapped[str] = mapped_column(String(32))
    tool_name: Mapped[str | None] = mapped_column(String(48), nullable=True)
    tool_args: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    tool_result: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _ts(server_default=func.now())

    agent_run: Mapped[AgentRun] = relationship(back_populates="steps")

    __table_args__ = (Index("ix_agent_steps_run_seq", "agent_run_id", "seq", unique=True),)


class Disposition(Base):
    __tablename__ = "dispositions"

    id: Mapped[int] = mapped_column(primary_key=True)
    alarm_id: Mapped[int] = mapped_column(ForeignKey("alarms.id"), index=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), unique=True, index=True)

    # What the agent proposed.
    recommended_action: Mapped[str] = mapped_column(String(16))
    root_cause_category: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    hypothesis: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)

    # What the engineer decided.
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    engineer_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engineer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decided_at: Mapped[datetime | None] = _ts(nullable=True)
    created_at: Mapped[datetime] = _ts(server_default=func.now())

    agent_run: Mapped[AgentRun] = relationship(back_populates="disposition")
    alarm: Mapped[Alarm] = relationship()
