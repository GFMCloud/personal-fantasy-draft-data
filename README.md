# personal-fantasy-draft-data

**What is this?** League-agnostic data layer for a personal fantasy football draft
tool: pulls stats, ADP, expert ranks, tiers, and real mock-draft pick logs from free
sources, normalizes everything onto one canonical player ID, and produces clean
Parquet artifacts for downstream draft modules (VORP, tier breaks, pick-survival).

**Owner.** Graham (personal). Part of the fantasy draft tool effort; the draft
engine / league layer is a separate future module.

**How to run.**

```bash
uv sync                 # once: install deps (Python 3.12 via uv)
make refresh            # fetch all enabled sources + rebuild outputs
make validate           # schema, null, and sanity checks
make query SQL="SELECT name, ecr FROM players ORDER BY ecr LIMIT 10"
make test               # unit tests
make board              # regenerate data/processed/board.html + board_<slug>.html per leagues/*.json
```

No API keys required; every enabled source is free. Sources are toggled in
`sources.toml` (`enabled = false` nulls that source's columns and nothing else
breaks). Outputs land in `data/processed/`: `players.parquet` (one row per player),
`draft_picks.parquet` (pick-level logs from real FFC mock drafts), `players.csv`
(eyeball mirror), `id_match_review.csv` (every fuzzy/judgment ID match),
`league.json` (reference defaults only), `meta.json` (staleness).

Design and rulings: `docs/design.md`, `docs/decisions.md`. What the next module
needs: `docs/next.md`.

**Status.** Active.
