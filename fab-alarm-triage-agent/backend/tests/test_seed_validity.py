"""Eval-validity invariants for the seeded dataset.

These are not "does the seeder run" tests. Each one guards a way the dataset could
silently become solvable by a heuristic instead of by reasoning — which would inflate
every accuracy number in the eval harness without anything failing.
"""

from __future__ import annotations

from sqlalchemy import func, select, text

from app.db.models import Alarm, Equipment, PmEvent, RecipeChange, SensorReading
from app.domain import Action, AlarmCode, RootCause
from app.seed.scenarios import SCENARIO_NAMES
from app.seed.secom import signals_by_key

# pm_overdue_wear plants 30 + 9..26 days; ordinary PM jitter tops out near the interval.
CLEARLY_OVERDUE_DAYS = 40


async def test_every_scenario_appears_in_the_eval_set(session):
    rows = await session.execute(
        select(Alarm.scenario, func.count())
        .where(Alarm.is_eval_case.is_(True))
        .group_by(Alarm.scenario)
    )
    counts = dict(rows.all())
    assert set(counts) == set(SCENARIO_NAMES)
    # A scenario with one case makes its per-cause accuracy meaningless.
    assert min(counts.values()) >= 2, counts


async def test_all_alarms_carry_ground_truth(session):
    missing = await session.scalar(
        select(func.count()).where(
            (Alarm.truth_action.is_(None))
            | (Alarm.truth_root_cause.is_(None))
            | (Alarm.scenario.is_(None))
        )
    )
    assert missing == 0


async def test_ground_truth_action_matches_root_cause_consistently(session):
    """One root cause must always imply the same action, or scoring is incoherent."""
    rows = await session.execute(
        select(Alarm.truth_root_cause, func.count(func.distinct(Alarm.truth_action))).group_by(
            Alarm.truth_root_cause
        )
    )
    for cause, distinct_actions in rows.all():
        assert distinct_actions == 1, f"{cause} maps to {distinct_actions} different actions"


async def test_demo_and_eval_sets_are_disjoint(session):
    rows = await session.execute(
        select(Alarm.run_id, func.count(func.distinct(Alarm.is_eval_case)))
        .group_by(Alarm.run_id)
        .having(func.count(func.distinct(Alarm.is_eval_case)) > 1)
    )
    assert rows.all() == []


async def test_no_two_alarms_share_a_run(session):
    rows = await session.execute(
        select(Alarm.run_id).group_by(Alarm.run_id).having(func.count() > 1)
    )
    assert rows.all() == [], "overlapping alarms would overwrite each other's evidence"


# --- the discriminations that make this a reasoning task ------------------


async def test_shared_alarm_codes_span_more_than_one_action(session):
    """The alarm code alone must never determine the answer."""
    rows = await session.execute(
        select(Alarm.alarm_code, func.count(func.distinct(Alarm.truth_action))).group_by(
            Alarm.alarm_code
        )
    )
    spans = dict(rows.all())
    assert spans[AlarmCode.PRESSURE_EXCURSION] > 1
    assert spans[AlarmCode.RF_REFLECTED_HIGH] > 1


async def test_existence_of_a_recipe_change_predicts_nothing(session):
    """Every tool must have recipe changes, or the table's emptiness is the answer."""
    tools_with_alarms = set(
        (await session.execute(select(func.distinct(Alarm.equipment_id)))).scalars()
    )
    tools_with_changes = set(
        (await session.execute(select(func.distinct(RecipeChange.equipment_id)))).scalars()
    )
    assert tools_with_alarms <= tools_with_changes


async def test_a_recent_recipe_change_is_still_a_real_signal(session):
    """Recency must remain informative even though existence is not."""
    recent = text(
        """
        SELECT a.scenario,
               EXISTS (SELECT 1 FROM recipe_changes rc
                       WHERE rc.equipment_id = a.equipment_id
                         AND rc.changed_at BETWEEN a.raised_at - interval '8 hours'
                                               AND a.raised_at) AS had_change
        FROM alarms a
        """
    )
    rows = (await session.execute(recent)).all()
    drift = [had for scenario, had in rows if scenario == "recipe_param_drift"]
    other = [had for scenario, had in rows if scenario != "recipe_param_drift"]

    assert all(drift), "every recipe_param_drift alarm needs its planted change"
    # Some incidental overlap is realistic; a majority would destroy the signal.
    assert sum(other) / len(other) < 0.25


async def test_pm_status_separates_the_two_rf_scenarios(session):
    """pm_overdue_wear and rf_match_degradation share an alarm code; PM age splits them."""
    days_since_pm = text(
        """
        SELECT a.scenario,
               EXTRACT(EPOCH FROM (a.raised_at - (
                   SELECT max(p.performed_at) FROM pm_events p
                   WHERE p.equipment_id = a.equipment_id
                     AND p.performed_at <= a.raised_at))) / 86400 AS days
        FROM alarms a
        WHERE a.alarm_code = :code
        """
    )
    rows = (await session.execute(days_since_pm, {"code": AlarmCode.RF_REFLECTED_HIGH})).all()
    wear = [d for s, d in rows if s == "pm_overdue_wear"]
    match = [d for s, d in rows if s == "rf_match_degradation"]

    assert wear and match
    assert all(d is not None and d > CLEARLY_OVERDUE_DAYS for d in wear)
    assert all(d is not None and d <= CLEARLY_OVERDUE_DAYS for d in match)


async def test_every_alarm_has_a_prior_pm_record(session):
    """A NULL PM date reads as 'unknown', not 'overdue', and silently breaks the signal."""
    orphans = await session.scalar(
        text(
            """
            SELECT count(*) FROM alarms a
            WHERE NOT EXISTS (
                SELECT 1 FROM pm_events p
                WHERE p.equipment_id = a.equipment_id AND p.performed_at <= a.raised_at)
            """
        )
    )
    assert orphans == 0


# --- planted evidence actually landed -------------------------------------


async def test_every_alarm_run_has_an_out_of_limit_signal(session):
    """An alarm with nothing out of limit is unsolvable."""
    rows = (
        await session.execute(
            text(
                """
                SELECT a.id, count(*) FILTER (
                    WHERE s.raw_value > s.ucl OR s.raw_value < s.lcl) AS breaches
                FROM alarms a JOIN sensor_readings s ON s.run_id = a.run_id
                GROUP BY a.id
                """
            )
        )
    ).all()
    assert rows
    assert all(breaches >= 1 for _, breaches in rows)


async def test_sensor_values_and_z_scores_stay_consistent(session):
    """Perturbation must update value and z together, as the loader does."""
    by_key = signals_by_key()
    rows = (
        await session.execute(
            select(
                SensorReading.signal_key, SensorReading.raw_value, SensorReading.z_score
            ).limit(3000)
        )
    ).all()
    assert rows
    for key, value, z in rows:
        assert abs(by_key[key].z_of(value) - z) < 1e-6, key


async def test_sensor_malfunction_leaves_other_signals_in_control(session):
    """Its whole tell is that only one signal moved."""
    rows = (
        await session.execute(
            text(
                """
                SELECT s.signal_key, count(*) FILTER (
                    WHERE s.raw_value > s.ucl OR s.raw_value < s.lcl) AS breaches
                FROM alarms a JOIN sensor_readings s ON s.run_id = a.run_id
                WHERE a.scenario = 'sensor_malfunction'
                GROUP BY s.signal_key
                """
            )
        )
    ).all()
    breaching = {key for key, breaches in rows if breaches}
    assert breaching == {"chuck_temp"}, breaching


async def test_reference_data_is_present(session):
    assert await session.scalar(select(func.count()).select_from(Equipment)) >= 6
    assert await session.scalar(select(func.count()).select_from(PmEvent)) > 0
    causes = set(
        (
            await session.execute(
                text("SELECT DISTINCT root_cause_category FROM incidents")
            )
        ).scalars()
    )
    assert causes == {c.value for c in RootCause}, "incident corpus must cover every root cause"


async def test_actions_are_from_the_fixed_vocabulary(session):
    actions = set((await session.execute(select(func.distinct(Alarm.truth_action)))).scalars())
    assert actions <= {a.value for a in Action}
    assert len(actions) == 3, "all three dispositions should be exercised"
