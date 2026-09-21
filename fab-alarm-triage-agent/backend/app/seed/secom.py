"""Download, cache and normalise the UCI SECOM dataset.

SECOM is 1567 process runs x 590 anonymised sensor columns, plus a pass/fail yield
label and a timestamp per run. We keep the real measurements and the real yield
labels; what we add is a semantic naming layer (signal_map.yaml) so the agent can
cite "chamber_pressure 58.4 mTorr, 3.2 sigma above UCL" rather than "sensor_412 high".
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

SECOM_URL = "https://archive.ics.uci.edu/static/public/179/secom.zip"

CACHE_DIR = Path(__file__).parent / ".cache"
SECOM_DATA = CACHE_DIR / "secom.data"
SECOM_LABELS = CACHE_DIR / "secom_labels.data"
SIGNAL_MAP_PATH = Path(__file__).parent / "signal_map.yaml"

# A nominal run sits mid-band; +/-3 sigma spans the control limits.
SIGMA_DIVISOR = 6.0


@dataclass(frozen=True)
class Signal:
    """One named fab signal backed by a SECOM column."""

    column: int
    key: str
    label: str
    unit: str
    lcl: float
    ucl: float
    # Hard physical bounds, distinct from the control limits. A leak rate may sit
    # outside its UCL, but it cannot be negative.
    floor: float | None = None
    ceiling: float | None = None

    @property
    def nominal(self) -> float:
        return (self.lcl + self.ucl) / 2.0

    @property
    def sigma(self) -> float:
        return (self.ucl - self.lcl) / SIGMA_DIVISOR

    def from_z(self, z: float) -> float:
        """Map a z-score onto this signal's engineering range, clamped to physical bounds."""
        return self.clamp(self.nominal + z * self.sigma)

    def clamp(self, value: float) -> float:
        if self.floor is not None:
            value = max(value, self.floor)
        if self.ceiling is not None:
            value = min(value, self.ceiling)
        return value

    def z_of(self, value: float) -> float:
        return (value - self.nominal) / self.sigma

    def out_of_limit(self, value: float) -> bool:
        return value < self.lcl or value > self.ucl


def ensure_secom() -> None:
    """Download and unpack SECOM if not already cached. Idempotent."""
    if SECOM_DATA.exists() and SECOM_LABELS.exists():
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(SECOM_URL, timeout=120) as resp:  # noqa: S310
        payload = resp.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        for name in ("secom.data", "secom_labels.data", "secom.names"):
            if name in zf.namelist():
                (CACHE_DIR / name).write_bytes(zf.read(name))


@lru_cache
def load_signals() -> tuple[Signal, ...]:
    spec = yaml.safe_load(SIGNAL_MAP_PATH.read_text())
    return tuple(Signal(**entry) for entry in spec["signals"])


@lru_cache
def load_scenario_signals() -> dict[str, tuple[str, ...]]:
    spec = yaml.safe_load(SIGNAL_MAP_PATH.read_text())
    return {k: tuple(v) for k, v in spec["scenario_signals"].items()}


def signals_by_key() -> dict[str, Signal]:
    return {s.key: s for s in load_signals()}


@dataclass(frozen=True)
class SecomFrame:
    """Normalised SECOM data, ready for seeding.

    `values` is indexed by run (0..1566) with one column per signal key, already
    rescaled into engineering units. `z` holds the matching z-scores.
    """

    values: pd.DataFrame
    z: pd.DataFrame
    yield_label: pd.Series  # "pass" | "fail"
    timestamps: pd.Series

    def __len__(self) -> int:
        return len(self.values)


@lru_cache
def load_secom() -> SecomFrame:
    """Load SECOM and project it onto the named signals."""
    ensure_secom()
    raw = pd.read_csv(SECOM_DATA, sep=r"\s+", header=None, na_values=["NaN"])
    # The label file is `<-1|1> "dd/mm/YYYY HH:MM:SS"` — the quoted timestamp contains a
    # space but parses as a single field, so this is two columns, not three.
    labels = pd.read_csv(
        SECOM_LABELS,
        sep=r"\s+",
        header=None,
        names=["label", "timestamp"],
        quotechar='"',
    )

    signals = load_signals()
    z_cols: dict[str, pd.Series] = {}
    val_cols: dict[str, pd.Series] = {}

    for sig in signals:
        col = raw[sig.column].astype(float)
        # Selected columns have no missing values, but guard anyway so a future
        # signal_map edit cannot silently produce NaN sensor readings.
        col = col.fillna(col.median())
        std = col.std()
        z = (col - col.mean()) / (std if std else 1.0)
        values = z.map(sig.from_z)
        # Recompute z from the clamped value so the two the agent sees always agree.
        val_cols[sig.key] = values
        z_cols[sig.key] = values.map(sig.z_of)

    timestamps = pd.to_datetime(labels["timestamp"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    if timestamps.isna().any():
        raise ValueError(
            f"SECOM label timestamps failed to parse ({int(timestamps.isna().sum())} of "
            f"{len(timestamps)}); the label file format may have changed."
        )

    return SecomFrame(
        values=pd.DataFrame(val_cols),
        z=pd.DataFrame(z_cols),
        # SECOM encodes +1 as a yield failure and -1 as a pass.
        yield_label=labels["label"].map({1: "fail", -1: "pass"}),
        timestamps=timestamps,
    )


def fail_run_indices() -> list[int]:
    """Row indices SECOM labels as yield failures (104 of 1567)."""
    frame = load_secom()
    return list(np.flatnonzero((frame.yield_label == "fail").to_numpy()))
