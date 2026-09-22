"""Durability and end-to-end triage, against real Postgres.

The first test is the one that justifies the architecture: a run paused for review is
resumed by a *different* graph object with a *different* checkpointer, built fresh from
the database. That is what a process restart looks like from the inside. If it passes,
the pause is genuinely durable rather than an in-memory convention.

The rest drive the real endpoints with a scripted model, so the database writes, the lot
hold and the step trace are all exercised without an API call.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.types import Command
from sqlalchemy import select

from app.agent.graph import build_graph
from app.agent.schemas import Disposition, Evidence
from app.db.models import AgentRun, AgentStep, Alarm, Lot
from app.db.models import Disposition as DispositionRow
from app.db.session import get_sessionmaker
from app.domain import Action, AgentRunStatus, AlarmStatus, DispositionStatus, LotStatus, RootCause
from app.services import triage
from tests.stub_model import StubChatModel

HOLD_DISPOSITION = Disposition(
    root_cause=RootCause.CHAMBER_LEAK,
    action=Action.HOLD_LOT,
    confidence=0.88,
    hypothesis="Helium leak rate 2.67 sccm against a 2.0 upper limit, climbing over three runs.",
    evidence=[
        Evidence(source="sensor", ref="he_leak_rate", detail="2.67 sccm, 5.0 sigma above UCL"),
        Evidence(source="incident", ref="incident:12", detail="same chamber, seal replaced"),
    ],
)


def stub_llm() -> StubChatModel:
    return StubChatModel(
        script=[AIMessage(content="I have enough."), AIMessage(content="Reasoning.")],
        structured_script=[HOLD_DISPOSITION],
    )


def alarm_tool(payload: dict) -> StructuredTool:
    async def _call(**kwargs: object) -> dict:
        return payload

    return StructuredTool.from_function(
        coroutine=_call, name="get_alarm", description="stub", infer_schema=False
    )


@dataclass(frozen=True)
class AlarmRef:
    """Plain values, not a live ORM row.

    Tests call `session.expire_all()` to see what the agent wrote from its own session.
    That expires any attached ORM object, and reading an attribute afterwards triggers a
    lazy reload that SQLAlchemy attempts synchronously inside async code. Copying the
    fields out once avoids the whole problem.
    """

    id: int
    lot_id: int
    alarm_code: str


@pytest.fixture
async def open_alarm(session) -> AlarmRef:
    """A seeded open alarm with a lot attached, so a hold has something to act on."""
    alarm = await session.scalar(
        select(Alarm).where(Alarm.status == AlarmStatus.OPEN, Alarm.lot_id.is_not(None)).limit(1)
    )
    assert alarm is not None, "seeded data should contain an open alarm with a lot"
    return AlarmRef(id=alarm.id, lot_id=alarm.lot_id, alarm_code=alarm.alarm_code)


# --- the restart test -----------------------------------------------------


async def test_a_paused_run_survives_losing_the_process(database, session, open_alarm):
    """Pause with one graph, resume with a completely different one.

    Nothing is shared between the two halves except the thread id and Postgres. This is
    the difference between human-in-the-loop and human-after-the-loop.
    """
    from app.agent.runtime import close_checkpointer, open_checkpointer

    started = await triage.start_run(session, open_alarm.id)
    config = {"configurable": {"thread_id": started.thread_id}}
    payload = {"id": open_alarm.id, "alarm_code": open_alarm.alarm_code, "out_of_limit": []}

    # --- first process: investigate and pause
    first_graph = build_graph(
        tools=[alarm_tool(payload)],
        llm=stub_llm(),
        sessionmaker=get_sessionmaker(),
        checkpointer=await open_checkpointer(),
        on_propose=triage.on_propose,
        on_decision=triage.on_decision,
    )
    result = await first_graph.ainvoke(
        {"alarm_id": open_alarm.id, "agent_run_id": started.agent_run_id, "tool_calls_made": 0},
        config,
    )
    assert "__interrupt__" in result

    run = await triage.get_run(session, started.agent_run_id)
    assert run.status == AgentRunStatus.AWAITING_REVIEW
    assert run.disposition.status == DispositionStatus.PENDING

    # --- the process dies
    del first_graph
    await close_checkpointer()

    # --- second process: a new checkpointer, a new graph, a new model
    second_graph = build_graph(
        tools=[alarm_tool(payload)],
        llm=stub_llm(),
        sessionmaker=get_sessionmaker(),
        checkpointer=await open_checkpointer(),
        on_propose=triage.on_propose,
        on_decision=triage.on_decision,
    )
    final = await second_graph.ainvoke(
        Command(resume={"decision": "approve", "engineer": "R. Okafor", "note": "agreed"}),
        config,
    )

    assert "__interrupt__" not in final
    assert final["review"]["engineer"] == "R. Okafor"

    session.expire_all()
    resumed = await triage.get_run(session, started.agent_run_id)
    assert resumed.status == AgentRunStatus.COMPLETED
    assert resumed.disposition.status == DispositionStatus.APPROVED
    assert resumed.disposition.final_action == Action.HOLD_LOT
    assert resumed.disposition.engineer_name == "R. Okafor"


async def test_the_second_process_sees_the_original_investigation(database, session, open_alarm):
    """Resume restores state, not just the ability to continue."""
    from app.agent.runtime import close_checkpointer, open_checkpointer

    started = await triage.start_run(session, open_alarm.id)
    config = {"configurable": {"thread_id": started.thread_id}}
    payload = {"id": open_alarm.id, "alarm_code": open_alarm.alarm_code, "out_of_limit": []}

    graph = build_graph(
        tools=[alarm_tool(payload)],
        llm=stub_llm(),
        sessionmaker=get_sessionmaker(),
        checkpointer=await open_checkpointer(),
        on_propose=triage.on_propose,
    )
    await graph.ainvoke(
        {"alarm_id": open_alarm.id, "agent_run_id": started.agent_run_id, "tool_calls_made": 0},
        config,
    )
    await close_checkpointer()

    fresh = build_graph(
        tools=[alarm_tool(payload)],
        llm=stub_llm(),
        sessionmaker=get_sessionmaker(),
        checkpointer=await open_checkpointer(),
    )
    state = await fresh.aget_state(config)

    assert state.next == ("human_review",)
    assert state.values["proposal"]["action"] == "hold_lot"
    assert state.values["alarm_id"] == open_alarm.id
    assert len(state.values["messages"]) >= 3, "the conversation itself was restored"


# --- through the API ------------------------------------------------------


@pytest.fixture
async def patched_graph(monkeypatch, database):
    """Point the runtime at a stub-backed graph so the endpoints run without Groq or MCP."""
    from app.agent import runtime

    async def fake_get_graph():
        alarm_payload = {"id": 0, "alarm_code": "STUB", "out_of_limit": []}
        return build_graph(
            tools=[alarm_tool(alarm_payload)],
            llm=stub_llm(),
            sessionmaker=get_sessionmaker(),
            checkpointer=await runtime.open_checkpointer(),
            on_propose=triage.on_propose,
            on_decision=triage.on_decision,
        )

    monkeypatch.setattr(runtime, "get_graph", fake_get_graph)
    yield
    runtime.reset()


async def test_triage_endpoint_runs_to_a_pending_recommendation(
    client, session, open_alarm, patched_graph
):
    response = await client.post(f"/api/alarms/{open_alarm.id}/triage")
    assert response.status_code == 202
    run_id = response.json()["agent_run_id"]

    run = (await client.get(f"/api/agent-runs/{run_id}")).json()
    assert run["status"] == AgentRunStatus.AWAITING_REVIEW
    assert run["disposition"]["status"] == DispositionStatus.PENDING
    assert run["disposition"]["recommended_action"] == Action.HOLD_LOT
    assert len(run["disposition"]["evidence"]) == 2


async def test_approving_holds_the_lot_and_closes_the_alarm(
    client, session, open_alarm, patched_graph
):
    lot_pk = open_alarm.lot_id
    run_id = (await client.post(f"/api/alarms/{open_alarm.id}/triage")).json()["agent_run_id"]

    reviewed = await client.post(
        f"/api/agent-runs/{run_id}/review",
        json={"decision": "approve", "engineer": "M. Silva", "note": "confirmed"},
    )
    assert reviewed.status_code == 200
    body = reviewed.json()
    assert body["status"] == AgentRunStatus.COMPLETED
    assert body["disposition"]["final_action"] == Action.HOLD_LOT

    session.expire_all()
    assert (await session.get(Lot, lot_pk)).status == LotStatus.HOLD
    assert (await session.get(Alarm, open_alarm.id)).status == AlarmStatus.TRIAGED


async def test_editing_records_the_engineers_action_not_the_agents(
    client, session, open_alarm, patched_graph
):
    run_id = (await client.post(f"/api/alarms/{open_alarm.id}/triage")).json()["agent_run_id"]
    body = (
        await client.post(
            f"/api/agent-runs/{run_id}/review",
            json={
                "decision": "edit",
                "engineer": "A. Haddad",
                "final_action": "escalate",
                "note": "tool needs a tech, lot is fine",
            },
        )
    ).json()

    assert body["disposition"]["status"] == DispositionStatus.EDITED
    assert body["disposition"]["recommended_action"] == Action.HOLD_LOT
    assert body["disposition"]["final_action"] == Action.ESCALATE


async def test_rejecting_leaves_the_alarm_open(client, session, open_alarm, patched_graph):
    """A thrown-out recommendation means nothing has been decided about the lot."""
    lot_pk = open_alarm.lot_id
    run_id = (await client.post(f"/api/alarms/{open_alarm.id}/triage")).json()["agent_run_id"]

    body = (
        await client.post(
            f"/api/agent-runs/{run_id}/review",
            json={"decision": "reject", "engineer": "J. Whitfield", "note": "not convinced"},
        )
    ).json()

    assert body["disposition"]["status"] == DispositionStatus.REJECTED
    assert body["disposition"]["final_action"] is None

    session.expire_all()
    assert (await session.get(Alarm, open_alarm.id)).status == AlarmStatus.OPEN
    assert (await session.get(Lot, lot_pk)).status != LotStatus.HOLD


async def test_editing_without_a_final_action_is_rejected(client, open_alarm, patched_graph):
    run_id = (await client.post(f"/api/alarms/{open_alarm.id}/triage")).json()["agent_run_id"]
    response = await client.post(
        f"/api/agent-runs/{run_id}/review", json={"decision": "edit", "engineer": "X"}
    )
    assert response.status_code == 422


async def test_a_run_cannot_be_reviewed_twice(client, open_alarm, patched_graph):
    run_id = (await client.post(f"/api/alarms/{open_alarm.id}/triage")).json()["agent_run_id"]
    first = await client.post(
        f"/api/agent-runs/{run_id}/review", json={"decision": "approve", "engineer": "M. Silva"}
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/agent-runs/{run_id}/review", json={"decision": "approve", "engineer": "M. Silva"}
    )
    assert second.status_code == 409


async def test_triage_on_a_missing_alarm_is_404(client, patched_graph):
    assert (await client.post("/api/alarms/999999/triage")).status_code == 404


# --- the trace ------------------------------------------------------------


async def test_every_step_is_recorded_in_order(client, session, open_alarm, patched_graph):
    run_id = (await client.post(f"/api/alarms/{open_alarm.id}/triage")).json()["agent_run_id"]
    await client.post(
        f"/api/agent-runs/{run_id}/review", json={"decision": "approve", "engineer": "M. Silva"}
    )

    steps = (await client.get(f"/api/agent-runs/{run_id}/trace")).json()
    assert steps, "a run with no trace is not auditable"
    assert [s["seq"] for s in steps] == sorted(s["seq"] for s in steps)

    nodes = [s["node"] for s in steps]
    assert "load_alarm" in nodes
    assert "propose" in nodes
    assert "record_decision" in nodes
    assert nodes.index("propose") < nodes.index("record_decision")


async def test_the_trace_survives_alongside_the_run(session, open_alarm, database):
    """Steps are written as they happen, so an abandoned run still leaves a trail."""
    from app.agent.runtime import open_checkpointer

    started = await triage.start_run(session, open_alarm.id)
    graph = build_graph(
        tools=[alarm_tool({"id": open_alarm.id, "alarm_code": "X", "out_of_limit": []})],
        llm=stub_llm(),
        sessionmaker=get_sessionmaker(),
        checkpointer=await open_checkpointer(),
        on_propose=triage.on_propose,
    )
    await graph.ainvoke(
        {"alarm_id": open_alarm.id, "agent_run_id": started.agent_run_id, "tool_calls_made": 0},
        {"configurable": {"thread_id": started.thread_id}},
    )

    steps = (
        (
            await session.execute(
                select(AgentStep).where(AgentStep.agent_run_id == started.agent_run_id)
            )
        )
        .scalars()
        .all()
    )
    assert steps, "the run paused but its steps should already be persisted"


async def test_the_disposition_is_written_once_per_run(session, open_alarm, database):
    """Guards the replay hazard at the database level, not just in the callbacks."""
    from app.agent.runtime import open_checkpointer

    started = await triage.start_run(session, open_alarm.id)
    config = {"configurable": {"thread_id": started.thread_id}}
    graph = build_graph(
        tools=[alarm_tool({"id": open_alarm.id, "alarm_code": "X", "out_of_limit": []})],
        llm=stub_llm(),
        sessionmaker=get_sessionmaker(),
        checkpointer=await open_checkpointer(),
        on_propose=triage.on_propose,
        on_decision=triage.on_decision,
    )
    await graph.ainvoke(
        {"alarm_id": open_alarm.id, "agent_run_id": started.agent_run_id, "tool_calls_made": 0},
        config,
    )
    await graph.ainvoke(Command(resume={"decision": "approve", "engineer": "M. Silva"}), config)

    rows = (
        (
            await session.execute(
                select(DispositionRow).where(DispositionRow.agent_run_id == started.agent_run_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1

    runs = (
        (await session.execute(select(AgentRun).where(AgentRun.id == started.agent_run_id)))
        .scalars()
        .all()
    )
    assert len(runs) == 1
