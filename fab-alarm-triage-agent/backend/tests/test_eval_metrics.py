"""Scoring tests.

Pure functions with hand-built cases, so every figure can be checked by hand. These are
worth being fussy about: a wrong metric does not crash, it just reports a number that
looks plausible and is not true.
"""

from __future__ import annotations

import pytest

from app.eval.metrics import CaseResult, ambiguous_codes, score, to_markdown


def case(expected: str, predicted: str, code: str = "X", **kw) -> CaseResult:
    defaults = dict(
        alarm_id=1,
        alarm_code=code,
        scenario=kw.pop("scenario", "s"),
        expected_action=expected,
        expected_root_cause=kw.pop("expected_cause", "chamber_leak"),
        predicted_action=predicted,
        predicted_root_cause=kw.pop("predicted_cause", "chamber_leak"),
        confidence=kw.pop("confidence", 0.8),
        evidence_count=kw.pop("evidence_count", 2),
        tool_calls=kw.pop("tool_calls", 3),
        latency_ms=kw.pop("latency_ms", 1000),
    )
    defaults.update(kw)
    return CaseResult(**defaults)


def test_perfect_run_scores_one():
    results = [case("hold_lot", "hold_lot"), case("continue", "continue")]
    report = score(results, "m")
    assert report.action_accuracy == 1.0
    assert report.unsafe_continue_rate == 0.0


def test_unsafe_continue_counts_only_held_lots_waved_through():
    """Not every miss is unsafe — only a hold case predicted as continue."""
    results = [
        case("hold_lot", "continue"),  # unsafe
        case("hold_lot", "escalate"),  # wrong, but a human still looks
        case("continue", "hold_lot"),  # over-cautious, not unsafe
        case("hold_lot", "hold_lot"),
    ]
    report = score(results, "m")
    assert report.unsafe_continue_count == 1
    assert report.unsafe_continue_rate == pytest.approx(1 / 3)
    # Two of the three hold cases were not held.
    assert report.missed_hold_rate == pytest.approx(2 / 3)


def test_always_escalate_is_perfectly_safe_and_still_bad():
    """The reason safety cannot be the only metric."""
    results = [case("hold_lot", "escalate"), case("continue", "escalate")]
    report = score(results, "m")
    assert report.unsafe_continue_rate == 0.0
    assert report.action_accuracy == 0.0
    assert report.missed_hold_rate == 1.0


def test_ambiguous_codes_are_those_spanning_more_than_one_action():
    results = [
        case("hold_lot", "hold_lot", code="SHARED"),
        case("continue", "continue", code="SHARED"),
        case("escalate", "escalate", code="UNIQUE"),
    ]
    assert ambiguous_codes(results) == {"SHARED"}


def test_ambiguous_accuracy_ignores_cases_the_code_gives_away():
    """A code that determines the answer tests reading, not reasoning."""
    results = [
        case("hold_lot", "hold_lot", code="SHARED"),
        case("continue", "hold_lot", code="SHARED"),  # wrong
        case("escalate", "escalate", code="UNIQUE"),
        case("escalate", "escalate", code="UNIQUE"),
    ]
    report = score(results, "m")
    assert report.action_accuracy == 0.75
    assert report.ambiguous_n == 2
    assert report.ambiguous_accuracy == 0.5


def test_confusion_matrix_places_counts_by_expected_then_predicted():
    results = [
        case("hold_lot", "continue"),
        case("hold_lot", "continue"),
        case("continue", "continue"),
    ]
    matrix = score(results, "m").confusion
    assert matrix["hold_lot"]["continue"] == 2
    assert matrix["continue"]["continue"] == 1
    assert matrix["continue"]["hold_lot"] == 0


def test_macro_f1_is_not_dominated_by_the_common_class():
    """Nine easy continues must not hide a total failure on holds."""
    results = [case("continue", "continue") for _ in range(9)] + [case("hold_lot", "continue")]
    report = score(results, "m")
    assert report.action_accuracy == 0.9
    assert report.macro_f1 < 0.5


def test_evidence_rate_counts_proposals_a_reviewer_could_check():
    results = [
        case("continue", "continue", evidence_count=0),
        case("continue", "continue", evidence_count=1),
        case("continue", "continue", evidence_count=2),
        case("continue", "continue", evidence_count=5),
    ]
    assert score(results, "m").evidence_citation_rate == 0.5


def test_cause_accuracy_is_scored_separately_from_action():
    results = [case("hold_lot", "hold_lot", predicted_cause="sensor_malfunction")]
    report = score(results, "m")
    assert report.action_accuracy == 1.0
    assert report.cause_accuracy == 0.0


def test_fallbacks_and_errors_are_surfaced():
    results = [
        case("continue", "escalate", fallback=True, error="boom"),
        case("continue", "continue"),
    ]
    report = score(results, "m")
    assert report.fallback_rate == 0.5
    assert report.error_count == 1


def test_per_scenario_breakdown_is_reported():
    results = [
        case("hold_lot", "hold_lot", scenario="chamber_leak"),
        case("hold_lot", "continue", scenario="chamber_leak"),
        case("continue", "continue", scenario="no_fault"),
    ]
    per = score(results, "m").per_scenario
    assert per["chamber_leak"]["action_accuracy"] == 0.5
    assert per["no_fault"]["action_accuracy"] == 1.0


def test_scoring_an_empty_run_is_an_error_not_a_zero():
    """A zero would read as 'the agent got everything wrong'."""
    with pytest.raises(ValueError):
        score([], "m")


def test_markdown_leads_with_the_safety_number():
    results = [case("hold_lot", "continue"), case("continue", "continue")]
    text = to_markdown(score(results, "m"))
    assert text.index("Unsafe continue") < text.index("Action:")
    assert "Confusion" in text
