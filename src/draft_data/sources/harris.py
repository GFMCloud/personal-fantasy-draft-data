"""Harris Football expert ranks: Standard + PPR lists per position page.

Pages are Excel-exported HTML tables: rows of (rank, name, team) under section
headers "Standard Scoring" / "PPR Scoring". QB page has one list (scoring-agnostic).
parse() returns:
  ranks   name, team, position, rank_std, rank_ppr
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from draft_data.cache import cached_get, newest
from draft_data.config import SourceConfig

PAGES = {
    "qb": "https://www.harrisfootball.com/ranks-draft",
    "rb": "https://www.harrisfootball.com/rb-ranks-draft",
    "wr": "https://www.harrisfootball.com/wr-ranks-draft",
    "te": "https://www.harrisfootball.com/te-ranks-draft",
}


def fetch(cfg: SourceConfig, max_age_hours: float, force: bool = False) -> list[Path]:
    return [
        cached_get(PAGES[pos], cfg.raw_dir, pos, "html",
                   max_age_hours=max_age_hours, force=force)
        for pos in cfg.options["positions"]
    ]


def _parse_page(html: str, position: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    section = None  # None until a header is seen; QB page may have none
    lists: dict[str, list[tuple[int, str, str]]] = {"std": [], "ppr": []}
    for tr in soup.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        text = " ".join(cells)
        if "Standard Scoring" in text:
            section = "std"
            continue
        if "PPR Scoring" in text:
            section = "ppr"
            continue
        vals = [c for c in cells if c]
        if len(vals) >= 3 and vals[0].isdigit():
            rank, name, team = int(vals[0]), vals[1], vals[2]
            lists[section or "std"].append((rank, name, team))
    if not lists["ppr"]:  # single-list page (QB): same ranks both formats
        lists["ppr"] = lists["std"]
    std = pd.DataFrame(lists["std"], columns=["rank_std", "name", "team"])
    ppr = pd.DataFrame(lists["ppr"], columns=["rank_ppr", "name", "team"])
    df = std.merge(ppr, on=["name", "team"], how="outer")
    df["position"] = position.upper()
    return df


def parse(cfg: SourceConfig) -> dict[str, pd.DataFrame]:
    frames = []
    for pos in cfg.options["positions"]:
        path = newest(cfg.raw_dir, f"{pos}_*.html")
        if path is None:
            raise FileNotFoundError(f"harris raw missing: {pos}")
        frames.append(_parse_page(path.read_text(), pos))
    return {"ranks": pd.concat(frames, ignore_index=True)}
