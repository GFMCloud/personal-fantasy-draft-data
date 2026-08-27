"""validate: schema, null audit, and sanity assertions on processed outputs."""

from __future__ import annotations

import pandas as pd

from draft_data.config import PROCESSED_DIR

KEEPERS = ["Zay Flowers", "Chase Brown"]


def _check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    return ok


def run_validate() -> int:
    ppath = PROCESSED_DIR / "players.parquet"
    if not ppath.exists():
        print("FAIL  players.parquet missing (run refresh first)")
        return 1
    df = pd.read_parquet(ppath)
    ok = True

    ok &= _check("player_id unique", df["player_id"].is_unique, f"{len(df)} rows")
    ok &= _check("identity columns non-null",
                 df[["player_id", "name", "position"]].notna().all().all())
    ok &= _check("no player on two teams",
                 df.groupby("player_id")["team"].nunique().le(1).all())

    core = df[["name", "team", "position", "bye_week"]].notna().all(axis=1)
    core &= df[["adp_ffc_ppr", "adp_espn"]].notna().any(axis=1) & df["ecr"].notna()
    ok &= _check("players fully populated (identity+bye+ADP+ECR) >= 300",
                 int(core.sum()) >= 300, f"{int(core.sum())} players")

    both = df.dropna(subset=["ecr", "adp_ffc_ppr"])
    rho = both["ecr"].rank().corr(both["adp_ffc_ppr"].rank())  # spearman, no scipy
    ok &= _check("ADP roughly monotonic with ECR (spearman > 0.9)", rho > 0.9,
                 f"rho={rho:.3f}, n={len(both)}")

    for fmt in ("ppr", "half", "std"):
        sub = df.dropna(subset=[f"adp_ffc_{fmt}"])
        bounds = (
            (sub[f"adp_ffc_{fmt}_high"] <= sub[f"adp_ffc_{fmt}"] + 1)
            & (sub[f"adp_ffc_{fmt}"] <= sub[f"adp_ffc_{fmt}_low"] + 1)
        ).all()
        ok &= _check(f"FFC {fmt}: high <= adp <= low", bool(bounds), f"n={len(sub)}")

    for name in KEEPERS:
        row = df[df["name"] == name]
        ok &= _check(f"keeper present: {name}", len(row) == 1,
                     row["team"].iloc[0] if len(row) else "MISSING")

    stat = df[df["g"].notna() & (df["g"] > 0)]
    ok &= _check("2025 stats block populated for players with games",
                 stat["pts_2025_ppr_pass4"].notna().all(), f"n={len(stat)}")

    kpath = PROCESSED_DIR / "draft_picks.parquet"
    if kpath.exists():
        picks = pd.read_parquet(kpath)
        per = picks.groupby("draft_id")
        ok &= _check("draft_picks: pick_overall unique within each draft",
                     per["pick_overall"].apply(lambda s: s.is_unique).all(),
                     f"{picks['draft_id'].nunique()} drafts, {len(picks)} picks")
        ok &= _check("draft_picks: player match rate >= 98%",
                     picks["player_id"].notna().mean() >= 0.98,
                     f"{picks['player_id'].notna().mean()*100:.1f}%")

    print("\nvalidate:", "ALL PASS" if ok else "FAILURES ABOVE")
    return 0 if ok else 1
