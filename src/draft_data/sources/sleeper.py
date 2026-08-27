"""Sleeper API: player master (status/injury flags, ID crosswalk) + trending adds.

parse() returns:
  players   sleeper_id, gsis_id, name, team, position, status, injury flags
  trending  sleeper_id, trend_add_count
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from draft_data.cache import cached_get, newest
from draft_data.config import SourceConfig

PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
TRENDING_URL = "https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours={h}&limit=300"


def fetch(cfg: SourceConfig, max_age_hours: float, force: bool = False) -> list[Path]:
    h = cfg.options.get("trending_lookback_hours", 48)
    return [
        cached_get(PLAYERS_URL, cfg.raw_dir, "players", "json",
                   max_age_hours=max_age_hours, force=force),
        cached_get(TRENDING_URL.format(h=h), cfg.raw_dir, "trending", "json",
                   max_age_hours=max_age_hours, force=force),
    ]


def parse(cfg: SourceConfig) -> dict[str, pd.DataFrame]:
    ppath = newest(cfg.raw_dir, "players_*.json")
    tpath = newest(cfg.raw_dir, "trending_*.json")
    if ppath is None or tpath is None:
        raise FileNotFoundError("sleeper raw missing (run refresh)")

    raw = json.loads(ppath.read_text())
    rows = []
    for sid, p in raw.items():
        if not isinstance(p, dict) or p.get("position") not in {"QB", "RB", "WR", "TE", "K", "DEF"}:
            continue
        rows.append({
            "sleeper_id": sid,
            "gsis_id": p.get("gsis_id"),
            "name": p.get("full_name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip(),
            "team": p.get("team"),
            "position": p.get("position"),
            "status": p.get("status"),
            "injury_status": p.get("injury_status"),
            "injury_note": p.get("injury_notes"),
        })
    players = pd.DataFrame(rows)
    if "gsis_id" in players.columns:
        players["gsis_id"] = players["gsis_id"].astype("string").str.strip()

    trending = pd.DataFrame(json.loads(tpath.read_text())).rename(
        columns={"player_id": "sleeper_id", "count": "trend_add_count"}
    )
    return {"players": players, "trending": trending}
