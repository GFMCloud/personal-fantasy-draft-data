"""Source registry: every module exposes fetch(cfg, max_age_hours, force) and parse(cfg)."""

from importlib import import_module

SOURCE_ORDER = [
    "nflverse",
    "ffc",
    "sleeper",
    "espn",
    "harris",
    "dynastyprocess",
    "borischen",
    "ffopportunity",
    "ffc_boards",
]


def get_module(name: str):
    return import_module(f"draft_data.sources.{name}")
