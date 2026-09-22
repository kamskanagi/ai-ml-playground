"""MCP server exposing the mock MES as read-only tools.

Every tool is a thin call onto the backend's REST API rather than a database query, so
the dashboard and the agent read through one data-access path and MES query logic is
not duplicated here.

**Every tool is read-only.** Seven investigation tools plus `list_open_alarms`, which
lets the server be explored on its own from an MCP client. Writing a disposition is
deliberately not a tool: it is a node in the agent's graph calling the service layer
directly. The agent therefore has no way to record an approved decision by calling
something, whatever it decides.

Docstrings below are not documentation — they are the tool descriptions the model reads
when choosing what to call, so they say what a tool is for and how to read its output.
They deliberately stop short of naming which evidence implies which root cause; that is
the judgement being evaluated.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "9000"))
TIMEOUT = float(os.environ.get("MCP_TIMEOUT_S", "20"))

mcp = FastMCP("fab-mes", host=HOST, port=PORT)

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=TIMEOUT)
    return _client


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    """Call the backend, turning failures into values the model can act on.

    A tool that raises gives the agent a stack trace to reason about. A tool that
    returns {"error": ...} gives it a fact, which it can either work around or cite as
    a reason it could not reach a conclusion.
    """
    clean = {k: v for k, v in (params or {}).items() if v is not None}
    try:
        response = await get_client().get(path, params=clean)
    except httpx.RequestError as exc:
        return {"error": f"MES unreachable: {exc.__class__.__name__}: {exc}"}

    if response.status_code == 404:
        return {"error": f"Not found: {path}"}
    if response.status_code >= 400:
        return {"error": f"MES returned {response.status_code} for {path}"}
    return response.json()


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else value


# --- tools ----------------------------------------------------------------


@mcp.tool()
async def get_alarm(alarm_id: int) -> dict[str, Any]:
    """Fetch one alarm with its immediate context. Start an investigation here.

    Returns the alarm itself (code, severity, message, time raised), the tool and
    chamber it fired on, the lot that was being processed, the recipe that was running,
    the state of the equipment *as of the moment the alarm fired*, and every sensor that
    was outside its control limits on that run, each with its recent trend.

    The returned `run_id`, `equipment.id`, `lot_id` and `recipe_id` are what the other
    tools take as arguments.
    """
    return await _get(f"/api/alarms/{alarm_id}")


@mcp.tool()
async def get_sensor_trace(
    run_id: int,
    signals: list[str] | None = None,
    only_out_of_limit: bool = False,
) -> dict[str, Any]:
    """Sensor readings for a run, each with the preceding runs on the same tool.

    Every signal comes back with `current` and a `history` list running oldest to
    newest, ending on this run. The shape of that series is usually more informative
    than the single value: a steady climb, a one-off spike that returns to normal, and a
    value repeating identically run after run are three very different situations.

    `z_score` is how many standard deviations the reading sits from nominal; +/-3 is the
    control limit. Pass `signals` to restrict to named keys (for example
    ["chamber_pressure", "he_leak_rate"]), or `only_out_of_limit=True` for just the
    breaching ones.
    """
    return await _get(
        f"/api/runs/{run_id}/sensors",
        {"signals": signals, "only_out_of_limit": only_out_of_limit},
    )


@mcp.tool()
async def get_equipment_state(equipment_id: int, as_of: str | None = None) -> dict[str, Any]:
    """Condition of one tool, optionally at a past moment.

    Returns status, when it was last serviced and by whom, how many days of preventive
    maintenance interval have elapsed, whether that is overdue and by how much, and how
    many alarms it has raised in the preceding 30 days.

    Pass `as_of` (ISO-8601) to ask how the tool looked at that time. When investigating
    an alarm, pass the alarm's `raised_at`: a tool serviced yesterday still looked badly
    overdue when an alarm fired three weeks ago, and today's figure would be misleading.
    """
    return await _get(f"/api/equipment/{equipment_id}", {"as_of": _iso(as_of)})


@mcp.tool()
async def get_recent_recipe_changes(
    equipment_id: int, window_hours: float = 72.0, before: str | None = None
) -> list[dict[str, Any]] | dict[str, Any]:
    """Recipe parameter edits on a tool inside a time window.

    Each entry gives the parameter, its old and new values, who changed it, why, and
    `hours_before` the end of the window.

    Recipe tuning is routine, so every tool has changes somewhere in its history and the
    mere existence of one means little. What carries information is a change close in
    time to the alarm, on a parameter connected to the signal that moved. Pass `before`
    as the alarm's `raised_at` so the window ends at the alarm rather than now.
    """
    return await _get(
        f"/api/equipment/{equipment_id}/recipe-changes",
        {"window_hours": window_hours, "before": _iso(before)},
    )


@mcp.tool()
async def get_lot_history(lot_id: str, limit: int = 20) -> dict[str, Any]:
    """Where a lot has been: its recent runs, newest first, and how many alarms it has hit.

    Each run names the tool, chamber and recipe, gives the yield result where known, and
    lists any signals that were out of limit. Useful for telling a problem specific to
    this lot apart from one specific to the tool it happened to be on.

    `lot_id` is the printed identifier such as "L26-1119", not a numeric id.
    """
    return await _get(f"/api/lots/{lot_id}", {"limit": limit})


@mcp.tool()
async def find_similar_incidents(
    alarm_code: str | None = None, equipment_id: int | None = None, limit: int = 5
) -> list[dict[str, Any]] | dict[str, Any]:
    """Closed incidents from the past, with what was found and what was done.

    Filter by `alarm_code` to see how this kind of alarm resolved before. Pass
    `equipment_id` as well to sort incidents on the same chamber first, since a repeat on
    the same chamber is stronger evidence than the same code elsewhere in the bay.

    These are precedent, not proof: the same alarm code resolves to different causes on
    different occasions, so weigh them against the sensor evidence rather than copying
    the previous action.
    """
    return await _get(
        "/api/incidents",
        {"alarm_code": alarm_code, "equipment_id": equipment_id, "limit": limit},
    )


@mcp.tool()
async def get_recipe(recipe_id: int) -> dict[str, Any]:
    """The recipe a run used, with its current parameter setpoints.

    Use it to check a measured value against what the process was actually asking for —
    a reading can sit inside its control limits and still be far from the recipe's
    setpoint. `get_alarm` returns the `recipe_id` for the run that alarmed.
    """
    return await _get(f"/api/recipes/{recipe_id}")


@mcp.tool()
async def list_open_alarms(limit: int = 20) -> list[dict[str, Any]] | dict[str, Any]:
    """The current alarm queue, newest first. Use it to find an alarm id to investigate."""
    return await _get("/api/alarms", {"status": "open", "limit": limit})


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
