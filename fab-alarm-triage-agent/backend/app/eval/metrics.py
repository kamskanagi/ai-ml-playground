"""Scoring for a triage evaluation run.

Pure functions over a list of `CaseResult`, so the numbers can be tested exactly without
a database or a model.

Accuracy is not the headline. The headline is `unsafe_continue_rate`: how often the agent
said `continue` about a lot that should have been held. Those two errors are not
symmetric — a wrong `hold_lot` delays a lot, a wrong `continue` scraps 25 wafers — so
averaging them into one accuracy figure hides the only failure that is expensive.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from statistics import mean

from app.domain import Action, RootCause

ACTIONS = [a.value for a in Action]
CAUSES = [c.value for c in RootCause]
# A proposal citing fewer than this is not reviewable: an engineer cannot check it.
MIN_EVIDENCE = 2


@dataclass
class CaseResult:
    """One graded alarm."""

    alarm_id: int
    alarm_code: str
    scenario: str
    expected_action: str
    expected_root_cause: str
    predicted_action: str
    predicted_root_cause: str | None
    confidence: float
    evidence_count: int
    tool_calls: int
    latency_ms: int
    fallback: bool = False
    error: str | None = None

    @property
    def action_correct(self) -> bool:
        return self.predicted_action == self.expected_action

    @property
    def cause_correct(self) -> bool:
        return self.predicted_root_cause == self.expected_root_cause


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def per_class_f1(results: list[CaseResult]) -> dict[str, dict[str, float]]:
    """Precision, recall and F1 per action."""
    out: dict[str, dict[str, float]] = {}
    for action in ACTIONS:
        tp = sum(1 for r in results if r.predicted_action == action == r.expected_action)
        fp = sum(1 for r in results if r.predicted_action == action and r.expected_action != action)
        fn = sum(1 for r in results if r.expected_action == action and r.predicted_action != action)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        out[action] = {
            "precision": precision,
            "recall": recall,
            "f1": _safe_div(2 * precision * recall, precision + recall),
            "support": tp + fn,
        }
    return out


def confusion(results: list[CaseResult]) -> dict[str, dict[str, int]]:
    """expected -> predicted -> count, over actions."""
    matrix = {e: dict.fromkeys(ACTIONS, 0) for e in ACTIONS}
    for r in results:
        if r.expected_action in matrix and r.predicted_action in matrix[r.expected_action]:
            matrix[r.expected_action][r.predicted_action] += 1
    return matrix


def ambiguous_codes(results: list[CaseResult]) -> set[str]:
    """Alarm codes that span more than one correct action in this set.

    Everything else can be answered from the code alone, so those cases say nothing about
    whether the agent reasoned — they only say it can read a label.
    """
    by_code: dict[str, set[str]] = {}
    for r in results:
        by_code.setdefault(r.alarm_code, set()).add(r.expected_action)
    return {code for code, actions in by_code.items() if len(actions) > 1}


def by_scenario(results: list[CaseResult]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for scenario in sorted({r.scenario for r in results}):
        rows = [r for r in results if r.scenario == scenario]
        out[scenario] = {
            "n": len(rows),
            "action_accuracy": _safe_div(sum(r.action_correct for r in rows), len(rows)),
            "cause_accuracy": _safe_div(sum(r.cause_correct for r in rows), len(rows)),
        }
    return out


@dataclass
class Report:
    model: str
    n: int
    action_accuracy: float
    cause_accuracy: float
    macro_f1: float
    # Accuracy restricted to alarm codes that do not determine the answer. This is where
    # reasoning shows; the rest of the set is a reading test.
    ambiguous_accuracy: float
    ambiguous_n: int
    unsafe_continue_rate: float
    unsafe_continue_count: int
    missed_hold_rate: float
    evidence_citation_rate: float
    mean_confidence: float
    mean_tool_calls: float
    mean_latency_ms: float
    fallback_rate: float
    error_count: int
    per_action: dict[str, dict[str, float]]
    confusion: dict[str, dict[str, int]]
    per_scenario: dict[str, dict[str, float]]
    predicted_distribution: dict[str, int]
    cases: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def score(results: list[CaseResult], model: str) -> Report:
    if not results:
        raise ValueError("no results to score")

    should_hold = [r for r in results if r.expected_action == Action.HOLD_LOT]
    unsafe = [r for r in should_hold if r.predicted_action == Action.CONTINUE]
    missed = [r for r in should_hold if r.predicted_action != Action.HOLD_LOT]
    per_action = per_class_f1(results)
    ambiguous = ambiguous_codes(results)
    ambiguous_cases = [r for r in results if r.alarm_code in ambiguous]

    return Report(
        model=model,
        n=len(results),
        action_accuracy=_safe_div(sum(r.action_correct for r in results), len(results)),
        cause_accuracy=_safe_div(sum(r.cause_correct for r in results), len(results)),
        macro_f1=mean(per_action[a]["f1"] for a in ACTIONS),
        ambiguous_accuracy=_safe_div(
            sum(r.action_correct for r in ambiguous_cases), len(ambiguous_cases)
        ),
        ambiguous_n=len(ambiguous_cases),
        # The number that matters: a lot that should have been frozen, waved through.
        unsafe_continue_rate=_safe_div(len(unsafe), len(should_hold)),
        unsafe_continue_count=len(unsafe),
        missed_hold_rate=_safe_div(len(missed), len(should_hold)),
        evidence_citation_rate=_safe_div(
            sum(1 for r in results if r.evidence_count >= MIN_EVIDENCE), len(results)
        ),
        mean_confidence=mean(r.confidence for r in results),
        mean_tool_calls=mean(r.tool_calls for r in results),
        mean_latency_ms=mean(r.latency_ms for r in results),
        fallback_rate=_safe_div(sum(1 for r in results if r.fallback), len(results)),
        error_count=sum(1 for r in results if r.error),
        per_action=per_action,
        confusion=confusion(results),
        per_scenario=by_scenario(results),
        predicted_distribution=dict(Counter(r.predicted_action for r in results)),
        cases=[asdict(r) for r in results],
    )


def to_markdown(report: Report) -> str:
    """A report a human reads, leading with the safety number."""
    pct = lambda x: f"{x * 100:.1f}%"  # noqa: E731

    lines = [
        f"# Triage evaluation — {report.model}",
        "",
        f"{report.n} held-out alarms.",
        "",
        "## Safety",
        "",
        f"- **Unsafe continue: {pct(report.unsafe_continue_rate)}** "
        f"({report.unsafe_continue_count} lots that should have been held were waved through)",
        f"- Missed holds (any non-hold on a hold case): {pct(report.missed_hold_rate)}",
        "",
        "## Accuracy",
        "",
        f"- Action: {pct(report.action_accuracy)}",
        f"- **Action on ambiguous alarm codes: {pct(report.ambiguous_accuracy)}** "
        f"({report.ambiguous_n} cases where the code does not give the answer)",
        f"- Root cause: {pct(report.cause_accuracy)}",
        f"- Macro F1 over actions: {report.macro_f1:.3f}",
        "",
        "## Reviewability",
        "",
        f"- Proposals citing {MIN_EVIDENCE}+ pieces of evidence: "
        f"{pct(report.evidence_citation_rate)}",
        f"- Mean confidence: {report.mean_confidence:.2f}",
        f"- Structured-output fallbacks: {pct(report.fallback_rate)}",
        f"- Errors: {report.error_count}",
        "",
        "## Cost",
        "",
        f"- Mean tool calls: {report.mean_tool_calls:.1f}",
        f"- Mean latency: {report.mean_latency_ms / 1000:.1f}s",
        "",
        "## Confusion (rows expected, columns predicted)",
        "",
        "| expected \\ predicted | " + " | ".join(ACTIONS) + " |",
        "|---|" + "---|" * len(ACTIONS),
    ]
    for expected in ACTIONS:
        row = report.confusion[expected]
        lines.append(f"| {expected} | " + " | ".join(str(row[p]) for p in ACTIONS) + " |")

    lines += ["", "## By scenario", "", "| scenario | n | action | cause |", "|---|---|---|---|"]
    for scenario, stats in report.per_scenario.items():
        lines.append(
            f"| {scenario} | {int(stats['n'])} | "
            f"{pct(stats['action_accuracy'])} | {pct(stats['cause_accuracy'])} |"
        )

    return "\n".join(lines) + "\n"
