"""Graph behaviour, driven by a scripted model.

No database, no MCP server, no API calls. `agent_run_id=0` disables step tracing, and the
two write callbacks are captured in lists, so these exercise the graph itself.

The tests that matter most are the ones around the pause: that it actually stops, that
resuming records the decision exactly once, and that a model which cannot produce a valid
answer escalates rather than waving the lot through.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agent.graph import build_graph
from app.agent.schemas import Disposition, Evidence
from app.domain import Action, RootCause
from tests.stub_model import StubChatModel

ALARM_PAYLOAD = {
    "id": 7,
    "alarm_code": "HE_LEAK_HIGH",
    "severity": "critical",
    "message": "Helium leak rate above upper control limit",
    "raised_at": "2026-09-20T22:26:21Z",
    "tool_id": "ETCH-05",
    "chamber": "CH2",
    "lot_id": "L26-1095",
    "run_id": 42,
    "recipe_id": 3,
    "recipe_name": "VIA-DEEP-B",
    "equipment": {
        "id": 5,
        "days_since_pm": 3.2,
        "pm_interval_days": 30,
        "pm_overdue": False,
        "alarms_last_30d": 1,
    },
    "out_of_limit": [
        {
            "signal_key": "he_leak_rate",
            "label": "Helium Leak Rate",
            "unit": "sccm",
            "lcl": 0.0,
            "ucl": 2.0,
            "current": {"value": 2.67, "z_score": 5.0, "out_of_limit": True},
            "history": [{"value": 1.0}, {"value": 1.8}, {"value": 2.67}],
        }
    ],
}

GOOD_DISPOSITION = Disposition(
    root_cause=RootCause.CHAMBER_LEAK,
    action=Action.HOLD_LOT,
    confidence=0.84,
    hypothesis="Helium leak rate is 2.67 sccm against a 2.0 upper limit and climbing.",
    evidence=[
        Evidence(source="sensor", ref="he_leak_rate", detail="2.67 sccm, 5.0 sigma high"),
        Evidence(source="equipment", ref="ETCH-05", detail="PM current at 3.2 days"),
    ],
)


def make_tool(name: str, payload: object) -> StructuredTool:
    async def _call(**kwargs: object) -> object:
        return payload

    return StructuredTool.from_function(
        coroutine=_call, name=name, description=f"stub {name}", infer_schema=False
    )


class Recorder:
    """Captures the graph's write callbacks so they can be counted."""

    def __init__(self) -> None:
        self.proposals: list[tuple[Disposition, str | None]] = []
        self.decisions: list[dict] = []

    async def on_propose(self, state, disposition, fallback) -> None:
        self.proposals.append((disposition, fallback))

    async def on_decision(self, state, review) -> None:
        self.decisions.append(review)


def build(llm, tools=None, recorder=None, checkpointer=None, cap=12):
    return build_graph(
        tools=tools or [make_tool("get_alarm", ALARM_PAYLOAD)],
        llm=llm,
        sessionmaker=None,
        checkpointer=checkpointer or InMemorySaver(),
        on_propose=recorder.on_propose if recorder else None,
        on_decision=recorder.on_decision if recorder else None,
        max_tool_calls=cap,
    )


def start_state(alarm_id: int = 7) -> dict:
    # agent_run_id 0 is falsy, which switches off step tracing and its database writes.
    return {"alarm_id": alarm_id, "agent_run_id": 0, "tool_calls_made": 0}


# --- the pause ------------------------------------------------------------


async def test_graph_stops_at_human_review():
    recorder = Recorder()
    llm = StubChatModel(
        script=[AIMessage(content="I have enough."), AIMessage(content="Reasoning.")],
        structured_script=[GOOD_DISPOSITION],
    )
    graph = build(llm, recorder=recorder)
    config = {"configurable": {"thread_id": "pause-1"}}

    result = await graph.ainvoke(start_state(), config)

    assert "__interrupt__" in result, "the graph should pause, not run to completion"
    state = await graph.aget_state(config)
    assert state.next == ("human_review",)
    assert recorder.decisions == [], "no decision may be recorded before a human answers"


async def test_proposal_is_written_before_the_pause():
    """The recommendation must be persisted while paused, or the UI has nothing to show."""
    recorder = Recorder()
    llm = StubChatModel(
        script=[AIMessage(content="done"), AIMessage(content="reasoning")],
        structured_script=[GOOD_DISPOSITION],
    )
    graph = build(llm, recorder=recorder)
    await graph.ainvoke(start_state(), {"configurable": {"thread_id": "pause-2"}})

    assert len(recorder.proposals) == 1
    disposition, fallback = recorder.proposals[0]
    assert disposition.action == Action.HOLD_LOT
    assert fallback is None


async def test_interrupt_payload_carries_the_proposal():
    """The pause hands the reviewer what they need to decide on."""
    llm = StubChatModel(
        script=[AIMessage(content="done"), AIMessage(content="reasoning")],
        structured_script=[GOOD_DISPOSITION],
    )
    graph = build(llm)
    result = await graph.ainvoke(start_state(), {"configurable": {"thread_id": "pause-3"}})

    payload = result["__interrupt__"][0].value
    assert payload["alarm_id"] == 7
    assert payload["proposal"]["action"] == "hold_lot"


# --- the resume -----------------------------------------------------------


async def test_resume_records_the_decision_exactly_once():
    """The replay hazard: a write sharing the interrupt node would fire twice."""
    recorder = Recorder()
    llm = StubChatModel(
        script=[AIMessage(content="done"), AIMessage(content="reasoning")],
        structured_script=[GOOD_DISPOSITION],
    )
    graph = build(llm, recorder=recorder)
    config = {"configurable": {"thread_id": "resume-1"}}

    await graph.ainvoke(start_state(), config)
    review = {"decision": "approve", "engineer": "R. Okafor", "note": "agreed"}
    final = await graph.ainvoke(Command(resume=review), config)

    assert len(recorder.decisions) == 1, "decision written more than once"
    assert recorder.decisions[0] == review
    assert len(recorder.proposals) == 1, "proposal re-written during replay"
    assert "__interrupt__" not in final
    assert final["review"]["decision"] == "approve"


async def test_resume_carries_an_edited_action_through():
    recorder = Recorder()
    llm = StubChatModel(
        script=[AIMessage(content="done"), AIMessage(content="reasoning")],
        structured_script=[GOOD_DISPOSITION],
    )
    graph = build(llm, recorder=recorder)
    config = {"configurable": {"thread_id": "resume-2"}}

    await graph.ainvoke(start_state(), config)
    await graph.ainvoke(
        Command(resume={"decision": "edit", "engineer": "L. Tanaka", "final_action": "escalate"}),
        config,
    )
    assert recorder.decisions[0]["final_action"] == "escalate"


async def test_a_run_left_paused_stays_paused():
    """No timeout, no default. It waits."""
    llm = StubChatModel(
        script=[AIMessage(content="done"), AIMessage(content="reasoning")],
        structured_script=[GOOD_DISPOSITION],
    )
    graph = build(llm)
    config = {"configurable": {"thread_id": "paused-forever"}}
    await graph.ainvoke(start_state(), config)

    for _ in range(3):
        state = await graph.aget_state(config)
        assert state.next == ("human_review",)


# --- the tool loop --------------------------------------------------------


async def test_investigate_runs_requested_tools_and_loops_back():
    call = AIMessage(
        content="",
        tool_calls=[{"name": "get_sensor_trace", "args": {"run_id": 42}, "id": "c1"}],
    )
    llm = StubChatModel(
        script=[call, AIMessage(content="enough"), AIMessage(content="reasoning")],
        structured_script=[GOOD_DISPOSITION],
    )
    graph = build(
        llm,
        tools=[
            make_tool("get_alarm", ALARM_PAYLOAD),
            make_tool("get_sensor_trace", {"signals": []}),
        ],
    )
    result = await graph.ainvoke(start_state(), {"configurable": {"thread_id": "tools-1"}})
    assert result["tool_calls_made"] == 1


async def test_tool_calls_are_capped():
    """A model that keeps asking for tools must not loop forever."""

    def always_calls():
        return AIMessage(
            content="",
            tool_calls=[{"name": "get_sensor_trace", "args": {"run_id": 42}, "id": "x"}],
        )

    llm = StubChatModel(
        script=[always_calls() for _ in range(20)] + [AIMessage(content="reasoning")],
        structured_script=[GOOD_DISPOSITION],
    )
    graph = build(
        llm,
        tools=[
            make_tool("get_alarm", ALARM_PAYLOAD),
            make_tool("get_sensor_trace", {"signals": []}),
        ],
        cap=3,
    )
    result = await graph.ainvoke(start_state(), {"configurable": {"thread_id": "cap-1"}})
    assert result["tool_calls_made"] <= 3


async def test_a_failing_tool_does_not_kill_the_run():
    """A broken tool becomes a message the model can read, not a crash."""

    async def boom(**kwargs: object) -> object:
        raise RuntimeError("MES exploded")

    bad = StructuredTool.from_function(
        coroutine=boom, name="get_sensor_trace", description="stub", infer_schema=False
    )
    llm = StubChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[{"name": "get_sensor_trace", "args": {}, "id": "c1"}],
            ),
            AIMessage(content="carrying on"),
            AIMessage(content="reasoning"),
        ],
        structured_script=[GOOD_DISPOSITION],
    )
    graph = build(llm, tools=[make_tool("get_alarm", ALARM_PAYLOAD), bad])
    result = await graph.ainvoke(start_state(), {"configurable": {"thread_id": "toolfail-1"}})
    assert "__interrupt__" in result, "the run should still reach review"


async def test_unknown_tool_is_reported_rather_than_raising():
    llm = StubChatModel(
        script=[
            AIMessage(content="", tool_calls=[{"name": "nonexistent", "args": {}, "id": "c1"}]),
            AIMessage(content="ok"),
            AIMessage(content="reasoning"),
        ],
        structured_script=[GOOD_DISPOSITION],
    )
    graph = build(llm)
    result = await graph.ainvoke(start_state(), {"configurable": {"thread_id": "badtool-1"}})
    assert "__interrupt__" in result


# --- the fail-safe --------------------------------------------------------


async def test_structured_output_is_retried_once_before_giving_up():
    recorder = Recorder()
    llm = StubChatModel(
        script=[AIMessage(content="done"), AIMessage(content="reasoning")],
        structured_script=[ValueError("not json"), GOOD_DISPOSITION],
    )
    graph = build(llm, recorder=recorder)
    await graph.ainvoke(start_state(), {"configurable": {"thread_id": "retry-1"}})

    assert llm.structured_calls == 2
    disposition, fallback = recorder.proposals[0]
    assert fallback is None
    assert disposition.action == Action.HOLD_LOT


async def test_repeated_parse_failure_escalates_rather_than_continuing():
    """The safety default. An agent that cannot reason must not wave the lot through."""
    recorder = Recorder()
    llm = StubChatModel(
        script=[AIMessage(content="done"), AIMessage(content="reasoning")],
        structured_script=[ValueError("bad"), ValueError("still bad")],
    )
    graph = build(llm, recorder=recorder)
    result = await graph.ainvoke(start_state(), {"configurable": {"thread_id": "fallback-1"}})

    disposition, fallback = recorder.proposals[0]
    assert disposition.action == Action.ESCALATE
    assert disposition.action != Action.CONTINUE
    assert disposition.confidence == 0.0
    assert disposition.root_cause is None
    assert fallback and "bad" in fallback
    assert "__interrupt__" in result, "even a fallback still goes to a human"


@pytest.mark.parametrize("failures", [1, 2])
async def test_the_run_always_reaches_review(failures: int):
    recorder = Recorder()
    script: list = [ValueError("bad")] * failures
    if failures < 2:
        script.append(GOOD_DISPOSITION)
    llm = StubChatModel(
        script=[AIMessage(content="done"), AIMessage(content="reasoning")],
        structured_script=script,
    )
    graph = build(llm, recorder=recorder)
    result = await graph.ainvoke(
        start_state(), {"configurable": {"thread_id": f"always-{failures}"}}
    )
    assert "__interrupt__" in result
    assert len(recorder.proposals) == 1


# --- context -------------------------------------------------------------


async def test_the_alarm_context_is_put_in_the_opening_prompt():
    """Otherwise the model spends its first tool call fetching what we already have."""
    llm = StubChatModel(
        script=[AIMessage(content="done"), AIMessage(content="reasoning")],
        structured_script=[GOOD_DISPOSITION],
    )
    graph = build(llm)
    await graph.ainvoke(start_state(), {"configurable": {"thread_id": "ctx-1"}})

    opening = "\n".join(str(m.content) for m in llm.prompts_seen[0])
    assert "HE_LEAK_HIGH" in opening
    assert "he_leak_rate" in opening
    assert "2.67" in opening
    assert "days since PM" in opening


async def test_a_missing_alarm_still_produces_a_reviewable_run():
    llm = StubChatModel(
        script=[AIMessage(content="cannot tell"), AIMessage(content="reasoning")],
        structured_script=[ValueError("no data"), ValueError("no data")],
    )
    graph = build(llm, tools=[make_tool("get_alarm", {"error": "Not found: /api/alarms/999"})])
    result = await graph.ainvoke(
        {"alarm_id": 999, "agent_run_id": 0, "tool_calls_made": 0},
        {"configurable": {"thread_id": "missing-1"}},
    )
    assert "__interrupt__" in result
    opening = "\n".join(str(m.content) for m in llm.prompts_seen[0])
    assert "Could not load the alarm" in opening
