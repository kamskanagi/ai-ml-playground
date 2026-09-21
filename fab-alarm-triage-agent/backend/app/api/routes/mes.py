"""MES read endpoints.

Thin: each route resolves dependencies and delegates to app.services.mes. The MCP
server calls these same endpoints, so anything added here is available to the agent.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.mes import (
    AlarmDetail,
    AlarmOut,
    EquipmentState,
    IncidentOut,
    LotHistory,
    LotOut,
    RecipeChangeOut,
    RecipeOut,
    SensorTrace,
)
from app.services import mes

router = APIRouter(prefix="/api", tags=["mes"])


@router.get("/alarms", response_model=list[AlarmOut])
async def list_alarms(
    status: str | None = None,
    include_eval: bool = Query(False, description="include held-out eval alarms"),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    return await mes.list_alarms(session, status=status, include_eval=include_eval, limit=limit)


@router.get("/alarms/{alarm_id}", response_model=AlarmDetail)
async def get_alarm(alarm_id: int, session: AsyncSession = Depends(get_session)):
    alarm = await mes.get_alarm(session, alarm_id)
    if alarm is None:
        raise HTTPException(status_code=404, detail=f"No alarm {alarm_id}")
    return alarm


@router.get("/equipment", response_model=list[EquipmentState])
async def list_equipment(session: AsyncSession = Depends(get_session)):
    return await mes.list_equipment(session)


@router.get("/equipment/{equipment_id}", response_model=EquipmentState)
async def get_equipment(
    equipment_id: int,
    as_of: datetime | None = Query(None, description="report PM age at this moment"),
    session: AsyncSession = Depends(get_session),
):
    state = await mes.get_equipment_state(session, equipment_id, as_of=as_of)
    if state is None:
        raise HTTPException(status_code=404, detail=f"No equipment {equipment_id}")
    return state


@router.get("/equipment/{equipment_id}/recipe-changes", response_model=list[RecipeChangeOut])
async def recent_recipe_changes(
    equipment_id: int,
    window_hours: float = Query(72.0, gt=0, le=24 * 90),
    before: datetime | None = None,
    session: AsyncSession = Depends(get_session),
):
    return await mes.get_recent_recipe_changes(
        session, equipment_id, window_hours=window_hours, before=before
    )


@router.get("/lots", response_model=list[LotOut])
async def list_lots(
    limit: int = Query(50, ge=1, le=500), session: AsyncSession = Depends(get_session)
):
    return await mes.list_lots(session, limit=limit)


@router.get("/lots/{lot_id}", response_model=LotHistory)
async def get_lot_history(
    lot_id: str,
    limit: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    history = await mes.get_lot_history(session, lot_id, limit=limit)
    if history is None:
        raise HTTPException(status_code=404, detail=f"No lot {lot_id}")
    return history


@router.get("/runs/{run_id}/sensors", response_model=SensorTrace)
async def get_sensor_trace(
    run_id: int,
    signals: list[str] | None = Query(None, description="restrict to these signal keys"),
    only_out_of_limit: bool = False,
    session: AsyncSession = Depends(get_session),
):
    trace = await mes.get_sensor_trace(
        session, run_id, signals=signals, only_out_of_limit=only_out_of_limit
    )
    if trace is None:
        raise HTTPException(status_code=404, detail=f"No run {run_id}")
    return trace


@router.get("/recipes", response_model=list[RecipeOut])
async def list_recipes(session: AsyncSession = Depends(get_session)):
    return await mes.list_recipes(session)


@router.get("/recipes/{recipe_id}", response_model=RecipeOut)
async def get_recipe(recipe_id: int, session: AsyncSession = Depends(get_session)):
    recipe = await mes.get_recipe(session, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail=f"No recipe {recipe_id}")
    return recipe


@router.get("/incidents", response_model=list[IncidentOut])
async def find_similar_incidents(
    alarm_code: str | None = None,
    equipment_id: int | None = None,
    limit: int = Query(5, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    return await mes.find_similar_incidents(
        session, alarm_code=alarm_code, equipment_id=equipment_id, limit=limit
    )
