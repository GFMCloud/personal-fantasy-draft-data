"""FFC completed mock-draft boards: pick-level logs for empirical survival curves.

Board pages are immutable once completed, so each board is cached forever; the
index is re-read each refresh and only new boards are fetched. parse() returns:
  picks   draft_id, format, teams, round, pick_in_round, pick_overall,
          name, position, team
"""

from __future__ import annotations

import html as htmllib
import re
import time
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from draft_data.cache import fetch_text
from draft_data.config import SourceConfig

INDEX = "https://fantasyfootballcalculator.com/mock-draft/results/format/{fmt}/teams/{teams}"
BOARD = "https://fantasyfootballcalculator.com/draft/{draft_id}"
FMT_KEY = {"ppr": "ppr", "half-ppr": "half", "standard": "std"}
CELL_RE = re.compile(r"^(QB|RB|WR|TE|K|DEF|PK)$")


def fetch(cfg: SourceConfig, max_age_hours: float, force: bool = False) -> list[Path]:
    o = cfg.options
    target = o.get("boards_per_format", 100)
    out = []
    for fmt in o["formats"]:
        key = FMT_KEY[fmt]
        have = {p.stem.split("_")[1] for p in cfg.raw_dir.glob(f"board-{key}_*.html")}
        # walk index pages until we have `target` boards for this format
        page = 1
        while len(have) < target and page <= 20:
            idx = fetch_text(INDEX.format(fmt=fmt, teams=o["teams"]) + f"?page={page}")
            ids = list(dict.fromkeys(re.findall(r"/draft/(\d+)", idx)))
            if not ids:
                break
            for did in ids:
                if did in have or len(have) >= target:
                    continue
                board = fetch_text(BOARD.format(draft_id=did))
                path = cfg.raw_dir / f"board-{key}_{did}.html"
                path.write_text(board)
                have.add(did)
                time.sleep(0.25)  # polite pacing
            page += 1
        out.extend(sorted(cfg.raw_dir.glob(f"board-{key}_*.html")))
        print(f"[ffc_boards] {key}: {len(have)} boards cached")
    return out


def _parse_board(path: Path, key: str, teams: int) -> list[dict]:
    draft_id = path.stem.split("_")[1]
    soup = BeautifulSoup(path.read_text(), "lxml")
    rows = []
    round_no = 0
    for tr in soup.find_all("tr"):
        cells = []
        for td in tr.find_all("td"):
            a = td.find("a", title=True)
            if a is None:
                continue
            txt = td.get_text(" ", strip=True)
            m = re.search(r"\b(QB|RB|WR|TE|PK|K|DEF)\b\s*\(([A-Z]{2,3})\)", txt)
            cells.append({
                "name": htmllib.unescape(a["title"]),
                "position": (m.group(1) if m else None),
                "team": (m.group(2) if m else None),
            })
        if len(cells) != teams:
            continue  # not a full pick row
        round_no += 1
        ordered = cells if round_no % 2 == 1 else list(reversed(cells))
        for i, c in enumerate(ordered, start=1):
            rows.append({
                "draft_id": draft_id, "format": key, "teams": teams,
                "round": round_no, "pick_in_round": i,
                "pick_overall": (round_no - 1) * teams + i,
                **c,
            })
    return rows


def parse(cfg: SourceConfig) -> dict[str, pd.DataFrame]:
    teams = cfg.options["teams"]
    rows = []
    for fmt in cfg.options["formats"]:
        key = FMT_KEY[fmt]
        for path in sorted(cfg.raw_dir.glob(f"board-{key}_*.html")):
            rows.extend(_parse_board(path, key, teams))
    if not rows:
        raise FileNotFoundError("ffc_boards raw missing (run refresh)")
    df = pd.DataFrame(rows)
    df.loc[df["position"] == "PK", "position"] = "K"
    return {"picks": df}
