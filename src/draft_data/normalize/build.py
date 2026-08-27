"""Assemble the normalized outputs: players.parquet, draft_picks.parquet,
id_match_review.csv, league.json, meta.json."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd

from draft_data.config import PROCESSED_DIR, Config
from draft_data.normalize.ids import build_master, match_names, norm_team
from draft_data.normalize.scoring import add_point_columns
from draft_data.sources import get_module

FFC_FORMATS = ("ppr", "half", "std")


def _parsed(cfg: Config, name: str):
    sc = cfg.sources.get(name)
    if sc is None or not sc.enabled:
        return None
    try:
        return get_module(name).parse(sc)
    except FileNotFoundError as e:
        print(f"[build] {name}: {e}; columns will be null")
        return None


def _match_map(df: pd.DataFrame, master: pd.DataFrame, source: str, review: list[dict]):
    """Match unique (name, position, team) triples; return merge-ready mapping."""
    keys = df[["name", "position", "team"]].drop_duplicates().reset_index(drop=True)
    keys["player_id"] = match_names(keys, master, source, review)
    return keys


def build_outputs(cfg: Config) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    review: list[dict] = []

    nflv = _parsed(cfg, "nflverse")
    if nflv is None:
        raise SystemExit("nflverse is the canonical baseline and must be enabled/fetched")
    sleeper = _parsed(cfg, "sleeper")
    if sleeper is None:
        raise SystemExit("sleeper is required for the master table (DST rows, status flags)")

    master = build_master(nflv["players"], sleeper["players"], nflv["ids"], nflv["byes"])

    # --- Sleeper status/injury + trending (exact ID joins) ---
    sp = sleeper["players"].copy()
    sp["sleeper_id_num"] = pd.to_numeric(sp["sleeper_id"], errors="coerce").astype("Int64")
    status_cols = sp[["sleeper_id_num", "status", "injury_status", "injury_note"]].rename(
        columns={"status": "status_sleeper"}).dropna(subset=["sleeper_id_num"])
    master = master.merge(status_cols, left_on="sleeper_id", right_on="sleeper_id_num",
                          how="left").drop(columns=["sleeper_id_num"])
    tr = sleeper["trending"].copy()
    tr["sleeper_id"] = pd.to_numeric(tr["sleeper_id"], errors="coerce").astype("Int64")
    tr = tr.dropna(subset=["sleeper_id"]).drop_duplicates("sleeper_id")
    master = master.merge(tr, on="sleeper_id", how="left")

    # --- ESPN (exact ID join) ---
    espn = _parsed(cfg, "espn")
    if espn is not None:
        e = espn["adp"].copy()
        e["espn_id"] = pd.to_numeric(e["espn_id"], errors="coerce").astype("Int64")
        e = e.dropna(subset=["espn_id"]).drop_duplicates("espn_id")
        master = master.merge(
            e[["espn_id", "adp_espn", "rank_espn_std", "rank_espn_ppr"]],
            on="espn_id", how="left")

    # --- DynastyProcess ECR (FantasyPros id join, name fallback) ---
    dp = _parsed(cfg, "dynastyprocess")
    if dp is not None:
        ecr = dp["ecr"].copy()
        master["fantasypros_id_str"] = (
            pd.to_numeric(master["fantasypros_id"], errors="coerce").astype("Int64").astype(str))
        by_id = ecr.merge(master[["player_id", "fantasypros_id_str"]],
                          left_on="fantasypros_id", right_on="fantasypros_id_str")
        unmatched = ecr[~ecr["fantasypros_id"].isin(by_id["fantasypros_id"])].copy()
        if len(unmatched):
            mm = _match_map(unmatched, master, "dynastyprocess", review)
            unmatched = unmatched.merge(mm, on=["name", "position", "team"], how="left")
        ecr_ids = pd.concat([by_id, unmatched], ignore_index=True)
        ecr_ids = ecr_ids.dropna(subset=["player_id"]).drop_duplicates("player_id")
        master = master.merge(
            ecr_ids[["player_id", "ecr", "ecr_sd", "ecr_best", "ecr_worst"]],
            on="player_id", how="left").drop(columns=["fantasypros_id_str"])

    # --- FFC ADP (name match, wide per format) ---
    ffc = _parsed(cfg, "ffc")
    ffc_meta = None
    if ffc is not None:
        ffc_meta = ffc["meta"]
        adp = ffc["adp"].copy()
        mm = _match_map(adp, master, "ffc", review)
        adp = adp.merge(mm, on=["name", "position", "team"], how="left")
        for fmt in FFC_FORMATS:
            sub = adp[(adp["format"] == fmt) & adp["player_id"].notna()]
            sub = sub.drop_duplicates("player_id").set_index("player_id")
            ren = {
                "adp": f"adp_ffc_{fmt}", "adp_sd": f"adp_ffc_{fmt}_sd",
                "adp_high": f"adp_ffc_{fmt}_high", "adp_low": f"adp_ffc_{fmt}_low",
                "times_drafted": f"adp_ffc_{fmt}_n",
            }
            master = master.merge(sub[list(ren)].rename(columns=ren),
                                  left_on="player_id", right_index=True, how="left")

    # --- Harris ranks (name match) ---
    harris = _parsed(cfg, "harris")
    if harris is not None:
        hr = harris["ranks"].copy()
        mm = _match_map(hr, master, "harris", review)
        hr = hr.merge(mm, on=["name", "position", "team"], how="left")
        hr = hr.dropna(subset=["player_id"]).drop_duplicates("player_id").set_index("player_id")
        master = master.merge(
            hr[["rank_std", "rank_ppr"]].rename(
                columns={"rank_std": "rank_harris_std", "rank_ppr": "rank_harris_ppr"}),
            left_on="player_id", right_index=True, how="left")

    # --- Boris Chen tiers (name match; no team column on his CSVs) ---
    bc = _parsed(cfg, "borischen")
    if bc is not None:
        tiers = bc["tiers"].copy()
        tiers["team"] = None
        mm = _match_map(tiers, master, "borischen", review)
        tiers = tiers.merge(mm, on=["name", "position", "team"], how="left")
        for fmt in FFC_FORMATS:
            sub = tiers[(tiers["format"] == fmt) & tiers["player_id"].notna()]
            sub = sub.drop_duplicates("player_id").set_index("player_id")
            master = master.merge(sub[["tier"]].rename(columns={"tier": f"tier_bc_{fmt}"}),
                                  left_on="player_id", right_index=True, how="left")

    # --- 2025 stats + xFP + scoring variants ---
    master = master.merge(nflv["stats"], on="gsis_id", how="left")
    xfp = _parsed(cfg, "ffopportunity")
    if xfp is not None:
        master = master.merge(xfp["xfp"], on="gsis_id", how="left")
    master = add_point_columns(master)

    # --- Board picks -> draft_picks.parquet with player_id attached ---
    boards = _parsed(cfg, "ffc_boards")
    if boards is not None:
        picks = boards["picks"].copy()
        mm = _match_map(picks, master, "ffc_boards", review)
        picks = picks.merge(mm, on=["name", "position", "team"], how="left")
        picks["team"] = picks["team"].map(norm_team)
        picks.to_parquet(PROCESSED_DIR / "draft_picks.parquet", index=False)
        print(f"[build] draft_picks.parquet: {len(picks)} picks "
              f"from {picks['draft_id'].nunique()} boards")

    # --- Trim to the relevant universe ---
    has_signal = (
        master[[c for c in master.columns if c.startswith(("adp_", "ecr", "rank_", "tier_"))]]
        .notna().any(axis=1)
    )
    played_2025 = master["g"].fillna(0) > 0
    master = master[has_signal | played_2025].copy()

    # --- Staleness stamps ---
    for sc in cfg.enabled_sources():
        files = sorted(sc.raw_dir.glob("*"))
        if files:
            ts = datetime.fromtimestamp(max(f.stat().st_mtime for f in files), UTC)
            master[f"fetched_at_{sc.name}"] = ts.isoformat(timespec="seconds")

    dup = master["player_id"].duplicated().sum()
    if dup:
        raise SystemExit(f"BUG: {dup} duplicate player_id rows after build; refusing to write")

    front = ["player_id", "name", "team", "position", "bye_week", "status", "status_sleeper",
             "injury_status", "injury_note", "trend_add_count"]
    master = master[front + [c for c in master.columns if c not in front]]
    master.to_parquet(PROCESSED_DIR / "players.parquet", index=False)
    master.to_csv(PROCESSED_DIR / "players.csv", index=False)
    print(f"[build] players.parquet: {master.shape[0]} rows x {master.shape[1]} cols")

    pd.DataFrame(review).to_csv(PROCESSED_DIR / "id_match_review.csv", index=False)
    print(f"[build] id_match_review.csv: {len(review)} fuzzy/unmatched rows to eyeball")

    league = {
        "note": "Reference defaults only. The league layer overrides; nothing here is baked into the data.",
        "roster_defaults": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DST": 1,
                            "bench": 7},
        "my_draft": {"pick": "1.01", "type": "snake",
                     "keepers": [{"player": "Zay Flowers", "round": 4},
                                 {"player": "Chase Brown", "round": 5}]},
        "scoring_variants_carried": ["ppr", "half", "std"], "pass_td_variants": [4, 6],
    }
    (PROCESSED_DIR / "league.json").write_text(json.dumps(league, indent=2))

    meta = {"built_at": datetime.now(UTC).isoformat(timespec="seconds")}
    if ffc_meta is not None:
        meta["ffc_adp_windows"] = ffc_meta.to_dict(orient="records")
    (PROCESSED_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
