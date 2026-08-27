"""ESPN ADP via the unofficial public leaguedefaults endpoint. No auth.

Undocumented API: this module fails loudly if the shape changes; refresh continues
without it. parse() returns:
  adp   espn_id, name, position, team, adp_espn, rank_espn_std, rank_espn_ppr
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from draft_data.cache import cached_get, newest
from draft_data.config import SourceConfig

URL = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
    "/segments/0/leaguedefaults/3?view=kona_player_info"
)
FILTER = {
    "players": {
        "limit": 1500,
        "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "STANDARD"},
    }
}
POSITION = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}
TEAM = {
    0: None, 1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN",
    8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA",
    16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI",
    23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR",
    30: "JAX", 33: "BAL", 34: "HOU",
}


def fetch(cfg: SourceConfig, max_age_hours: float, force: bool = False) -> list[Path]:
    url = URL.format(season=cfg.options["season"])
    headers = {"Accept": "application/json", "X-Fantasy-Filter": json.dumps(FILTER)}
    return [cached_get(url, cfg.raw_dir, "kona", "json",
                       max_age_hours=max_age_hours, force=force, headers=headers)]


def parse(cfg: SourceConfig) -> dict[str, pd.DataFrame]:
    path = newest(cfg.raw_dir, "kona_*.json")
    if path is None:
        raise FileNotFoundError("espn raw missing (run refresh)")
    data = json.loads(path.read_text())
    rows = []
    for entry in data["players"]:
        p = entry["player"]
        ranks = p.get("draftRanksByRankType", {})
        adp = (p.get("ownership") or {}).get("averageDraftPosition")
        rows.append({
            "espn_id": p["id"],
            "name": p.get("fullName"),
            "position": POSITION.get(p.get("defaultPositionId")),
            "team": TEAM.get(p.get("proTeamId")),
            "adp_espn": adp,
            "rank_espn_std": (ranks.get("STANDARD") or {}).get("rank"),
            "rank_espn_ppr": (ranks.get("PPR") or {}).get("rank"),
        })
    df = pd.DataFrame(rows)
    df = df[df["position"].notna()]
    return {"adp": df}
