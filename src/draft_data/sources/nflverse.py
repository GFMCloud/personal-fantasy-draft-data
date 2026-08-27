"""nflverse via nflreadpy: canonical IDs, 2025 stats, snap %, red-zone usage, byes.

parse() returns:
  players   one row per gsis_id (QB/RB/WR/TE/K pool + raw roster fields)
  stats     2025 regular-season aggregates per gsis_id
  ids       cross-platform ID crosswalk
  byes      2026 bye week per team
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import polars as pl

from draft_data.cache import is_fresh, newest, timestamp
from draft_data.config import SourceConfig

DATASETS = ("players", "player_stats", "snap_counts", "pbp", "schedules", "ff_playerids")


def _load(dataset: str, season: int) -> pl.DataFrame:
    import nflreadpy as nfl

    if dataset == "players":
        return nfl.load_players()
    if dataset == "player_stats":
        return nfl.load_player_stats([season])
    if dataset == "snap_counts":
        return nfl.load_snap_counts([season])
    if dataset == "pbp":
        return nfl.load_pbp([season])
    if dataset == "schedules":
        return nfl.load_schedules([season + 1])  # upcoming season, for byes
    if dataset == "ff_playerids":
        return nfl.load_ff_playerids()
    raise ValueError(dataset)


def fetch(cfg: SourceConfig, max_age_hours: float, force: bool = False) -> list[Path]:
    season = cfg.options["season"]
    out = []
    for ds in DATASETS:
        existing = newest(cfg.raw_dir, f"{ds}_*.parquet")
        if not force and is_fresh(existing, max_age_hours):
            out.append(existing)
            continue
        df = _load(ds, season)
        # pbp is huge; keep only the columns red-zone usage needs
        if ds == "pbp":
            df = df.select(
                "season_type", "yardline_100", "rush_attempt", "pass_attempt",
                "complete_pass", "rusher_player_id", "receiver_player_id",
            )
        path = cfg.raw_dir / f"{ds}_{timestamp()}.parquet"
        df.write_parquet(path)
        out.append(path)
    return out


def _read(cfg: SourceConfig, ds: str) -> pd.DataFrame:
    path = newest(cfg.raw_dir, f"{ds}_*.parquet")
    if path is None:
        raise FileNotFoundError(f"nflverse raw missing: {ds} (run refresh)")
    return pl.read_parquet(path).to_pandas()


def parse(cfg: SourceConfig) -> dict[str, pd.DataFrame]:
    players = _read(cfg, "players")
    players = players[players["position"].isin(["QB", "RB", "WR", "TE", "K"])][
        ["gsis_id", "display_name", "position", "latest_team", "status",
         "draft_year", "draft_round", "draft_pick", "espn_id"]
    ].rename(columns={"display_name": "name", "latest_team": "team"})
    players = players.dropna(subset=["gsis_id"])

    stats = _season_stats(cfg)
    ids = _read(cfg, "ff_playerids")[
        ["gsis_id", "sleeper_id", "espn_id", "yahoo_id", "fantasypros_id", "pfr_id", "mfl_id"]
    ].dropna(subset=["gsis_id"])
    byes = _byes(_read(cfg, "schedules"))
    return {"players": players, "stats": stats, "ids": ids, "byes": byes}


def _season_stats(cfg: SourceConfig) -> pd.DataFrame:
    ps = _read(cfg, "player_stats")
    ps = ps[ps["season_type"] == "REG"]
    g = ps.groupby("player_id")
    stats = pd.DataFrame({
        "g": g["week"].nunique(),
        "targets": g["targets"].sum(),
        "receptions": g["receptions"].sum(),
        "rec_yards": g["receiving_yards"].sum(),
        "rec_td": g["receiving_tds"].sum(),
        "rush_att": g["carries"].sum(),
        "rush_yards": g["rushing_yards"].sum(),
        "rush_td": g["rushing_tds"].sum(),
        "pass_att": g["attempts"].sum(),
        "pass_yards": g["passing_yards"].sum(),
        "pass_td": g["passing_tds"].sum(),
        "pass_int": g["passing_interceptions"].sum(),
        "two_pt": g["passing_2pt_conversions"].sum()
        + g["rushing_2pt_conversions"].sum()
        + g["receiving_2pt_conversions"].sum(),
        "fumbles_lost": g["sack_fumbles_lost"].sum()
        + g["rushing_fumbles_lost"].sum()
        + g["receiving_fumbles_lost"].sum(),
        "target_share": g["target_share"].mean(),
        "wopr": g["wopr"].mean(),
    })

    snaps = _read(cfg, "snap_counts")
    ids = _read(cfg, "ff_playerids")[["gsis_id", "pfr_id"]].dropna()
    snap_pct = (
        snaps.groupby("pfr_player_id")["offense_pct"].mean().rename("snap_pct").reset_index()
        .merge(ids, left_on="pfr_player_id", right_on="pfr_id")
        .set_index("gsis_id")["snap_pct"]
    )
    stats = stats.join(snap_pct)

    pbp = _read(cfg, "pbp")
    rz = pbp[(pbp["season_type"] == "REG") & (pbp["yardline_100"] <= 20)]
    rz_carries = rz[rz["rush_attempt"] == 1].groupby("rusher_player_id").size()
    rz_targets = rz[rz["pass_attempt"] == 1].groupby("receiver_player_id").size()
    rz_rec = rz[rz["complete_pass"] == 1].groupby("receiver_player_id").size()
    stats["rz_carries"] = rz_carries.reindex(stats.index).fillna(0).astype(int)
    stats["rz_targets"] = rz_targets.reindex(stats.index).fillna(0).astype(int)
    stats["rz_touches"] = stats["rz_carries"] + rz_rec.reindex(stats.index).fillna(0).astype(int)

    return stats.reset_index().rename(columns={"player_id": "gsis_id"})


def _byes(sched: pd.DataFrame) -> pd.DataFrame:
    reg = sched[sched["game_type"] == "REG"]
    weeks = set(range(1, int(reg["week"].max()) + 1))
    rows = []
    for team in sorted(set(reg["home_team"]) | set(reg["away_team"])):
        played = set(reg.loc[reg["home_team"] == team, "week"]) | set(
            reg.loc[reg["away_team"] == team, "week"]
        )
        bye = sorted(weeks - played)
        rows.append({"team": team, "bye_week": bye[0] if bye else None})
    return pd.DataFrame(rows)
