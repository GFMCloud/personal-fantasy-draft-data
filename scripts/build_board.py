"""Generate board HTML files from the processed parquet artifacts.

The template (src/draft_data/board_template.html) is the editable source; the
HTML outputs are generated and gitignored. Run via `make board`.

Builds data/processed/board.html (league-agnostic default) plus one
board_<slug>.html per config in leagues/*.json. A league config supplies the
title, default scoring format, and that league's keepers; the data underneath
is identical.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

import pandas as pd

from draft_data.config import PROCESSED_DIR, ROOT

TEMPLATE = ROOT / "src" / "draft_data" / "board_template.html"
LEAGUES_DIR = ROOT / "leagues"
FORMATS = ("ppr", "half", "std")
FMT_LABELS = {"ppr": "PPR", "half": "Half-PPR", "std": "Standard"}
MIN_BOARDS = 20  # min appearances before an empirical availability % is shown


def _f(v, nd=2):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), nd)


def _load_data():
    players = pd.read_parquet(PROCESSED_DIR / "players.parquet")
    picks = pd.read_parquet(PROCESSED_DIR / "draft_picks.parquet")
    meta = json.loads((PROCESSED_DIR / "meta.json").read_text())
    return players, picks, meta


def _availability(picks, avail_picks):
    # empirical availability per (player, format): % of boards where the player
    # went at pick >= N (i.e. was still available when pick N came up)
    p1, p2 = avail_picks
    avail: dict[str, dict[str, list]] = {}
    drafts_by_fmt = {}
    for fmt, g in picks.groupby("format"):
        drafts_by_fmt[fmt] = int(g["draft_id"].nunique())
        agg = g.dropna(subset=["player_id"]).groupby("player_id")["pick_overall"].agg(
            n="count", a1=lambda s: (s >= p1).mean() * 100, a2=lambda s: (s >= p2).mean() * 100
        )
        for pid, row in agg[agg["n"] >= MIN_BOARDS].iterrows():
            avail.setdefault(pid, {})[fmt] = [round(row["a1"], 1), round(row["a2"], 1)]
    return avail, drafts_by_fmt


def _rows(players, avail, keepers, remove_keepers=False):
    board = players[
        players["ecr"].notna()
        | players[[f"adp_ffc_{f}" for f in FORMATS]].notna().any(axis=1)
        | players["adp_espn"].notna()
    ]
    rows = []
    removed = []
    for _, p in board.iterrows():
        if remove_keepers and p["name"] in keepers:
            removed.append(p["name"])
            continue
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
    if remove_keepers:
        missing = sorted(keepers - set(removed))
        if missing:  # surface, never silently drop the mismatch
            print(f"[board] WARNING: keepers not found on board (check names): {missing}")
        print(f"[board] keepers removed from board: {len(removed)}")
    return rows


def _render(template, out_path, *, title, slug, fmt_default, subtitle_lead,
            rows, picks, drafts_by_fmt, meta, avail_picks):
    windows = {w["format"]: w for w in meta.get("ffc_adp_windows", [])}
    adp_end = windows.get("ppr", {}).get("end_date", "?")
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    subtitle = (
        f"{subtitle_lead} · generated {generated} · "
        f"availability from real FFC 12-team mocks · ECR is PPR-flavored (FantasyPros via DynastyProcess)"
    )
    html = (
        template.replace("__DATA__", json.dumps(rows, separators=(",", ":")))
        .replace("__DRAFTS_BY_FMT__", json.dumps(drafts_by_fmt))
        .replace("__TITLE__", title)
        .replace("__SLUG__", slug)
        .replace("__FMT_DEFAULT__", fmt_default)
        .replace("__SUBTITLE__", subtitle)
        .replace("__N_PLAYERS__", str(len(rows)))
        .replace("__N_DRAFTS__", str(int(picks["draft_id"].nunique())))
        .replace("__N_PICKS__", str(len(picks)))
        .replace("__N_DRAFTS_FMT__", "~" + str(drafts_by_fmt.get(fmt_default, 0)))
        .replace("__AVAIL_A__", str(avail_picks[0]))
        .replace("__AVAIL_B__", str(avail_picks[1]))
        .replace("__ADP_END__", str(adp_end))
    )
    out_path.write_text(html)
    print(f"[board] {out_path}: {len(rows)} players, {len(html)//1024} KB")


def build_boards() -> None:
    players, picks, meta = _load_data()
    league_defaults = json.loads((PROCESSED_DIR / "league.json").read_text())
    template = TEMPLATE.read_text()
    avail_cache: dict[tuple, tuple] = {}

    def availability(avail_picks):
        key = tuple(avail_picks)
        if key not in avail_cache:
            avail_cache[key] = _availability(picks, key)
        return avail_cache[key]

    # default league-agnostic board (keepers from the recorded reference defaults)
    default_keepers = {k["player"] for k in league_defaults["my_draft"]["keepers"]}
    avail, drafts_by_fmt = availability((24, 26))
    _render(
        template, PROCESSED_DIR / "board.html",
        title="Draft Board", slug="draft-board", fmt_default="ppr",
        subtitle_lead="League-agnostic board",
        rows=_rows(players, avail, default_keepers),
        picks=picks, drafts_by_fmt=drafts_by_fmt, meta=meta, avail_picks=(24, 26),
    )

    # one board per league config; same data, league-specific presentation
    for cfg_path in sorted(LEAGUES_DIR.glob("*.json")) if LEAGUES_DIR.exists() else []:
        cfg = json.loads(cfg_path.read_text())
        fmt = cfg["default_format"]
        if fmt not in FORMATS:
            raise ValueError(f"{cfg_path.name}: default_format must be one of {FORMATS}")
        keepers = {k["player"] for k in cfg.get("keepers", [])}
        remove = bool(cfg.get("remove_keepers"))
        avail_picks = tuple(cfg.get("avail_picks", (24, 26)))
        avail, drafts_by_fmt = availability(avail_picks)
        lead = f"{cfg['title']} · {cfg['teams']}-team · {FMT_LABELS[fmt]} default"
        if keepers and remove:
            lead += f" · {len(keepers)} keepers removed from pool"
        elif not keepers:
            lead += " · keepers TBD"
        _render(
            template, PROCESSED_DIR / f"board_{cfg['slug']}.html",
            title=cfg["title"], slug=f"draft-board-{cfg['slug']}", fmt_default=fmt,
            subtitle_lead=lead,
            rows=_rows(players, avail, keepers, remove_keepers=remove),
            picks=picks, drafts_by_fmt=drafts_by_fmt, meta=meta, avail_picks=avail_picks,
        )


if __name__ == "__main__":
    build_boards()
