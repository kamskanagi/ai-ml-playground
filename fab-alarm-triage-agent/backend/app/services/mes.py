"""MES queries.

The one data-access path for MES facts. Both the dashboard's REST routes and the MCP
tools the agent calls go through here, so query logic exists once.

Functions return schema objects rather than ORM rows: the ground-truth columns on
`alarms` must not escape this layer, and converting here means no caller can forget.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db.models import (
    Alarm,
    Equipment,
    Incident,
    Lot,
    PmEvent,
    ProcessRun,
    Recipe,
    RecipeChange,
    SensorReading,
)
from app.domain import AlarmStatus
from app.schemas.mes import (
    AlarmDetail,
    AlarmOut,
    EquipmentState,
    IncidentOut,
    LotHistory,
    LotOut,
    RecipeChangeOut,
    RecipeOut,
    RunOut,
    SensorPoint,
    SensorTrace,
    SignalTrace,
)

TREND_RUNS = 6
RECENT_ALARM_WINDOW_DAYS = 30


def _aware(value: datetime | None) -> datetime | None:
    """Postgres returns tz-aware values; SQLite does not. Normalise to UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# --- equipment ------------------------------------------------------------


async def get_equipment_state(
    session: AsyncSession, equipment_id: int, as_of: datetime | None = None
) -> EquipmentState | None:
    equipment = await session.get(Equipment, equipment_id)
    if equipment is None:
        return None

    moment = _aware(as_of) or datetime.now(UTC)

    pm = (
        await session.execute(
            select(PmEvent)
            .where(PmEvent.equipment_id == equipment_id, PmEvent.performed_at <= moment)
            .order_by(PmEvent.performed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    last_pm = _aware(pm.performed_at) if pm else None
    days_since = (moment - last_pm).total_seconds() / 86400 if last_pm else None
    overdue_by = max(0.0, (days_since or 0.0) - equipment.pm_interval_days)

    recent = await session.scalar(
        select(func.count())
        .select_from(Alarm)
        .where(
            Alarm.equipment_id == equipment_id,
            Alarm.raised_at <= moment,
            Alarm.raised_at >= moment - timedelta(days=RECENT_ALARM_WINDOW_DAYS),
        )
    )
    open_count = await session.scalar(
        select(func.count())
        .select_from(Alarm)
        .where(
            Alarm.equipment_id == equipment_id,
            Alarm.raised_at <= moment,
            Alarm.status == AlarmStatus.OPEN,
        )
    )

    return EquipmentState(
        id=equipment.id,
        tool_id=equipment.tool_id,
        chamber=equipment.chamber,
        tool_type=equipment.tool_type,
        status=equipment.status,
        as_of=moment,
        last_pm_at=last_pm,
        last_pm_by=pm.performed_by if pm else None,
        pm_interval_days=equipment.pm_interval_days,
        days_since_pm=days_since,
        pm_overdue=days_since is not None and days_since > equipment.pm_interval_days,
        pm_overdue_by_days=overdue_by,
        alarms_last_30d=recent or 0,
        open_alarms=open_count or 0,
    )


async def list_equipment(session: AsyncSession) -> list[EquipmentState]:
    ids = list((await session.execute(select(Equipment.id).order_by(Equipment.tool_id))).scalars())
    states = [await get_equipment_state(session, pk) for pk in ids]
    return [s for s in states if s is not None]


# --- runs and sensors -----------------------------------------------------


def _run_query() -> Select:
    return (
        select(ProcessRun, Lot.lot_id, Equipment.tool_id, Equipment.chamber, Recipe.name)
        .join(Lot, Lot.id == ProcessRun.lot_id)
        .join(Equipment, Equipment.id == ProcessRun.equipment_id)
        .join(Recipe, Recipe.id == ProcessRun.recipe_id)
    )


async def _breaching_signals(session: AsyncSession, run_ids: list[int]) -> dict[int, list[str]]:
    if not run_ids:
        return {}
    rows = (
        await session.execute(
            select(SensorReading.run_id, SensorReading.signal_key).where(
                SensorReading.run_id.in_(run_ids),
                (SensorReading.raw_value > SensorReading.ucl)
                | (SensorReading.raw_value < SensorReading.lcl),
            )
        )
    ).all()
    out: dict[int, list[str]] = {}
    for run_id, key in rows:
        out.setdefault(run_id, []).append(key)
    return out


def _to_run_out(row, breaches: dict[int, list[str]]) -> RunOut:
    run, lot_id, tool_id, chamber, recipe_name = row
    return RunOut(
        id=run.id,
        lot_id=lot_id,
        tool_id=tool_id,
        chamber=chamber,
        recipe_id=run.recipe_id,
        recipe_name=recipe_name,
        started_at=run.started_at,
        ended_at=run.ended_at,
        yield_label=run.yield_label,
        out_of_limit_signals=sorted(breaches.get(run.id, [])),
    )


async def get_sensor_trace(
    session: AsyncSession,
    run_id: int,
    signals: list[str] | None = None,
    only_out_of_limit: bool = False,
) -> SensorTrace | None:
    """Sensor values on a run, each with the preceding runs on the same tool."""
    row = (await session.execute(_run_query().where(ProcessRun.id == run_id))).first()
    if row is None:
        return None
    run, _lot_id, tool_id, _chamber, _recipe = row

    history_runs = list(
        (
            await session.execute(
                select(ProcessRun.id, ProcessRun.started_at)
                .where(
                    ProcessRun.equipment_id == run.equipment_id,
                    ProcessRun.started_at <= run.started_at,
                )
                .order_by(ProcessRun.started_at.desc())
                .limit(TREND_RUNS)
            )
        ).all()
    )
    history_runs.reverse()
    run_ids = [r for r, _ in history_runs]
    started_by_run = {r: s for r, s in history_runs}

    query = select(SensorReading).where(SensorReading.run_id.in_(run_ids))
    if signals:
        query = query.where(SensorReading.signal_key.in_(signals))
    readings = list((await session.execute(query)).scalars())

    by_signal: dict[str, list[SensorReading]] = {}
    for reading in readings:
        by_signal.setdefault(reading.signal_key, []).append(reading)

    traces: list[SignalTrace] = []
    for key, group in sorted(by_signal.items()):
        ordered = sorted(group, key=lambda r: run_ids.index(r.run_id))
        current = next((r for r in ordered if r.run_id == run_id), None)
        if current is None:
            continue
        if only_out_of_limit and not current.out_of_limit:
            continue
        traces.append(
            SignalTrace(
                signal_key=key,
                label=current.label,
                unit=current.unit,
                lcl=current.lcl,
                ucl=current.ucl,
                current=_point(current, started_by_run),
                history=[_point(r, started_by_run) for r in ordered],
            )
        )

    return SensorTrace(run_id=run_id, tool_id=tool_id, started_at=run.started_at, signals=traces)


def _point(reading: SensorReading, started_by_run: dict[int, datetime]) -> SensorPoint:
    return SensorPoint(
        run_id=reading.run_id,
        started_at=started_by_run[reading.run_id],
        value=reading.raw_value,
        z_score=reading.z_score,
        out_of_limit=reading.out_of_limit,
    )


# --- lots -----------------------------------------------------------------


async def get_lot_history(session: AsyncSession, lot_id: str, limit: int = 20) -> LotHistory | None:
    lot = (await session.execute(select(Lot).where(Lot.lot_id == lot_id))).scalar_one_or_none()
    if lot is None:
        return None

    rows = (
        await session.execute(
            _run_query()
            .where(ProcessRun.lot_id == lot.id)
            .order_by(ProcessRun.started_at.desc())
            .limit(limit)
        )
    ).all()
    breaches = await _breaching_signals(session, [r[0].id for r in rows])

    prior = await session.scalar(
        select(func.count()).select_from(Alarm).where(Alarm.lot_id == lot.id)
    )
    return LotHistory(
        lot=LotOut.model_validate(lot),
        runs=[_to_run_out(r, breaches) for r in rows],
        prior_alarms=prior or 0,
    )


async def list_lots(session: AsyncSession, limit: int = 50) -> list[LotOut]:
    rows = (
        await session.execute(select(Lot).order_by(Lot.started_at.desc()).limit(limit))
    ).scalars()
    return [LotOut.model_validate(r) for r in rows]


# --- recipes --------------------------------------------------------------


async def list_recipes(session: AsyncSession) -> list[RecipeOut]:
    rows = (await session.execute(select(Recipe).order_by(Recipe.name))).scalars()
    return [RecipeOut.model_validate(r) for r in rows]


async def get_recipe(session: AsyncSession, recipe_id: int) -> RecipeOut | None:
    recipe = await session.get(Recipe, recipe_id)
    return RecipeOut.model_validate(recipe) if recipe else None


async def get_recent_recipe_changes(
    session: AsyncSession,
    equipment_id: int,
    window_hours: float = 72.0,
    before: datetime | None = None,
) -> list[RecipeChangeOut]:
    """Recipe changes on a tool within a window ending at `before` (default now).

    Recency is the signal that matters — every tool has routine changes in its history,
    so an unbounded list says nothing.
    """
    end = _aware(before) or datetime.now(UTC)
    start = end - timedelta(hours=window_hours)

    rows = (
        await session.execute(
            select(RecipeChange, Recipe.name, Equipment.tool_id)
            .join(Recipe, Recipe.id == RecipeChange.recipe_id)
            .join(Equipment, Equipment.id == RecipeChange.equipment_id)
            .where(
                RecipeChange.equipment_id == equipment_id,
                RecipeChange.changed_at >= start,
                RecipeChange.changed_at <= end,
            )
            .order_by(RecipeChange.changed_at.desc())
        )
    ).all()

    out = []
    for change, recipe_name, tool_id in rows:
        changed_at = _aware(change.changed_at)
        out.append(
            RecipeChangeOut(
                id=change.id,
                recipe_name=recipe_name,
                tool_id=tool_id,
                changed_by=change.changed_by,
                changed_at=change.changed_at,
                param=change.param,
                old_value=change.old_value,
                new_value=change.new_value,
                reason=change.reason,
                hours_before=(end - changed_at).total_seconds() / 3600 if changed_at else None,
            )
        )
    return out


# --- incidents ------------------------------------------------------------


async def find_similar_incidents(
    session: AsyncSession,
    alarm_code: str | None = None,
    equipment_id: int | None = None,
    limit: int = 5,
) -> list[IncidentOut]:
    """Closed incidents matching an alarm code, most recent first.

    Same-tool incidents sort ahead of others, since a repeat on the same chamber is
    stronger evidence than the same code elsewhere in the bay.
    """
    tool = aliased(Equipment)
    query = (
        select(Incident, tool.tool_id)
        .outerjoin(tool, tool.id == Incident.equipment_id)
        .order_by(
            (Incident.equipment_id == equipment_id).desc()
            if equipment_id is not None
            else Incident.closed_at.desc(),
            Incident.closed_at.desc(),
        )
        .limit(limit)
    )
    if alarm_code:
        query = query.where(Incident.alarm_code == alarm_code)

    rows = (await session.execute(query)).all()
    return [
        IncidentOut(
            id=incident.id,
            alarm_code=incident.alarm_code,
            tool_id=tool_id,
            root_cause_category=incident.root_cause_category,
            root_cause_text=incident.root_cause_text,
            resolution=incident.resolution,
            action_taken=incident.action_taken,
            closed_at=incident.closed_at,
        )
        for incident, tool_id in rows
    ]


# --- alarms ---------------------------------------------------------------


def _alarm_query() -> Select:
    return (
        select(Alarm, Equipment.tool_id, Equipment.chamber, Lot.lot_id)
        .join(Equipment, Equipment.id == Alarm.equipment_id)
        .outerjoin(Lot, Lot.id == Alarm.lot_id)
    )


def _to_alarm_out(row) -> AlarmOut:
    alarm, tool_id, chamber, lot_id = row
    return AlarmOut(
        id=alarm.id,
        alarm_code=alarm.alarm_code,
        severity=alarm.severity,
        message=alarm.message,
        raised_at=alarm.raised_at,
        status=alarm.status,
        tool_id=tool_id,
        chamber=chamber,
        lot_id=lot_id,
        run_id=alarm.run_id,
    )


async def list_alarms(
    session: AsyncSession,
    status: str | None = None,
    include_eval: bool = False,
    limit: int = 100,
) -> list[AlarmOut]:
    """The alarm queue.

    Eval alarms are held back by default so the dashboard shows the demo set and the
    held-out cases are not triaged by hand before they are scored.
    """
    query = _alarm_query().order_by(Alarm.raised_at.desc()).limit(limit)
    if status:
        query = query.where(Alarm.status == status)
    if not include_eval:
        query = query.where(Alarm.is_eval_case.is_(False))
    return [_to_alarm_out(r) for r in (await session.execute(query)).all()]


async def get_alarm(session: AsyncSession, alarm_id: int) -> AlarmDetail | None:
    row = (await session.execute(_alarm_query().where(Alarm.id == alarm_id))).first()
    if row is None:
        return None
    alarm = row[0]
    base = _to_alarm_out(row)

    equipment = await get_equipment_state(session, alarm.equipment_id, as_of=alarm.raised_at)
    lot = await session.get(Lot, alarm.lot_id) if alarm.lot_id else None

    recipe_id: int | None = None
    recipe_name: str | None = None
    if alarm.run_id is not None:
        run_row = (await session.execute(_run_query().where(ProcessRun.id == alarm.run_id))).first()
        if run_row is not None:
            recipe_id, recipe_name = run_row[0].recipe_id, run_row[4]

    breaching: list[SignalTrace] = []
    if alarm.run_id is not None:
        trace = await get_sensor_trace(session, alarm.run_id, only_out_of_limit=True)
        breaching = trace.signals if trace else []

    return AlarmDetail(
        **base.model_dump(),
        equipment=equipment,
        lot=LotOut.model_validate(lot) if lot else None,
        recipe_id=recipe_id,
        recipe_name=recipe_name,
        out_of_limit=breaching,
    )
