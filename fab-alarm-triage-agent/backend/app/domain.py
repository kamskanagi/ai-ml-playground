"""Fixed domain vocabulary.

These enums are the contract between the seeder, the agent, the API and the eval
harness. Changing a member invalidates existing eval cases and logged dispositions,
so treat them as versioned data, not as incidental strings.
"""

from enum import StrEnum


class Action(StrEnum):
    """What the engineer (or the agent) decides to do with the lot."""

    HOLD_LOT = "hold_lot"
    CONTINUE = "continue"
    ESCALATE = "escalate"


class RootCause(StrEnum):
    """Root-cause taxonomy used for hypotheses and eval scoring."""

    RECIPE_PARAM_DRIFT = "recipe_param_drift"
    PM_OVERDUE_WEAR = "pm_overdue_wear"
    CHAMBER_LEAK = "chamber_leak"
    SENSOR_MALFUNCTION = "sensor_malfunction"
    GAS_FLOW_INSTABILITY = "gas_flow_instability"
    RF_MATCH_DEGRADATION = "rf_match_degradation"
    NO_FAULT_FALSE_ALARM = "no_fault_false_alarm"


class AlarmStatus(StrEnum):
    OPEN = "open"
    TRIAGED = "triaged"
    CLOSED = "closed"


class LotStatus(StrEnum):
    RUNNING = "running"
    HOLD = "hold"
    RELEASED = "released"


class EquipmentStatus(StrEnum):
    UP = "up"
    DOWN = "down"
    MAINTENANCE = "maintenance"


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"


class DispositionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
