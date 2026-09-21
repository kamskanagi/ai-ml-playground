"""Reproduce the SECOM column selection recorded in app/seed/signal_map.yaml.

    python -m tools.profile_secom

Selection rule: zero missing values, more than 800 distinct values, non-zero
variance; of the columns that qualify, take the 16 with the lowest absolute skew.
"""

from __future__ import annotations

import pandas as pd

from app.seed.secom import SECOM_DATA, ensure_secom

N_SIGNALS = 16
MIN_UNIQUE = 800


def main() -> None:
    ensure_secom()
    df = pd.read_csv(SECOM_DATA, sep=r"\s+", header=None, na_values=["NaN"])

    qualifies = (df.isna().mean() == 0.0) & (df.nunique() > MIN_UNIQUE) & (df.std() > 0)
    candidates = df.columns[qualifies]
    ranked = df[candidates].skew().abs().sort_values()

    print(f"{len(candidates)} columns qualify; lowest-skew {N_SIGNALS} selected:\n")
    print(f"{'col':>5} {'nuniq':>7} {'mean':>12} {'std':>11} {'|skew|':>9}")
    for col in ranked.index[:N_SIGNALS]:
        print(
            f"{col:5d} {df[col].nunique():7d} {df[col].mean():12.3f} "
            f"{df[col].std():11.3f} {ranked[col]:9.3f}"
        )
    print("\ncolumns:", sorted(int(c) for c in ranked.index[:N_SIGNALS]))


if __name__ == "__main__":
    main()
