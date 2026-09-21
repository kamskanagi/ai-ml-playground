"""Tests for the SECOM loader and the signal map.

These exercise the real dataset (cached under app/seed/.cache). The normalisation is
what every downstream evidence string depends on, so it is worth pinning precisely.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.seed.secom import (
    Signal,
    fail_run_indices,
    load_scenario_signals,
    load_secom,
    load_signals,
    signals_by_key,
)

EXPECTED_RUNS = 1567
EXPECTED_FAILS = 104
EXPECTED_SIGNALS = 16


# --- signal map integrity -------------------------------------------------


def test_signal_map_has_unique_keys_and_columns():
    signals = load_signals()
    assert len(signals) == EXPECTED_SIGNALS
    assert len({s.key for s in signals}) == EXPECTED_SIGNALS
    assert len({s.column for s in signals}) == EXPECTED_SIGNALS


def test_control_limits_are_ordered():
    for sig in load_signals():
        assert sig.lcl < sig.ucl, sig.key
        assert sig.sigma > 0, sig.key


def test_scenario_signal_references_resolve():
    keys = signals_by_key().keys()
    for cause, refs in load_scenario_signals().items():
        for ref in refs:
            assert ref in keys, f"{cause} references unknown signal {ref}"


def test_physical_bounds_do_not_contradict_control_limits():
    for sig in load_signals():
        if sig.floor is not None:
            assert sig.floor <= sig.lcl, sig.key
        if sig.ceiling is not None:
            assert sig.ceiling >= sig.ucl, sig.key


# --- Signal arithmetic ----------------------------------------------------


def test_from_z_maps_three_sigma_onto_the_control_limits():
    sig = Signal(column=0, key="k", label="K", unit="u", lcl=45.0, ucl=55.0)
    assert sig.nominal == pytest.approx(50.0)
    assert sig.from_z(0.0) == pytest.approx(50.0)
    assert sig.from_z(-3.0) == pytest.approx(45.0)
    assert sig.from_z(3.0) == pytest.approx(55.0)


def test_z_of_inverts_from_z():
    sig = Signal(column=0, key="k", label="K", unit="u", lcl=45.0, ucl=55.0)
    for z in (-2.5, -0.4, 0.0, 1.7):
        assert sig.z_of(sig.from_z(z)) == pytest.approx(z)


def test_from_z_clamps_to_physical_floor():
    sig = Signal(column=0, key="leak", label="Leak", unit="sccm", lcl=0.0, ucl=2.0, floor=0.0)
    assert sig.from_z(-10.0) == pytest.approx(0.0)


def test_from_z_clamps_to_physical_ceiling():
    sig = Signal(
        column=0, key="pos", label="Pos", unit="%", lcl=30.0, ucl=70.0, floor=0.0, ceiling=100.0
    )
    assert sig.from_z(50.0) == pytest.approx(100.0)


def test_out_of_limit_detects_both_directions():
    sig = Signal(column=0, key="k", label="K", unit="u", lcl=45.0, ucl=55.0)
    assert sig.out_of_limit(44.9)
    assert sig.out_of_limit(55.1)
    assert not sig.out_of_limit(50.0)


# --- dataset --------------------------------------------------------------


def test_dataset_shape_and_yield_distribution():
    frame = load_secom()
    assert len(frame) == EXPECTED_RUNS
    assert list(frame.values.columns) == [s.key for s in load_signals()]
    assert frame.yield_label.value_counts().to_dict() == {
        "pass": EXPECTED_RUNS - EXPECTED_FAILS,
        "fail": EXPECTED_FAILS,
    }
    assert len(fail_run_indices()) == EXPECTED_FAILS


def test_timestamps_all_parse():
    frame = load_secom()
    assert frame.timestamps.isna().sum() == 0
    assert frame.timestamps.min().year == 2008
    assert frame.timestamps.max() > frame.timestamps.min()


def test_signals_are_centred_on_their_nominal_value():
    frame = load_secom()
    for sig in load_signals():
        series = frame.values[sig.key]
        # Clamping pulls a few heavily-skewed signals off centre; allow half a sigma.
        assert abs(series.mean() - sig.nominal) < 0.5 * sig.sigma, sig.key


def test_most_runs_sit_inside_control_limits():
    """The baseline must be quiet — the scenario generator is what creates excursions."""
    frame = load_secom()
    for sig in load_signals():
        breaches = sum(sig.out_of_limit(v) for v in frame.values[sig.key])
        assert breaches / len(frame) < 0.05, f"{sig.key} breaches limits on {breaches} runs"


def test_values_respect_physical_bounds():
    frame = load_secom()
    for sig in load_signals():
        series = frame.values[sig.key]
        if sig.floor is not None:
            assert series.min() >= sig.floor - 1e-9, sig.key
        if sig.ceiling is not None:
            assert series.max() <= sig.ceiling + 1e-9, sig.key


def test_stored_z_scores_match_stored_values():
    """The agent cites value and sigma together; they must not disagree."""
    frame = load_secom()
    by_key = signals_by_key()
    for key in frame.values.columns:
        reconstructed = frame.z[key].map(by_key[key].from_z)
        assert np.allclose(reconstructed, frame.values[key]), key


def test_load_secom_is_cached():
    assert load_secom() is load_secom()
