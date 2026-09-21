"""MES endpoint tests.

The first test is the important one: ground truth lives on the `alarms` row, and a
leak would not fail anything — it would quietly make every eval number meaningless.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.db.models import Alarm

# Column names the agent must never observe, plus the substrings a careless future
# schema would most likely introduce.
FORBIDDEN_KEYS = {"truth_root_cause", "truth_action", "scenario", "is_eval_case"}
FORBIDDEN_SUBSTRINGS = ("truth", "ground_truth", "is_eval")


def _walk_keys(payload, found: set[str]) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.add(key)
            _walk_keys(value, found)
    elif isinstance(payload, list):
        for item in payload:
            _walk_keys(item, found)


async def _every_endpoint(client) -> list[tuple[str, object]]:
    alarms = (await client.get("/api/alarms")).json()
    alarm_id = alarms[0]["id"]
    detail = (await client.get(f"/api/alarms/{alarm_id}")).json()
    run_id = detail["run_id"]
    equipment_id = detail["equipment"]["id"]
    lot_id = detail["lot_id"]

    recipe_id = (await client.get("/api/recipes")).json()[0]["id"]

    paths = [
        "/api/alarms",
        "/api/alarms?include_eval=true",
        f"/api/alarms/{alarm_id}",
        "/api/equipment",
        f"/api/equipment/{equipment_id}",
        f"/api/equipment/{equipment_id}/recipe-changes?window_hours=2160",
        "/api/lots",
        f"/api/lots/{lot_id}",
        f"/api/runs/{run_id}/sensors",
        "/api/recipes",
        f"/api/recipes/{recipe_id}",
        "/api/incidents",
    ]
    return [(path, (await client.get(path)).json()) for path in paths]


async def test_no_endpoint_leaks_ground_truth(client):
    for path, payload in await _every_endpoint(client):
        keys: set[str] = set()
        _walk_keys(payload, keys)
        assert not (keys & FORBIDDEN_KEYS), f"{path} exposes {keys & FORBIDDEN_KEYS}"
        for key in keys:
            lowered = key.lower()
            assert not any(bad in lowered for bad in FORBIDDEN_SUBSTRINGS), f"{path} -> {key}"


async def test_every_endpoint_returns_200(client):
    for path, _ in await _every_endpoint(client):
        assert (await client.get(path)).status_code == 200, path


# --- alarm queue ----------------------------------------------------------


async def test_alarm_queue_hides_eval_cases_by_default(client, session):
    default = (await client.get("/api/alarms?limit=500")).json()
    with_eval = (await client.get("/api/alarms?limit=500&include_eval=true")).json()
    assert len(with_eval) > len(default)

    eval_ids = set(
        (await session.execute(select(Alarm.id).where(Alarm.is_eval_case.is_(True)))).scalars()
    )
    assert not {a["id"] for a in default} & eval_ids


async def test_alarm_queue_filters_by_status(client):
    rows = (await client.get("/api/alarms?status=open&limit=500")).json()
    assert rows
    assert all(a["status"] == "open" for a in rows)


async def test_unknown_alarm_returns_404(client):
    assert (await client.get("/api/alarms/999999")).status_code == 404


# --- point-in-time equipment state ---------------------------------------


async def test_alarm_detail_reports_pm_age_at_alarm_time_not_now(client):
    """An alarm raised weeks ago must not be described using today's PM age."""
    alarms = (await client.get("/api/alarms?limit=500")).json()
    oldest = min(alarms, key=lambda a: a["raised_at"])
    detail = (await client.get(f"/api/alarms/{oldest['id']}")).json()

    assert detail["equipment"]["as_of"] == detail["raised_at"]

    now_state = (await client.get(f"/api/equipment/{detail['equipment']['id']}")).json()
    raised = datetime.fromisoformat(detail["raised_at"])
    age_gap = (datetime.fromisoformat(now_state["as_of"]) - raised).days
    if age_gap > 2 and now_state["days_since_pm"] is not None:
        assert detail["equipment"]["days_since_pm"] != now_state["days_since_pm"]


async def test_equipment_state_accepts_an_as_of_override(client):
    equipment = (await client.get("/api/equipment")).json()[0]
    at_now = (await client.get(f"/api/equipment/{equipment['id']}")).json()
    old = (await client.get(f"/api/equipment/{equipment['id']}?as_of=2020-01-01T00:00:00Z")).json()
    assert old["days_since_pm"] is None or old["days_since_pm"] < at_now["days_since_pm"]


async def test_unknown_equipment_returns_404(client):
    assert (await client.get("/api/equipment/999999")).status_code == 404


# --- sensors --------------------------------------------------------------


async def test_sensor_trace_carries_history_for_each_signal(client):
    detail = (await client.get("/api/alarms")).json()[0]
    trace = (await client.get(f"/api/runs/{detail['run_id']}/sensors")).json()

    assert trace["signals"]
    for signal in trace["signals"]:
        assert signal["history"], signal["signal_key"]
        assert signal["history"][-1]["run_id"] == trace["run_id"], "current run ends the series"
        stamps = [p["started_at"] for p in signal["history"]]
        assert stamps == sorted(stamps), "history must read oldest to newest"


async def test_sensor_trace_can_restrict_to_named_signals(client):
    detail = (await client.get("/api/alarms")).json()[0]
    trace = (
        await client.get(f"/api/runs/{detail['run_id']}/sensors?signals=chamber_pressure")
    ).json()
    assert [s["signal_key"] for s in trace["signals"]] == ["chamber_pressure"]


async def test_alarm_detail_lists_only_breaching_signals(client):
    alarms = (await client.get("/api/alarms?limit=500")).json()
    detail = (await client.get(f"/api/alarms/{alarms[0]['id']}")).json()
    assert detail["out_of_limit"]
    for signal in detail["out_of_limit"]:
        current = signal["current"]
        assert current["out_of_limit"]
        assert current["value"] > signal["ucl"] or current["value"] < signal["lcl"]


# --- recipe changes -------------------------------------------------------


async def test_recipe_change_window_is_bounded_by_before(client):
    alarms = (await client.get("/api/alarms?limit=500")).json()
    detail = (await client.get(f"/api/alarms/{alarms[0]['id']}")).json()
    equipment_id = detail["equipment"]["id"]

    wide = (
        await client.get(
            f"/api/equipment/{equipment_id}/recipe-changes"
            f"?window_hours=2160&before={detail['raised_at']}"
        )
    ).json()
    narrow = (
        await client.get(
            f"/api/equipment/{equipment_id}/recipe-changes"
            f"?window_hours=8&before={detail['raised_at']}"
        )
    ).json()

    assert len(narrow) <= len(wide)
    for change in wide:
        assert change["changed_at"] <= detail["raised_at"]
        assert change["hours_before"] >= 0


# --- lots and incidents ---------------------------------------------------


async def test_lot_history_returns_runs_newest_first(client):
    lots = (await client.get("/api/lots")).json()
    history = (await client.get(f"/api/lots/{lots[0]['lot_id']}")).json()
    assert history["lot"]["lot_id"] == lots[0]["lot_id"]
    stamps = [r["started_at"] for r in history["runs"]]
    assert stamps == sorted(stamps, reverse=True)


async def test_unknown_lot_returns_404(client):
    assert (await client.get("/api/lots/NOPE-0000")).status_code == 404


@pytest.mark.parametrize("code", ["HE_LEAK_HIGH", "RF_REFLECTED_HIGH"])
async def test_incidents_filter_by_alarm_code(client, code):
    rows = (await client.get(f"/api/incidents?alarm_code={code}")).json()
    assert rows
    assert all(r["alarm_code"] == code for r in rows)


async def test_incidents_prefer_the_same_tool(client):
    alarms = (await client.get("/api/alarms?limit=500")).json()
    detail = (await client.get(f"/api/alarms/{alarms[0]['id']}")).json()
    equipment_id = detail["equipment"]["id"]
    rows = (await client.get(f"/api/incidents?equipment_id={equipment_id}&limit=5")).json()
    assert rows
    same_tool = [r for r in rows if r["tool_id"] == detail["tool_id"]]
    if same_tool:
        assert rows[0]["tool_id"] == detail["tool_id"]
