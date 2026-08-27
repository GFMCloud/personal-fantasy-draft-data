"""Fantasy point computation for every carried scoring variant.

Base (all formats): 0.04/pass yd, -2/INT, 0.1/rush+rec yd, 6/rush+rec TD,
2/two-point, -2/fumble lost. Variants: pass TD 4 or 6; reception 0 / 0.5 / 1.
"""

from __future__ import annotations

import pandas as pd

RECEPTION_VALUE = {"std": 0.0, "half": 0.5, "ppr": 1.0}
SEASON = 2025


def add_point_columns(df: pd.DataFrame) -> pd.DataFrame:
    base = (
        df["pass_yards"].fillna(0) * 0.04
        - df["pass_int"].fillna(0) * 2
        + (df["rush_yards"].fillna(0) + df["rec_yards"].fillna(0)) * 0.1
        + (df["rush_td"].fillna(0) + df["rec_td"].fillna(0)) * 6
        + df["two_pt"].fillna(0) * 2
        - df["fumbles_lost"].fillna(0) * 2
    )
    played = df["g"].fillna(0) > 0
    for fmt, rec_val in RECEPTION_VALUE.items():
        for ptd in (4, 6):
            pts = base + df["receptions"].fillna(0) * rec_val + df["pass_td"].fillna(0) * ptd
            pts = pts.where(played)
            df[f"pts_{SEASON}_{fmt}_pass{ptd}"] = pts.round(2)
            df[f"ppg_{SEASON}_{fmt}_pass{ptd}"] = (pts / df["g"]).where(played).round(2)
    return df
