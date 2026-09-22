"""Things that can produce a disposition for an alarm.

The agent is one of these. The others are baselines, and they are not filler: without a
baseline, an accuracy figure means nothing. "78% correct" is only good if the trivial
strategies do worse.

Two baselines, each answering a specific question:

* `always-escalate` — what does refusing to decide score? It is perfectly safe by
  construction (it never waves a lot through) and almost useless, which is exactly why
  safety cannot be the only number.
* `majority-by-code` — can a lookup table solve this? It learns the most common action
  per alarm code from the demo set and applies it to the held-out set. Phase 1 made two
  alarm codes deliberately ambiguous, so this baseline should be capped well below the
  agent. If it is not, the dataset is solvable without reasoning and the agent's score
  means nothing.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alarm
from app.domain import Action


@dataclass
class Prediction:
    action: str
    root_cause: str | None = None
    confidence: float = 0.0
    evidence_count: int = 0
    tool_calls: int = 0
    latency_ms: int = 0
    fallback: bool = False
    error: str | None = None


class Predictor(Protocol):
    name: str

    async def predict(self, session: AsyncSession, alarm: Alarm) -> Prediction: ...


class AlwaysEscalate:
    """Never decides. Zero unsafe continues, and close to zero use."""

    name = "baseline-always-escalate"

    async def predict(self, session: AsyncSession, alarm: Alarm) -> Prediction:
        return Prediction(action=Action.ESCALATE, confidence=0.0)


class MajorityByCode:
    """Fit the most common action per alarm code on the demo set, apply to the eval set.

    Fitting on the demo alarms and testing on the held-out ones keeps this honest: it may
    not see a single label from the set it is scored on.
    """

    name = "baseline-majority-by-code"

    def __init__(self) -> None:
        self._by_code: dict[str, str] = {}
        self._cause_by_code: dict[str, str] = {}
        self._fallback = Action.ESCALATE.value

    async def fit(self, session: AsyncSession) -> None:
        rows = (
            await session.execute(
                select(Alarm.alarm_code, Alarm.truth_action, Alarm.truth_root_cause).where(
                    Alarm.is_eval_case.is_(False)
                )
            )
        ).all()

        actions: dict[str, Counter] = defaultdict(Counter)
        causes: dict[str, Counter] = defaultdict(Counter)
        overall: Counter = Counter()
        for code, action, cause in rows:
            if action:
                actions[code][action] += 1
                overall[action] += 1
            if cause:
                causes[code][cause] += 1

        self._by_code = {code: c.most_common(1)[0][0] for code, c in actions.items()}
        self._cause_by_code = {code: c.most_common(1)[0][0] for code, c in causes.items()}
        if overall:
            self._fallback = overall.most_common(1)[0][0]

    async def predict(self, session: AsyncSession, alarm: Alarm) -> Prediction:
        return Prediction(
            action=self._by_code.get(alarm.alarm_code, self._fallback),
            root_cause=self._cause_by_code.get(alarm.alarm_code),
            confidence=0.0,
        )


class TriageAgent:
    """The real thing: run the graph, auto-approve the pause, read what it proposed.

    The interrupt is resumed with a synthetic approval purely so the run reaches a
    terminal state. What is scored is the agent's *recommendation*, made before any
    decision existed — the approval never influences it.
    """

    name = "agent"

    def __init__(self, model_name: str) -> None:
        self.name = model_name

    async def predict(self, session: AsyncSession, alarm: Alarm) -> Prediction:
        from langgraph.types import Command

        from app.agent.runtime import get_graph
        from app.db.models import AgentStep
        from app.services import triage

        started_at = time.perf_counter()
        started = await triage.start_run(session, alarm.id)
        if started is None:
            return Prediction(action=Action.ESCALATE, error="could not start run")

        config = {"configurable": {"thread_id": started.thread_id}}
        try:
            graph = await get_graph()
            await graph.ainvoke(
                {
                    "alarm_id": alarm.id,
                    "agent_run_id": started.agent_run_id,
                    "tool_calls_made": 0,
                },
                config,
            )
            await graph.ainvoke(
                Command(resume={"decision": "approve", "engineer": "eval-harness"}), config
            )
        except Exception as exc:  # noqa: BLE001 - one bad case must not end the run
            return Prediction(
                action=Action.ESCALATE,
                error=f"{type(exc).__name__}: {exc}"[:300],
                latency_ms=int((time.perf_counter() - started_at) * 1000),
            )

        session.expire_all()
        run = await triage.get_run(session, started.agent_run_id)
        steps = (
            (
                await session.execute(
                    select(AgentStep).where(AgentStep.agent_run_id == started.agent_run_id)
                )
            )
            .scalars()
            .all()
        )
        tool_calls = sum(1 for s in steps if s.tool_name)

        if run is None or run.disposition is None:
            return Prediction(
                action=Action.ESCALATE,
                error="run produced no disposition",
                tool_calls=tool_calls,
                latency_ms=int((time.perf_counter() - started_at) * 1000),
            )

        d = run.disposition
        return Prediction(
            action=d.recommended_action,
            root_cause=d.root_cause_category,
            confidence=d.confidence,
            evidence_count=len(d.evidence),
            tool_calls=tool_calls,
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            fallback=bool(run.error and "fallback" in run.error),
        )
