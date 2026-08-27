"""FantasyPros ECR republished by DynastyProcess (via nflreadpy load_ff_rankings).

Redraft-overall page = PPR cheatsheet. parse() returns:
  ecr   fantasypros_id, name, position, team, ecr, ecr_sd, ecr_best, ecr_worst, scrape_date
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl

from draft_data.cache import is_fresh, newest, timestamp
from draft_data.config import SourceConfig


def fetch(cfg: SourceConfig, max_age_hours: float, force: bool = False) -> list[Path]:
    existing = newest(cfg.raw_dir, "ff_rankings_*.parquet")
    if not force and is_fresh(existing, max_age_hours):
        return [existing]
    import nflreadpy as nfl

    df = nfl.load_ff_rankings("draft")
    path = cfg.raw_dir / f"ff_rankings_{timestamp()}.parquet"
    df.write_parquet(path)
    return [path]


def parse(cfg: SourceConfig) -> dict[str, pd.DataFrame]:
    path = newest(cfg.raw_dir, "ff_rankings_*.parquet")
    if path is None:
        raise FileNotFoundError("dynastyprocess raw missing (run refresh)")
    df = pl.read_parquet(path).to_pandas()
    ecr = df[df["page_type"] == "redraft-overall"][
        ["id", "player", "pos", "tm", "ecr", "sd", "best", "worst", "scrape_date"]
    ].rename(columns={
        "id": "fantasypros_id", "player": "name", "pos": "position", "tm": "team",
        "sd": "ecr_sd", "best": "ecr_best", "worst": "ecr_worst",
    })
    ecr["fantasypros_id"] = ecr["fantasypros_id"].astype(str)
    return {"ecr": ecr}
