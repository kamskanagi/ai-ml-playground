"""MCP tool tests against a stubbed backend.

No database and no running API: respx intercepts the HTTP calls, so these run fast and
assert on exactly what each tool asks the MES for.
"""

from __future__ import annotations

import httpx
import pytest
import respx

import server

BASE = server.BACKEND_URL

# Seven investigation tools plus the queue browser.
EXPECTED_TOOLS = {
    "get_alarm",
    "get_sensor_trace",
    "get_equipment_state",
    "get_recent_recipe_changes",
    "get_lot_history",
    "find_similar_incidents",
    "get_recipe",
    "list_open_alarms",
}


@pytest.fixture(autouse=True)
def reset_client():
    """The httpx client is cached module-level; drop it so each test gets a clean one."""
    server._client = None
    yield
    server._client = None


# --- inventory ------------------------------------------------------------


async def test_exactly_the_expected_tools_are_exposed():
    names = {t.name for t in await server.mcp.list_tools()}
    assert names == EXPECTED_TOOLS


async def test_every_tool_has_a_description():
    """Descriptions are the model's instructions for choosing a tool, not decoration."""
    for tool in await server.mcp.list_tools():
        assert tool.description and len(tool.description.strip()) > 40, tool.name


@respx.mock
async def test_no_tool_can_write():
    """The safety property: the agent must not be able to change MES state.

    Any non-GET would raise here, since only GET is routed.
    """
    respx.get(url__regex=rf"{BASE}/.*").mock(return_value=httpx.Response(200, json={}))

    await server.get_alarm(1)
    await server.get_sensor_trace(1)
    await server.get_equipment_state(1)
    await server.get_recent_recipe_changes(1)
    await server.get_lot_history("L26-1000")
    await server.find_similar_incidents("HE_LEAK_HIGH")
    await server.get_recipe(1)
    await server.list_open_alarms()

    assert respx.calls.call_count == 8
    assert {c.request.method for c in respx.calls} == {"GET"}


# --- request shaping ------------------------------------------------------


@respx.mock
async def test_get_alarm_requests_the_alarm_endpoint():
    route = respx.get(f"{BASE}/api/alarms/42").mock(
        return_value=httpx.Response(200, json={"id": 42, "alarm_code": "HE_LEAK_HIGH"})
    )
    assert (await server.get_alarm(42))["id"] == 42
    assert route.called


@respx.mock
async def test_optional_arguments_are_omitted_rather_than_sent_as_null():
    """A literal `as_of=None` in the query string would be parsed as a bad datetime."""
    route = respx.get(f"{BASE}/api/equipment/7").mock(
        return_value=httpx.Response(200, json={"id": 7})
    )
    await server.get_equipment_state(7)
    assert "as_of" not in route.calls[0].request.url.params


@respx.mock
async def test_as_of_is_forwarded_when_given():
    route = respx.get(f"{BASE}/api/equipment/7").mock(
        return_value=httpx.Response(200, json={"id": 7})
    )
    await server.get_equipment_state(7, as_of="2026-09-20T22:26:21Z")
    assert route.calls[0].request.url.params["as_of"] == "2026-09-20T22:26:21Z"


@respx.mock
async def test_datetime_objects_are_serialised_to_iso():
    """The model sends strings, but a Python caller may pass a datetime."""
    from datetime import UTC, datetime

    route = respx.get(f"{BASE}/api/equipment/7/recipe-changes").mock(
        return_value=httpx.Response(200, json=[])
    )
    await server.get_recent_recipe_changes(
        7, window_hours=8, before=datetime(2026, 9, 20, 22, 26, tzinfo=UTC)
    )
    params = route.calls[0].request.url.params
    assert params["before"].startswith("2026-09-20T22:26")
    assert float(params["window_hours"]) == 8.0


@respx.mock
async def test_sensor_trace_forwards_signal_filters():
    route = respx.get(f"{BASE}/api/runs/99/sensors").mock(
        return_value=httpx.Response(200, json={"run_id": 99, "signals": []})
    )
    await server.get_sensor_trace(99, signals=["chamber_pressure", "he_leak_rate"])
    params = route.calls[0].request.url
    assert "chamber_pressure" in str(params)
    assert "he_leak_rate" in str(params)


@respx.mock
async def test_find_similar_incidents_sends_only_the_given_filters():
    route = respx.get(f"{BASE}/api/incidents").mock(return_value=httpx.Response(200, json=[]))
    await server.find_similar_incidents(alarm_code="HE_LEAK_HIGH")
    params = route.calls[0].request.url.params
    assert params["alarm_code"] == "HE_LEAK_HIGH"
    assert "equipment_id" not in params


@respx.mock
async def test_lot_history_uses_the_printed_lot_identifier():
    route = respx.get(f"{BASE}/api/lots/L26-1119").mock(
        return_value=httpx.Response(200, json={"lot": {"lot_id": "L26-1119"}, "runs": []})
    )
    await server.get_lot_history("L26-1119")
    assert route.called


# --- failure behaviour ----------------------------------------------------


@respx.mock
async def test_missing_record_returns_an_error_value_not_an_exception():
    """The agent should be able to reason about a miss, not crash on it."""
    respx.get(f"{BASE}/api/alarms/999999").mock(return_value=httpx.Response(404))
    result = await server.get_alarm(999999)
    assert "error" in result
    assert "Not found" in result["error"]


@respx.mock
async def test_server_error_is_reported_with_its_status():
    respx.get(f"{BASE}/api/recipes/1").mock(return_value=httpx.Response(500))
    result = await server.get_recipe(1)
    assert "500" in result["error"]


@respx.mock
async def test_unreachable_mes_is_reported_as_a_fact():
    respx.get(f"{BASE}/api/alarms/1").mock(side_effect=httpx.ConnectError("refused"))
    result = await server.get_alarm(1)
    assert "MES unreachable" in result["error"]
