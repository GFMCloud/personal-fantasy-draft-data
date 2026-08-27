"""FantasyFootballCalculator ADP: mean, sd, high, low, times_drafted per format.

parse() returns:
  adp   one row per (player, format)
  meta  one row per format: total_drafts, start_date, end_date
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from draft_data.cache import cached_get, newest
from draft_data.config import SourceConfig

API = "https://fantasyfootballcalculator.com/api/v1/adp/{fmt}?teams={teams}&year={year}"
FMT_KEY = {"ppr": "ppr", "half-ppr": "half", "standard": "std"}


def fetch(cfg: SourceConfig, max_age_hours: float, force: bool = False) -> list[Path]:
    o = cfg.options
    return [
        cached_get(
            API.format(fmt=fmt, teams=o["teams"], year=o["year"]),
            cfg.raw_dir, f"adp_{FMT_KEY[fmt]}", "json",
            max_age_hours=max_age_hours, force=force,
        )
        for fmt in o["formats"]
    ]


def parse(cfg: SourceConfig) -> dict[str, pd.DataFrame]:
    rows, meta = [], []
    for fmt in cfg.options["formats"]:
        key = FMT_KEY[fmt]
        path = newest(cfg.raw_dir, f"adp_{key}_*.json")
        if path is None:
            raise FileNotFoundError(f"ffc raw missing: {fmt}")
        data = json.loads(path.read_text())
        m = data.get("meta", {})
        meta.append({
            "format": key,
            "total_drafts": m.get("total_drafts"),
            "start_date": m.get("start_date"),
            "end_date": m.get("end_date"),
        })
        for p in data["players"]:
            rows.append({
                "name": p["name"], "position": p["position"], "team": p["team"],
                "bye": p.get("bye"), "format": key,
                "adp": p["adp"], "adp_sd": p.get("stdev"),
                "adp_high": p.get("high"), "adp_low": p.get("low"),
                "times_drafted": p.get("times_drafted"),
            })
    return {"adp": pd.DataFrame(rows), "meta": pd.DataFrame(meta)}
