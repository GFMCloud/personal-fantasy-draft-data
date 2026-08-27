"""Project paths and the source registry (sources.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
SOURCES_TOML = ROOT / "sources.toml"


@dataclass
class SourceConfig:
    name: str
    enabled: bool
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def raw_dir(self) -> Path:
        d = RAW_DIR / self.name
        d.mkdir(parents=True, exist_ok=True)
        return d


@dataclass
class Config:
    sources: dict[str, SourceConfig]
    max_age_hours: float

    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources.values() if s.enabled]


def load_config(path: Path = SOURCES_TOML) -> Config:
    raw = tomllib.loads(path.read_text())
    sources = {}
    for name, opts in raw.get("sources", {}).items():
        opts = dict(opts)
        enabled = opts.pop("enabled", True)
        sources[name] = SourceConfig(name=name, enabled=enabled, options=opts)
    return Config(sources=sources, max_age_hours=raw.get("cache", {}).get("max_age_hours", 12))
