"""Raw-response caching: timestamped files, freshness checks, polite HTTP."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import requests

USER_AGENT = "draft-data/0.1 (personal draft tool)"


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def newest(raw_dir: Path, pattern: str) -> Path | None:
    files = sorted(raw_dir.glob(pattern))
    return files[-1] if files else None


def is_fresh(path: Path | None, max_age_hours: float) -> bool:
    if path is None or not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < max_age_hours * 3600


def fetch_text(url: str, *, headers: dict | None = None, timeout: int = 30) -> str:
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    resp = requests.get(url, headers=h, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def cached_get(
    url: str,
    raw_dir: Path,
    stem: str,
    suffix: str,
    *,
    max_age_hours: float,
    force: bool = False,
    headers: dict | None = None,
) -> Path:
    """GET url and store as raw_dir/<stem>_<ts>.<suffix>; reuse a fresh copy."""
    existing = newest(raw_dir, f"{stem}_*.{suffix}")
    if not force and is_fresh(existing, max_age_hours):
        return existing
    text = fetch_text(url, headers=headers)
    path = raw_dir / f"{stem}_{timestamp()}.{suffix}"
    path.write_text(text)
    return path
