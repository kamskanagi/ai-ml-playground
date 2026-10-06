"""Response models for the MES API.

Every model lists its fields explicitly. `Alarm` carries ground-truth columns
(`truth_root_cause`, `truth_action`, `scenario`, `is_eval_case`) that the agent must
never see; declaring fields by hand rather than dumping the ORM model is what keeps
them out. `tests/test_api_mes.py::test_no_endpoint_leaks_ground_truth` enforces it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain import Action, AlarmCode, RootCause


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- equipment ------------------------------------------------------------


class EquipmentOut(ORMModel):
    id: int
    tool_id: str
    chamber: str
    tool_type: str
    status: str


class EquipmentState(EquipmentOut):
    """Equipment as of a point in time.

    `as_of` matters: triaging an alarm raised three weeks ago must report the PM age at
    that moment, not today's.
    """

    as_of: datetime
    last_pm_at: datetime | None
    last_pm_by: str | None
    pm_interval_days: int
    days_since_pm: float | None
    pm_overdue: bool
    pm_overdue_by_days: float
    alarms_last_30d: int
    open_alarms: int


# --- lots and runs --------------------------------------------------------


class LotOut(ORMModel):
    id: int
    lot_id: str
    product: str
    route_step: str
    wafer_count: int
    priority: str
    status: str
    started_at: datetime


class RunOut(BaseModel):
    id: int
    lot_id: str
    tool_id: str
    chamber: str
    recipe_id: int
    recipe_name: str
    started_at: datetime
    ended_at: datetime | None
    yield_label: str | None
    out_of_limit_signals: list[str] = []


class LotHistory(BaseModel):
    lot: LotOut
    runs: list[RunOut]
    prior_alarms: int


# --- sensors --------------------------------------------------------------


class SensorPoint(BaseModel):
    run_id: int
    started_at: datetime
    value: float
    z_score: float
    out_of_limit: bool


class SignalTrace(BaseModel):
    """One signal on the alarm run, with the preceding runs on the same tool.

    The shape of `history` is the evidence that separates a drift from a spike from a
    stuck reading, so the trend travels with the value rather than needing a second call.
    """

    signal_key: str
    label: str
    unit: str
    lcl: float
    ucl: float
    current: SensorPoint
    history: list[SensorPoint]


class SensorTrace(BaseModel):
    run_id: int
    tool_id: str
    started_at: datetime
    signals: list[SignalTrace]


# --- recipes --------------------------------------------------------------


class RecipeOut(ORMModel):
    id: int
    name: str
    version: int
    params: dict[str, float]


class RecipeChangeOut(BaseModel):
    id: int
    recipe_name: str
    tool_id: str
    changed_by: str
    changed_at: datetime
    param: str
    old_value: str
    new_value: str
    reason: str
    hours_before: float | None = None


# --- alarms ---------------------------------------------------------------


class AlarmOut(ORMModel):
    id: int
    alarm_code: AlarmCode
    severity: str
    message: str
    raised_at: datetime
    status: str
    tool_id: str
    chamber: str
    lot_id: str | None
    run_id: int | None


class AlarmDetail(AlarmOut):
    equipment: EquipmentState
    lot: LotOut | None
    # Carried so the agent can reach the recipe from the alarm without guessing an id.
    recipe_id: int | None
    recipe_name: str | None
    out_of_limit: list[SignalTrace]


# --- incidents ------------------------------------------------------------


class IncidentOut(BaseModel):
    id: int
    alarm_code: AlarmCode
    tool_id: str | None
    root_cause_category: RootCause
    root_cause_text: str
    resolution: str
    action_taken: Action
    closed_at: datetime
