"""ffverse expected fantasy points (xFP) for the prior season, via nflreadpy.

parse() returns:
  xfp   gsis_id, xfp_2025, fp_over_xfp_2025 (season totals, ffverse's own FP calc)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl

from draft_data.cache import is_fresh, newest, timestamp
from draft_data.config import SourceConfig


def fetch(cfg: SourceConfig, max_age_hours: float, force: bool = False) -> list[Path]:
    existing = newest(cfg.raw_dir, "ff_opportunity_*.parquet")
    if not force and is_fresh(existing, max_age_hours):
        return [existing]
    import nflreadpy as nfl

    df = nfl.load_ff_opportunity([cfg.options["season"]])
    path = cfg.raw_dir / f"ff_opportunity_{timestamp()}.parquet"
    df.write_parquet(path)
    return [path]


def parse(cfg: SourceConfig) -> dict[str, pd.DataFrame]:
    path = newest(cfg.raw_dir, "ff_opportunity_*.parquet")
    if path is None:
        raise FileNotFoundError("ffopportunity raw missing (run refresh)")
    df = pl.read_parquet(path).to_pandas()
    season = cfg.options["season"]
    agg = (
        df.groupby("player_id")[["total_fantasy_points", "total_fantasy_points_exp"]]
        .sum()
        .rename(columns={
            "total_fantasy_points": f"fp_ffv_{season}",
            "total_fantasy_points_exp": f"xfp_{season}",
        })
    )
    agg[f"fp_over_xfp_{season}"] = agg[f"fp_ffv_{season}"] - agg[f"xfp_{season}"]
    return {"xfp": agg.reset_index().rename(columns={"player_id": "gsis_id"})}
