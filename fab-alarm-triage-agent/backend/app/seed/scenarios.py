"""Fault scenarios with ground truth known by construction.

Each generator describes an alarm and the corroborating evidence planted around it:
which signals move and by how much, on the alarm run and on the preceding runs of the
same tool; whether a recipe change happened shortly before; whether the tool is overdue
for PM; whether a matching past incident exists.

Because the fault is planted rather than discovered, the correct disposition and root
cause are known exactly, which is what makes the eval harness meaningful.

Two discriminations are deliberate and are the reason this is not a lookup table:

* `recipe_param_drift` and `no_fault_false_alarm` share PRESSURE_EXCURSION but need
  opposite actions. The tell is a recipe change plus a multi-run ramp versus a single
  marginal point that recovers.
* `pm_overdue_wear` (escalate) and `rf_match_degradation` (hold_lot) share
  RF_REFLECTED_HIGH but need different actions. The tell is PM status plus a slow
  multi-run ramp versus a sudden single-run step with both match positions at rail.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from app.domain import Action, AlarmCode, RootCause, Severity


@dataclass(frozen=True)
class Perturbation:
    """Force one signal to a z-score on a run relative to the alarm run.

    `run_offset` counts back through the runs of the *same tool*: 0 is the alarm run,
    -1 the tool's previous run. A z beyond +/-3 lands outside the control limits.
    """

    signal_key: str
    z: float
    run_offset: int = 0


@dataclass(frozen=True)
class RecipeChangeSpec:
    param: str
    old_value: str
    new_value: str
    hours_before: float
    reason: str


@dataclass(frozen=True)
class ScenarioPlan:
    scenario: str
    root_cause: RootCause
    action: Action
    alarm_code: AlarmCode
    severity: Severity
    message: str
    perturbations: tuple[Perturbation, ...]
    recipe_change: RecipeChangeSpec | None = None
    # current | overdue | unchanged
    pm_state: str = "current"
    pm_overdue_days: int = 0
    plant_similar_incident: bool = False
    # Override the SECOM yield label when the label is itself part of the evidence.
    force_yield: str | None = None
    # Preceding runs on the same tool this scenario needs in order to be discoverable.
    required_history: int = field(default=0)

    def __post_init__(self) -> None:
        depth = max((-p.run_offset for p in self.perturbations), default=0)
        object.__setattr__(self, "required_history", depth)


def _recipe_param_drift(rng: random.Random) -> ScenarioPlan:
    """Someone widened a gas flow a few hours ago and the chamber has drifted since."""
    old = rng.uniform(98.0, 102.0)
    new = old + rng.uniform(8.0, 14.0)
    return ScenarioPlan(
        scenario="recipe_param_drift",
        root_cause=RootCause.RECIPE_PARAM_DRIFT,
        action=Action.HOLD_LOT,
        alarm_code=AlarmCode.PRESSURE_EXCURSION,
        severity=Severity.HIGH,
        message="Chamber pressure above upper control limit",
        perturbations=(
            Perturbation("chamber_pressure", rng.uniform(3.6, 5.0)),
            Perturbation("cf4_flow", rng.uniform(3.4, 4.6)),
            Perturbation("endpoint_intensity", rng.uniform(-3.8, -3.2)),
            Perturbation("chamber_pressure", rng.uniform(2.1, 2.8), run_offset=-1),
            Perturbation("cf4_flow", rng.uniform(2.0, 2.9), run_offset=-1),
            Perturbation("chamber_pressure", rng.uniform(1.4, 2.0), run_offset=-2),
        ),
        recipe_change=RecipeChangeSpec(
            param="cf4_flow_sccm",
            old_value=f"{old:.1f}",
            new_value=f"{new:.1f}",
            hours_before=rng.uniform(2.0, 6.0),
            reason="Etch rate centering request",
        ),
        pm_state="current",
    )


def _pm_overdue_wear(rng: random.Random) -> ScenarioPlan:
    """Consumable parts are past their service interval; reflected power creeps up."""
    return ScenarioPlan(
        scenario="pm_overdue_wear",
        root_cause=RootCause.PM_OVERDUE_WEAR,
        action=Action.ESCALATE,
        alarm_code=AlarmCode.RF_REFLECTED_HIGH,
        severity=Severity.MEDIUM,
        message="RF reflected power trending above control limit",
        perturbations=(
            Perturbation("rf_reflected_power", rng.uniform(3.3, 4.2)),
            Perturbation("match_position_c1", rng.uniform(3.0, 3.8)),
            Perturbation("chamber_wall_temp", rng.uniform(2.4, 3.1)),
            Perturbation("rf_reflected_power", rng.uniform(2.4, 3.0), run_offset=-1),
            Perturbation("rf_reflected_power", rng.uniform(1.8, 2.4), run_offset=-2),
            Perturbation("rf_reflected_power", rng.uniform(1.2, 1.8), run_offset=-3),
        ),
        pm_state="overdue",
        pm_overdue_days=rng.randint(9, 26),
    )


def _chamber_leak(rng: random.Random) -> ScenarioPlan:
    """Vacuum integrity loss: helium up, pressure up, throttle valve closing to hold setpoint."""
    return ScenarioPlan(
        scenario="chamber_leak",
        root_cause=RootCause.CHAMBER_LEAK,
        action=Action.HOLD_LOT,
        alarm_code=AlarmCode.HE_LEAK_HIGH,
        severity=Severity.CRITICAL,
        message="Helium leak rate above upper control limit",
        perturbations=(
            Perturbation("he_leak_rate", rng.uniform(4.0, 5.5)),
            Perturbation("chamber_pressure", rng.uniform(3.2, 4.4)),
            Perturbation("throttle_valve_angle", rng.uniform(-3.9, -3.2)),
            Perturbation("he_leak_rate", rng.uniform(2.2, 3.0), run_offset=-1),
        ),
        pm_state="current",
        plant_similar_incident=True,
    )


def _sensor_malfunction(rng: random.Random) -> ScenarioPlan:
    """A thermocouple has railed. Nothing else moved and the wafers came out fine."""
    railed = rng.uniform(7.5, 8.5)
    return ScenarioPlan(
        scenario="sensor_malfunction",
        root_cause=RootCause.SENSOR_MALFUNCTION,
        action=Action.CONTINUE,
        alarm_code=AlarmCode.CHUCK_TEMP_OOR,
        severity=Severity.MEDIUM,
        message="Chuck temperature out of range",
        perturbations=(
            # Identical value three runs running: a reading that is stuck, not a process
            # that is drifting.
            Perturbation("chuck_temp", railed),
            Perturbation("chuck_temp", railed, run_offset=-1),
            Perturbation("chuck_temp", railed, run_offset=-2),
        ),
        pm_state="current",
        force_yield="pass",
    )


def _no_fault_false_alarm(rng: random.Random) -> ScenarioPlan:
    """A single marginal point that recovers on its own. Nothing is wrong."""
    return ScenarioPlan(
        scenario="no_fault_false_alarm",
        root_cause=RootCause.NO_FAULT_FALSE_ALARM,
        action=Action.CONTINUE,
        alarm_code=AlarmCode.PRESSURE_EXCURSION,
        severity=Severity.LOW,
        message="Chamber pressure above upper control limit",
        perturbations=(Perturbation("chamber_pressure", rng.uniform(3.05, 3.25)),),
        pm_state="current",
        force_yield="pass",
    )


def _gas_flow_instability(rng: random.Random) -> ScenarioPlan:
    """Mass flow controller hunting: flows swing either side of setpoint run to run."""
    return ScenarioPlan(
        scenario="gas_flow_instability",
        root_cause=RootCause.GAS_FLOW_INSTABILITY,
        # Flows oscillate either side of setpoint, so net dose is likely recoverable:
        # the tool needs a technician, the lot does not need freezing.
        action=Action.ESCALATE,
        alarm_code=AlarmCode.GAS_FLOW_UNSTABLE,
        severity=Severity.HIGH,
        message="Process gas flow unstable across consecutive runs",
        perturbations=(
            # Alternating signs: oscillation, not the monotone ramp of a recipe change.
            Perturbation("cf4_flow", rng.uniform(3.4, 4.2)),
            Perturbation("o2_flow", rng.uniform(-4.2, -3.4)),
            Perturbation("cf4_flow", rng.uniform(-3.8, -3.1), run_offset=-1),
            Perturbation("o2_flow", rng.uniform(3.2, 4.0), run_offset=-1),
            Perturbation("cf4_flow", rng.uniform(3.2, 3.9), run_offset=-2),
        ),
        pm_state="current",
    )


def _rf_match_degradation(rng: random.Random) -> ScenarioPlan:
    """Match network failing: both capacitor positions at rail, and it happened suddenly."""
    return ScenarioPlan(
        scenario="rf_match_degradation",
        root_cause=RootCause.RF_MATCH_DEGRADATION,
        # A sudden match failure means this lot saw the wrong delivered power.
        action=Action.HOLD_LOT,
        alarm_code=AlarmCode.RF_REFLECTED_HIGH,
        severity=Severity.HIGH,
        message="RF reflected power above upper control limit",
        perturbations=(
            Perturbation("rf_reflected_power", rng.uniform(3.5, 4.4)),
            Perturbation("match_position_c1", rng.uniform(3.4, 4.2)),
            Perturbation("match_position_c2", rng.uniform(3.3, 4.1)),
        ),
        # PM is current, which is what separates this from pm_overdue_wear.
        pm_state="current",
    )


GENERATORS: dict[str, Callable[[random.Random], ScenarioPlan]] = {
    "recipe_param_drift": _recipe_param_drift,
    "pm_overdue_wear": _pm_overdue_wear,
    "chamber_leak": _chamber_leak,
    "sensor_malfunction": _sensor_malfunction,
    "no_fault_false_alarm": _no_fault_false_alarm,
    "gas_flow_instability": _gas_flow_instability,
    "rf_match_degradation": _rf_match_degradation,
}

SCENARIO_NAMES = tuple(GENERATORS)


def build_plan(scenario: str, rng: random.Random) -> ScenarioPlan:
    return GENERATORS[scenario](rng)


def balanced_scenario_cycle(count: int, rng: random.Random) -> list[str]:
    """Pick `count` scenarios, keeping every scenario roughly equally represented.

    Sampling independently would leave some scenarios with one or two cases in a
    30-alarm eval set, which makes per-cause accuracy meaningless.
    """
    names = list(SCENARIO_NAMES)
    out: list[str] = []
    while len(out) < count:
        block = names[:]
        rng.shuffle(block)
        out.extend(block)
    return out[:count]
