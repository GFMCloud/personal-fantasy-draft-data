"""Generate data/processed/board.html from the processed parquet artifacts.

The template (src/draft_data/board_template.html) is the editable source; the
HTML output is generated and gitignored. Run via `make board`.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

import pandas as pd

from draft_data.config import PROCESSED_DIR, ROOT

TEMPLATE = ROOT / "src" / "draft_data" / "board_template.html"
OUT = PROCESSED_DIR / "board.html"
FORMATS = ("ppr", "half", "std")
MIN_BOARDS = 20  # min appearances before an empirical availability % is shown


def _f(v, nd=2):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), nd)


def build_board() -> None:
    players = pd.read_parquet(PROCESSED_DIR / "players.parquet")
    picks = pd.read_parquet(PROCESSED_DIR / "draft_picks.parquet")
    meta = json.loads((PROCESSED_DIR / "meta.json").read_text())
    league = json.loads((PROCESSED_DIR / "league.json").read_text())
    keepers = {k["player"] for k in league["my_draft"]["keepers"]}

    # empirical availability per (player, format): % of boards where the player
    # went at pick >= N (i.e. was still available when pick N came up)
    avail: dict[str, dict[str, list]] = {}
    drafts_by_fmt = {}
    for fmt, g in picks.groupby("format"):
        drafts_by_fmt[fmt] = int(g["draft_id"].nunique())
        agg = g.dropna(subset=["player_id"]).groupby("player_id")["pick_overall"].agg(
            n="count", a24=lambda s: (s >= 24).mean() * 100, a26=lambda s: (s >= 26).mean() * 100
        )
        for pid, row in agg[agg["n"] >= MIN_BOARDS].iterrows():
            avail.setdefault(pid, {})[fmt] = [round(row["a24"], 1), round(row["a26"], 1)]

    board = players[
        players["ecr"].notna()
        | players[[f"adp_ffc_{f}" for f in FORMATS]].notna().any(axis=1)
        | players["adp_espn"].notna()
    ]

    rows = []
    for _, p in board.iterrows():
        rows.append({
            "name": p["name"], "team": p["team"] if pd.notna(p["team"]) else None,
            "pos": p["position"], "bye": _f(p["bye_week"], 0),
            "keeper": p["name"] in keepers,
            "inj": p["injury_status"] if pd.notna(p.get("injury_status")) else None,
            "ecr": _f(p["ecr"]), "ecr_sd": _f(p["ecr_sd"]),
            "tier": {f: _f(p[f"tier_bc_{f}"], 0) for f in FORMATS},
            "adp": {f: ([_f(p[f"adp_ffc_{f}"]), _f(p[f"adp_ffc_{f}_sd"])]
                        if pd.notna(p[f"adp_ffc_{f}"]) else None) for f in FORMATS},
            "espn": _f(p["adp_espn"]),
            "harris": {"std": _f(p["rank_harris_std"], 0), "ppr": _f(p["rank_harris_ppr"], 0)},
            "avail": avail.get(p["player_id"], {}),
            "ppg": {"ppr": _f(p["ppg_2025_ppr_pass4"]), "half": _f(p["ppg_2025_half_pass4"]),
                    "std": _f(p["ppg_2025_std_pass4"])},
            "luck": _f(p["fp_over_xfp_2025"]),
            "heat": int(p["trend_add_count"]) if pd.notna(p["trend_add_count"]) else None,
        })

    windows = {w["format"]: w for w in meta.get("ffc_adp_windows", [])}
    adp_end = windows.get("ppr", {}).get("end_date", "?")
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    subtitle = (
        f"League-agnostic board · generated {generated} · "
        f"availability from real FFC 12-team mocks · ECR is PPR-flavored (FantasyPros via DynastyProcess)"
    )

    html = TEMPLATE.read_text()
    html = (
        html.replace("__DATA__", json.dumps(rows, separators=(",", ":")))
        .replace("__DRAFTS_BY_FMT__", json.dumps(drafts_by_fmt))
        .replace("__SUBTITLE__", subtitle)
        .replace("__N_PLAYERS__", str(len(rows)))
        .replace("__N_DRAFTS__", str(int(picks["draft_id"].nunique())))
        .replace("__N_PICKS__", str(len(picks)))
        .replace("__N_DRAFTS_FMT__", "~" + str(drafts_by_fmt.get("ppr", 0)))
        .replace("__ADP_END__", str(adp_end))
    )
    OUT.write_text(html)
    print(f"[board] {OUT}: {len(rows)} players, {len(html)//1024} KB")


if __name__ == "__main__":
    build_board()
