"""refresh: fetch enabled sources, then rebuild the normalized outputs."""

from __future__ import annotations

import traceback

from draft_data.config import load_config
from draft_data.sources import SOURCE_ORDER, get_module


def run_refresh(source: str | None = None, force: bool = False, build: bool = True) -> int:
    cfg = load_config()
    names = [source] if source else [n for n in SOURCE_ORDER if n in cfg.sources]
    failed = []
    for name in names:
        sc = cfg.sources.get(name)
        if sc is None:
            print(f"[{name}] unknown source"); return 2
        if not sc.enabled:
            print(f"[{name}] disabled, skipping"); continue
        try:
            paths = get_module(name).fetch(sc, cfg.max_age_hours, force=force)
            print(f"[{name}] fetched: {len(paths)} raw file(s)")
        except Exception:  # noqa: BLE001 -- one broken source must not kill the refresh
            print(f"[{name}] FAILED (continuing with other sources)")
            traceback.print_exc()
            failed.append(name)
    if build:
        from draft_data.normalize.build import build_outputs

        build_outputs(cfg)
    if failed:
        print(f"refresh finished with failures: {', '.join(failed)}")
        return 1
    return 0
