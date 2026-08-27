"""Boris Chen tiers (Gaussian mixture over FantasyPros ECR), published as S3 CSVs.

parse() returns:
  tiers   name, position, format, tier
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from draft_data.cache import cached_get, newest
from draft_data.config import SourceConfig

BASE = "https://s3-us-west-1.amazonaws.com/fftiers/out/weekly-ALL{suffix}.csv"
FMT = {"PPR": ("-PPR", "ppr"), "HALF-PPR": ("-HALF-PPR", "half"), "": ("", "std")}


def fetch(cfg: SourceConfig, max_age_hours: float, force: bool = False) -> list[Path]:
    out = []
    for fmt in cfg.options["formats"]:
        suffix, key = FMT[fmt]
        out.append(cached_get(BASE.format(suffix=suffix), cfg.raw_dir, f"tiers_{key}", "csv",
                              max_age_hours=max_age_hours, force=force))
    return out


def parse(cfg: SourceConfig) -> dict[str, pd.DataFrame]:
    frames = []
    for fmt in cfg.options["formats"]:
        _, key = FMT[fmt]
        path = newest(cfg.raw_dir, f"tiers_{key}_*.csv")
        if path is None:
            raise FileNotFoundError(f"borischen raw missing: {key}")
        df = pd.read_csv(io.StringIO(path.read_text()))
        df = df.rename(columns={"Player.Name": "name", "Position": "position", "Tier": "tier"})
        df["format"] = key
        frames.append(df[["name", "position", "format", "tier"]])
    return {"tiers": pd.concat(frames, ignore_index=True)}
