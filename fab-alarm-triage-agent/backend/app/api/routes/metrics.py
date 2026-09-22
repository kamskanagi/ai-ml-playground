"""How the agent is doing, offline and in practice."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services import metrics

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/eval")
async def eval_metrics(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """The latest eval report plus live engineer agreement.

    `report` is null when the harness has not been run yet; the dashboard says so rather
    than showing zeroes, which would read as "the agent scored nothing".
    """
    return {
        "report": metrics.load_latest_report(),
        "live": await metrics.live_agreement(session),
    }
