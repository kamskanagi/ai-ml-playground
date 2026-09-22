"""The triage graph.

    load_alarm -> investigate <-> tools -> hypothesize -> propose
                                                            |
                                                      human_review  (pauses here)
                                                            |
                                                     record_decision -> END

Two constraints from LangGraph's execution model shape this file, and breaking either
produces bugs that only appear after a resume:

1. `human_review` contains a single `interrupt()` call and nothing else. On resume the
   graph replays from the checkpoint boundary rather than the paused line, so any side
   effect sharing that node would run twice. Every write lives in `propose` (before) or
   `record_decision` (after).

2. `interrupt()` raises through `GraphBubbleUp`, bypassing retry policies and node error
   handlers. Nothing here may swallow it with a bare `except`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent import prompts
from app.agent.schemas import Disposition
from app.agent.tracing import record_step
from app.config import get_settings
from app.domain import Action

# Tools whose results are worth summarising into the opening prompt rather than making
# the model spend a call to discover them.
ALARM_TOOL = "get_alarm"


class TriageState(TypedDict, total=False):
    alarm_id: int
    agent_run_id: int
    messages: Annotated[list[AnyMessage], add_messages]
    tool_calls_made: int
    alarm: dict[str, Any]
    proposal: dict[str, Any]
    review: dict[str, Any]
    fallback_reason: str | None


def _summarise_alarm(alarm: dict[str, Any]) -> str:
    """Put the alarm's own context in the first prompt.

    The agent would otherwise spend its first tool call fetching what we already have,
    and a weaker model sometimes never gets past it.
    """
    if "error" in alarm:
        return f"Could not load the alarm: {alarm['error']}"

    equipment = alarm.get("equipment") or {}
    lines = [
        f"Alarm code: {alarm.get('alarm_code')} (severity {alarm.get('severity')})",
        f"Message: {alarm.get('message')}",
        f"Raised at: {alarm.get('raised_at')}",
        f"Tool: {alarm.get('tool_id')}/{alarm.get('chamber')} (equipment_id={equipment.get('id')})",
        f"Lot: {alarm.get('lot_id')}   Run: {alarm.get('run_id')}   "
        f"Recipe: {alarm.get('recipe_name')} (recipe_id={alarm.get('recipe_id')})",
    ]

    days = equipment.get("days_since_pm")
    if days is not None:
        lines.append(
            f"Equipment at that moment: {days:.1f} days since PM "
            f"(interval {equipment.get('pm_interval_days')}), "
            f"overdue={equipment.get('pm_overdue')}, "
            f"alarms in prior 30d={equipment.get('alarms_last_30d')}"
        )

    breaching = alarm.get("out_of_limit") or []
    if breaching:
        lines.append("Signals outside control limits on this run:")
        for signal in breaching:
            current = signal.get("current", {})
            history = " -> ".join(f"{p['value']:.2f}" for p in signal.get("history", []))
            lines.append(
                f"  - {signal.get('label')} ({signal.get('signal_key')}): "
                f"{current.get('value'):.2f} {signal.get('unit')}, "
                f"z={current.get('z_score'):+.2f}, "
                f"limits [{signal.get('lcl')}, {signal.get('ucl')}]"
            )
            if history:
                lines.append(f"      recent runs: {history}")
    else:
        lines.append("No signals were outside control limits on this run.")

    return "\n".join(lines)


def build_graph(
    tools: list[BaseTool],
    llm: BaseChatModel,
    sessionmaker: async_sessionmaker,
    checkpointer: Any,
    on_propose: Callable | None = None,
    on_decision: Callable | None = None,
    max_tool_calls: int | None = None,
):
    """Compile the triage graph.

    Tools, model, persistence and the two write callbacks are all injected so the graph
    can be exercised with a stub model and an in-memory checkpointer, costing no API
    calls. `on_propose` and `on_decision` do the database writes; keeping them out of
    this module is what lets the graph be tested without the MES.
    """
    settings = get_settings()
    cap = max_tool_calls if max_tool_calls is not None else settings.max_tool_calls
    tools_by_name = {tool.name: tool for tool in tools}
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    async def trace(state: TriageState, node: str, **kw: Any) -> None:
        run_id = state.get("agent_run_id")
        if run_id:
            await record_step(sessionmaker, run_id, node, **kw)

    # --- nodes ------------------------------------------------------------

    async def load_alarm(state: TriageState) -> dict[str, Any]:
        """Fetch the alarm and open the conversation with its context."""
        alarm: dict[str, Any] = {}
        tool = tools_by_name.get(ALARM_TOOL)
        if tool is not None:
            started = time.perf_counter()
            try:
                alarm = _as_dict(await tool.ainvoke({"alarm_id": state["alarm_id"]}))
                error = None
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                alarm, error = {"error": str(exc)}, str(exc)
            await trace(
                state,
                "load_alarm",
                tool_name=ALARM_TOOL,
                tool_args={"alarm_id": state["alarm_id"]},
                tool_result=alarm,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=error,
            )

        return {
            "alarm": alarm,
            "tool_calls_made": 0,
            "messages": [
                SystemMessage(prompts.SYSTEM.format(max_tool_calls=cap)),
                HumanMessage(
                    prompts.INVESTIGATE.format(
                        alarm_id=state["alarm_id"], alarm_summary=_summarise_alarm(alarm)
                    )
                ),
            ],
        }

    async def investigate(state: TriageState) -> dict[str, Any]:
        response = await llm_with_tools.ainvoke(state["messages"])
        await trace(state, "investigate")
        return {"messages": [response]}

    async def run_tools(state: TriageState) -> dict[str, Any]:
        """Execute the requested tool calls, recording each one.

        Written out rather than using the prebuilt ToolNode so every call lands in
        `agent_steps` with its latency, and so the cap counts real calls.
        """
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", []) or []
        out: list[ToolMessage] = []

        for call in calls:
            tool = tools_by_name.get(call["name"])
            started = time.perf_counter()
            if tool is None:
                result: Any = {"error": f"No such tool: {call['name']}"}
                error: str | None = result["error"]
            else:
                try:
                    result = _as_text(await tool.ainvoke(call["args"]))
                    error = None
                except Exception as exc:  # noqa: BLE001 - surfaced to the model
                    result = {"error": f"{type(exc).__name__}: {exc}"}
                    error = str(exc)

            await trace(
                state,
                "tools",
                tool_name=call["name"],
                tool_args=call["args"],
                tool_result=result,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=error,
            )
            out.append(
                ToolMessage(
                    content=result if isinstance(result, str) else repr(result),
                    tool_call_id=call["id"],
                    name=call["name"],
                )
            )

        return {"messages": out, "tool_calls_made": state.get("tool_calls_made", 0) + len(calls)}

    async def hypothesize(state: TriageState) -> dict[str, Any]:
        """A plain reasoning turn before the structured one.

        Asking for prose first and structure second gives a weaker model somewhere to do
        the thinking, and leaves exactly one place where parsing can fail.
        """
        response = await llm.ainvoke([*state["messages"], HumanMessage(prompts.HYPOTHESIZE)])
        await trace(state, "hypothesize")
        return {"messages": [response]}

    async def propose(state: TriageState) -> dict[str, Any]:
        """Produce the structured recommendation and persist it as pending."""
        disposition, fallback = await _structured_disposition(llm, state["messages"], cap=2)

        await trace(
            state,
            "propose",
            tool_result=disposition.model_dump(mode="json"),
            error=fallback,
        )
        if on_propose is not None:
            await on_propose(state, disposition, fallback)

        return {
            "proposal": disposition.model_dump(mode="json"),
            "fallback_reason": fallback,
            "messages": [
                AIMessage(
                    f"Recommendation: {disposition.action} "
                    f"(confidence {disposition.confidence:.2f})"
                )
            ],
        }

    def human_review(state: TriageState) -> dict[str, Any]:
        """Pause for an engineer.

        This node contains one statement on purpose — see the module docstring. Do not
        add logging, persistence or metrics here.
        """
        decision = interrupt({"proposal": state.get("proposal"), "alarm_id": state["alarm_id"]})
        return {"review": decision}

    async def record_decision(state: TriageState) -> dict[str, Any]:
        review = state.get("review") or {}
        await trace(state, "record_decision", tool_result=review)
        if on_decision is not None:
            await on_decision(state, review)
        return {}

    # --- edges ------------------------------------------------------------

    def after_investigate(state: TriageState) -> Literal["tools", "hypothesize"]:
        last = state["messages"][-1]
        wants_tools = bool(getattr(last, "tool_calls", None))
        if wants_tools and state.get("tool_calls_made", 0) < cap:
            return "tools"
        return "hypothesize"

    builder = StateGraph(TriageState)
    builder.add_node("load_alarm", load_alarm)
    builder.add_node("investigate", investigate)
    builder.add_node("tools", run_tools)
    builder.add_node("hypothesize", hypothesize)
    builder.add_node("propose", propose)
    builder.add_node("human_review", human_review)
    builder.add_node("record_decision", record_decision)

    builder.add_edge(START, "load_alarm")
    builder.add_edge("load_alarm", "investigate")
    builder.add_conditional_edges("investigate", after_investigate)
    builder.add_edge("tools", "investigate")
    builder.add_edge("hypothesize", "propose")
    builder.add_edge("propose", "human_review")
    builder.add_edge("human_review", "record_decision")
    builder.add_edge("record_decision", END)

    return builder.compile(checkpointer=checkpointer)


# --- structured output with a safe fallback -------------------------------


async def _structured_disposition(
    llm: BaseChatModel, messages: list[AnyMessage], cap: int = 2
) -> tuple[Disposition, str | None]:
    """Ask for a Disposition, retrying once with the parser error fed back.

    Returns the disposition and, when the model never produced a valid one, the reason.
    The fallback is `escalate` at zero confidence: an agent that cannot reason about an
    alarm should hand it to a human, never wave the lot through with `continue`.
    """
    structured = llm.with_structured_output(Disposition)
    conversation = [*messages, HumanMessage(prompts.PROPOSE)]
    last_error = ""

    for attempt in range(cap):
        try:
            result = await structured.ainvoke(conversation)
            if isinstance(result, Disposition):
                return result, None
            return Disposition.model_validate(result), None
        except (ValidationError, ValueError, TypeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"[:400]
            if attempt + 1 < cap:
                conversation = [
                    *conversation,
                    HumanMessage(prompts.REPAIR.format(error=last_error)),
                ]

    return (
        Disposition(
            root_cause=None,
            action=Action.ESCALATE,
            confidence=0.0,
            hypothesis=(
                "The model did not return a usable structured recommendation, so this "
                "alarm is being escalated for a human to assess directly."
            ),
            evidence=[],
        ),
        last_error or "structured output failed",
    )


def _as_dict(value: Any) -> dict[str, Any]:
    """Unwrap an MCP tool result into a dict.

    Results arrive as content blocks — [{"type": "text", "text": "<json>"}] — with one
    block per list element, not as parsed objects.
    """
    import json

    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"error": value}
        return parsed if isinstance(parsed, dict) else {"items": parsed}
    if isinstance(value, list) and value and isinstance(value[0], dict):
        if value[0].get("type") == "text":
            items = []
            for block in value:
                try:
                    items.append(json.loads(block["text"]))
                except (json.JSONDecodeError, KeyError):
                    items.append(block.get("text"))
            return items[0] if len(items) == 1 and isinstance(items[0], dict) else {"items": items}
        return {"items": value}
    return {"value": value}


def _as_text(value: Any) -> str:
    """Flatten a tool result to the text the model will read."""
    import json

    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        texts = [block.get("text", "") for block in value if block.get("type") == "text"]
        if texts:
            return "\n".join(texts)
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return repr(value)
