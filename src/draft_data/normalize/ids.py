"""Player identity: canonical master table + matching for ID-less sources.

Canonical player_id = nflverse gsis_id; DSTs (no gsis) get "DST_<team>".
ID-joins (crosswalk) are exact. Name-based sources (FFC, Harris, Boris Chen,
board picks) go through match_names(): exact normalized-name match first, fuzzy
only for leftovers, and every fuzzy match is logged for human review.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd
from rapidfuzz import fuzz, process

FUZZY_THRESHOLD = 88
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
# Team-code aliases across sources, normalized to nflverse codes
TEAM_ALIASES = {
    "JAC": "JAX", "WSH": "WAS", "LA": "LAR", "OAK": "LV", "SD": "LAC", "STL": "LAR",
    # DynastyProcess/FantasyPros 3-letter style
    "LVR": "LV", "SFO": "SF", "GBP": "GB", "NOS": "NO", "KCR": "KC", "TBB": "TB",
    "NEP": "NE", "ARZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU",
}
# Formal first names -> the short form nflverse tends to carry (and vice versa is
# handled by normalizing both sides through this map)
NICKNAMES = {
    "kenneth": "kenny", "nicholas": "nick", "matthew": "matt", "michael": "mike",
    "christopher": "chris", "benjamin": "ben", "joshua": "josh", "cameron": "cam",
    "zachary": "zach", "jeffery": "jeff", "jeffrey": "jeff", "daniel": "dan",
    "william": "will", "robert": "rob", "alexander": "alex", "anthony": "tony",
}
# Full franchise names -> nflverse team codes (DST rows in name-only sources)
TEAM_NAMES = {
    "arizona cardinals": "ARI", "atlanta falcons": "ATL", "baltimore ravens": "BAL",
    "buffalo bills": "BUF", "carolina panthers": "CAR", "chicago bears": "CHI",
    "cincinnati bengals": "CIN", "cleveland browns": "CLE", "dallas cowboys": "DAL",
    "denver broncos": "DEN", "detroit lions": "DET", "green bay packers": "GB",
    "houston texans": "HOU", "indianapolis colts": "IND", "jacksonville jaguars": "JAX",
    "kansas city chiefs": "KC", "las vegas raiders": "LV", "los angeles chargers": "LAC",
    "los angeles rams": "LAR", "miami dolphins": "MIA", "minnesota vikings": "MIN",
    "new england patriots": "NE", "new orleans saints": "NO", "new york giants": "NYG",
    "new york jets": "NYJ", "philadelphia eagles": "PHI", "pittsburgh steelers": "PIT",
    "san francisco 49ers": "SF", "seattle seahawks": "SEA", "tampa bay buccaneers": "TB",
    "tennessee titans": "TEN", "washington commanders": "WAS",
}


def _gsis_seq(player_id: str) -> int:
    m = re.match(r"00-(\d+)$", str(player_id))
    return int(m.group(1)) if m else 0


def norm_team(team) -> str | None:
    if team is None or (isinstance(team, float) and pd.isna(team)):
        return None
    t = str(team).upper().strip()
    return TEAM_ALIASES.get(t, t) or None


def norm_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z ]", "", s.lower().replace(".", "").replace("'", ""))
    parts = [p for p in s.split() if p not in SUFFIXES]
    if parts:
        parts[0] = NICKNAMES.get(parts[0], parts[0])
    return " ".join(parts)


def build_master(nfl_players: pd.DataFrame, sleeper_players: pd.DataFrame,
                 ids: pd.DataFrame, byes: pd.DataFrame) -> pd.DataFrame:
    m = nfl_players.copy()
    m.loc[m["position"] == "FB", "position"] = "RB"  # rankers list FBs as RB

    # Players nflverse lists at a non-fantasy position but fantasy platforms rank
    # anyway (two-way players, e.g. Travis Hunter CB->WR): adopt Sleeper's position.
    sl = sleeper_players[
        sleeper_players["position"].isin(["QB", "RB", "WR", "TE", "K"])
    ].copy()
    # Sleeper's own gsis_id is often null for young players; recover via crosswalk
    xw = ids[["gsis_id", "sleeper_id"]].dropna().copy()
    xw["sleeper_id"] = pd.to_numeric(xw["sleeper_id"], errors="coerce").astype("Int64")
    sl["sleeper_id_num"] = pd.to_numeric(sl["sleeper_id"], errors="coerce").astype("Int64")
    sl = sl.merge(xw.rename(columns={"gsis_id": "gsis_xw"}),
                  left_on="sleeper_id_num", right_on="sleeper_id", how="left",
                  suffixes=("", "_xwj"))
    sl["gsis_id"] = sl["gsis_id"].fillna(sl["gsis_xw"])
    extra = sl[sl["gsis_id"].notna() & ~sl["gsis_id"].isin(m["gsis_id"])]
    if len(extra):
        m = pd.concat(
            [m, extra[["gsis_id", "name", "team", "position", "status"]]], ignore_index=True)

    m["player_id"] = m["gsis_id"]
    m["team"] = m["team"].map(norm_team)

    dst = sleeper_players[sleeper_players["position"] == "DEF"].copy()
    dst["team"] = dst["sleeper_id"].map(norm_team)
    dst = pd.DataFrame({
        "player_id": "DST_" + dst["team"],
        "gsis_id": None, "name": dst["name"], "position": "DST",
        "team": dst["team"], "status": "ACT",
    })
    m = pd.concat([m, dst], ignore_index=True)

    ids = ids.drop_duplicates("gsis_id").copy()
    for col in ("espn_id", "sleeper_id", "yahoo_id"):
        ids[col] = pd.to_numeric(ids[col], errors="coerce").astype("Int64")
    m = m.drop(columns=["espn_id"], errors="ignore").merge(ids, on="gsis_id", how="left")
    m.loc[m["position"] == "DST", "sleeper_id"] = pd.NA  # sleeper DEF ids are team codes
    m = m.merge(byes, on="team", how="left")
    return m.drop_duplicates("player_id").reset_index(drop=True)


def match_names(
    df: pd.DataFrame, master: pd.DataFrame, source: str, review: list[dict]
) -> pd.Series:
    """Return a player_id Series aligned to df (name/position/team columns).

    DST rows match by team; others by normalized name within position, team as
    tiebreaker, fuzzy as last resort (logged to `review`).
    """
    m = master[["player_id", "name", "position", "team", "status"]].copy()
    m["norm"] = m["name"].map(norm_name)
    by_pos = {pos: g for pos, g in m.groupby("position")}

    out = []
    for _, row in df.iterrows():
        pos = row["position"]
        team = norm_team(row.get("team"))
        if pos in ("DEF", "DST"):
            if not team:
                team = TEAM_NAMES.get(norm_name(row["name"]))
            out.append(f"DST_{team}" if team else None)
            continue
        pos = "K" if pos == "PK" else pos
        cands = by_pos.get(pos)
        if cands is None:
            out.append(None)
            continue
        n = norm_name(row["name"])
        exact = cands[cands["norm"] == n]
        if len(exact) > 1 and team:
            on_team = exact[exact["team"] == team]
            exact = on_team if len(on_team) else exact
        if len(exact) > 1:  # namesake collision, no team to split on: prefer actives
            act = exact[exact["status"].isin(["ACT", "Active"])]
            exact = act if len(act) == 1 else exact
        if len(exact) > 1:
            # last resort: newest gsis registration wins (retired namesakes carry
            # stale ACT flags); always logged so a human eyeballs the call
            keys = exact["player_id"].map(_gsis_seq)
            pick = exact.loc[keys.idxmax()]
            review.append({"source": source, "name": row["name"], "position": pos,
                           "team": team, "matched_to": f"{pick['name']} (gsis-recency)",
                           "score": 0})
            exact = exact.loc[[keys.idxmax()]]
        if len(exact) == 1:
            out.append(exact["player_id"].iloc[0])
            continue
        if len(exact) > 1:
            # same name, same position, no team tiebreak: send to review, pick none
            review.append({"source": source, "name": row["name"], "position": pos,
                           "team": team, "matched_to": "AMBIGUOUS", "score": 0})
            out.append(None)
            continue
        hit = process.extractOne(n, cands["norm"], scorer=fuzz.token_sort_ratio,
                                 score_cutoff=FUZZY_THRESHOLD)
        if hit is None:
            review.append({"source": source, "name": row["name"], "position": pos,
                           "team": team, "matched_to": "NO_MATCH", "score": 0})
            out.append(None)
        else:
            matched = cands.loc[hit[2]]
            review.append({"source": source, "name": row["name"], "position": pos,
                           "team": team, "matched_to": matched["name"],
                           "score": round(hit[1], 1)})
            out.append(matched["player_id"])
    return pd.Series(out, index=df.index, dtype="object")
