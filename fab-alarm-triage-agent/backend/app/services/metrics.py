"""Evaluation and live-agreement figures for the dashboard.

Two different things sit side by side here on purpose:

* the **offline** report, scored against held-out alarms with known answers;
* the **live** agreement rate, from what engineers actually did with the agent's
  recommendations in the demo set.

Offline accuracy says whether the agent is right. Live agreement says whether the people
using it think so. They can disagree, and that gap is worth seeing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Disposition
from app.domain import DispositionStatus

REPORTS_DIR = Path(__file__).resolve().parents[3] / "eval" / "reports"


def load_latest_report(reports_dir: Path | None = None) -> dict[str, Any] | None:
    """The most recent eval run, or None if the harness has never been run."""
    directory = reports_dir or REPORTS_DIR
    latest = directory / "latest.json"
    if not latest.exists():
        return None
    try:
        return json.loads(latest.read_text())
    except (OSError, json.JSONDecodeError):
        return None


async def live_agreement(session: AsyncSession) -> dict[str, Any]:
    """What engineers did with the agent's recommendations."""
    rows = (
        await session.execute(
            select(Disposition.status, func.count())
            .where(Disposition.status != DispositionStatus.PENDING)
            .group_by(Disposition.status)
        )
    ).all()
    counts = {status: count for status, count in rows}
    decided = sum(counts.values())

    pending = await session.scalar(
        select(func.count())
        .select_from(Disposition)
        .where(Disposition.status == DispositionStatus.PENDING)
    )

    return {
        "decided": decided,
        "pending": pending or 0,
        "approved": counts.get(DispositionStatus.APPROVED, 0),
        "edited": counts.get(DispositionStatus.EDITED, 0),
        "rejected": counts.get(DispositionStatus.REJECTED, 0),
        "agreement_rate": (counts.get(DispositionStatus.APPROVED, 0) / decided)
        if decided
        else None,
    }
