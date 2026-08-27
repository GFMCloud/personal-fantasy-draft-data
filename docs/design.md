# Fantasy draft tool: data layer design

Status: **awaiting approval** (Phase 1 gate). See `decisions.md` for the rulings
behind every choice here.

## Purpose

Deliver clean, normalized, cached, league-agnostic inputs for downstream modules
(VORP, tier breaks, pick-survival odds). This layer knows nothing about any specific
league; it carries every scoring variant and every ADP source side by side, and the
next layer chooses.

## Sources and roles

| Source | Role | Access | Fetch |
|---|---|---|---|
| nflverse (`nfl_data_py`) | Canonical player IDs (gsis), 2025 season stats, bye weeks, ID crosswalk (`import_ids`) | Free, no key | Library calls |
| FFC | ADP with std-dev, per format (PPR / half / standard) | Free REST API | `GET /adp` per format |
| ESPN | ADP point estimate + platform rank (Standard, PPR) | Unofficial public JSON endpoint, no auth | `leaguedefaults/3?view=kona_player_info` |
| Sleeper | Injury/status flags, secondary ID crosswalk | Free API, no key | `GET /players/nfl` |
| Harris Football | Expert ranks, Standard + PPR, per position | Plain HTML pages, no key | fetch + parse position pages |

No API keys are required by any enabled source. `.env.example` will exist but list
nothing mandatory. ESPN is flagged in-code as `unofficial: true`; if the endpoint
breaks, the module fails loudly and the rest of the refresh continues.

**Removability:** `sources.toml` holds an `enabled` flag per source. A disabled
source is skipped by `make refresh`, its columns come out null, and validation
adjusts expectations accordingly. `make refresh-<source>` targets each one alone.

**Caching:** every `fetch()` writes raw responses to `data/raw/<source>/` with a
timestamp; re-fetch is skipped if the raw file is under N hours old (default 12)
unless `--force`.

## ID normalization

- Canonical key: `player_id` = nflverse `gsis_id`.
- Crosswalk table from `nfl_data_py.import_ids()` (ffverse): maps gsis to sleeper,
  espn, and friends. Sleeper's player dump is the secondary crosswalk.
- FFC and Harris rows carry no usable IDs: matched by normalized name + team +
  position. Exact normalized match first; fuzzy (rapidfuzz) only for leftovers.
- **Every fuzzy match** lands in `data/processed/id_match_review.csv` for eyeballing.
  No silent name-only merges.
- Target: at least 98% match rate for the top-300 by ADP; the unmatched list is
  printed in full, not summarized.

## Output schema: `data/processed/players.parquet`

One row per player. Sortable, joinable, league-agnostic.

| Column group | Columns | Source |
|---|---|---|
| Identity | `player_id`, `name`, `team`, `position`, `bye_week` | nflverse |
| Crosswalk | `sleeper_id`, `espn_id` | ids crosswalk |
| Status | `status`, `injury_note` | Sleeper |
| ADP: FFC | `adp_ffc_ppr`, `adp_ffc_ppr_sd`, `adp_ffc_half`, `adp_ffc_half_sd`, `adp_ffc_std`, `adp_ffc_std_sd` | FFC |
| ADP: ESPN | `adp_espn`, `rank_espn_std`, `rank_espn_ppr` | ESPN |
| Expert ranks | `rank_harris_std`, `rank_harris_ppr` | Harris |
| 2025 raw stats | `g`, `targets`, `receptions`, `rec_yards`, `rec_td`, `rush_att`, `rush_yards`, `rush_td`, `pass_att`, `pass_yards`, `pass_td`, `interceptions`, `fumbles_lost`, `target_share`, `snap_pct`, `rz_touches` | nflverse |
| 2025 points (computed) | `pts_2025_{ppr,half,std}_{pass4,pass6}` (6 columns), plus matching `ppg_` columns | computed from raw stats |
| Staleness | `fetched_at_<source>` per enabled source | pipeline |

Points are computed from raw components so every scoring variant is exact, including
the 4-vs-6 passing TD split. Downstream layers can also recompute from the raw block
with any custom rules (bonuses, TE premium) without touching this layer.

Side artifacts:

- `data/processed/players.csv` mirror for eyeballing.
- `data/processed/id_match_review.csv` (fuzzy matches).
- `data/processed/league.json`: **reference defaults only**, never authoritative.
  Roster defaults (1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX / 1 K / 1 DEF, 7 bench), the
  known keepers (Zay Flowers R4, Chase Brown R5, pick 1.01, snake), and a
  `"note": "defaults; the league layer overrides"`.

## Directory layout

```
fantasy-draft-data/
├── src/draft_data/
│   ├── sources/          # one module per source: nflverse.py, ffc.py, espn.py, sleeper.py, harris.py
│   ├── normalize/        # ids.py (crosswalk + fuzzy), scoring.py (variant point calc), build.py
│   └── cli/              # refresh, validate, query entry points
├── data/raw/<source>/    # gitignored, timestamped raw responses
├── data/processed/       # gitignored artifacts
├── docs/                 # decisions.md, design.md, next.md
├── tests/
├── sources.toml          # enabled flags + per-source config
├── Makefile              # refresh, refresh-<source>, validate, test, query
├── .env.example          # names only; currently no required vars
└── pyproject.toml        # uv-managed
```

## Dependencies

`nfl_data_py`, `pandas`, `pyarrow`, `duckdb`, `requests`, `rapidfuzz`, `beautifulsoup4`
(Harris pages), `pytest` + `ruff` (dev). All installed via uv. Anything beyond this
list gets asked about first.

## Interfaces

Each source module: `fetch(force: bool) -> list[Path]` (raw files) and
`parse() -> pd.DataFrame` with a documented schema. `make refresh` runs
fetch+parse for enabled sources, then normalize, then writes artifacts.
`make validate` runs schema/null/sanity checks (ADP roughly monotonic with ranks,
no player on two teams, keepers present). `make query "..."` runs DuckDB SQL
against the parquet.

## Build order and estimate

| Step | What | Est. |
|---|---|---|
| 1 | Scaffold: layout, Makefile, sources.toml, empty test suite green, git init | 0.5 h |
| 2a | nflverse module (proves the pipeline) | 1.0 h |
| 2b | FFC module (3 formats) | 0.5 h |
| 2c | Sleeper module | 0.5 h |
| 2d | ESPN module (unofficial endpoint, loud failure mode) | 1.0 h |
| 2e | Harris module (HTML parse, most fragile) | 1.0 h |
| 3 | ID normalization + review CSV + match-rate evidence | 1.5 h |
| 4 | Normalized parquet + scoring variants + league.json | 1.0 h |
| 5 | validate + query + the three demo queries | 1.0 h |
| 6 | Hand-off docs, GitHub repo per standard, final commit | 0.5 h |

Total: roughly 8.5 hours of build. Evidence (real output, row counts, sample rows,
spot checks on Zay Flowers / Chase Brown / one rookie) after every step.

## Amendment 1: research-driven additions (proposed 2026-08-26, pending approval)

Deep research on published draft-tool methods (survival models, tier clustering, VBD
variants, open-source simulators) produced these changes. Full findings and source
URLs: `docs/research-2026-08-26.md`.

**Why it matters:** every credible pick-survival method needs ADP mean + sd (already
planned) and benefits from distribution tails; every tier method (Boris Chen's
Gaussian mixture is the standard) needs expert-consensus rank mean/sd, which we lost
by skipping FantasyPros. Both gaps close for free.

New sources (all free, no keys, verified responding):

| Source | What it adds | Effort |
|---|---|---|
| DynastyProcess data repo (nflverse-adjacent, weekly refresh) | FantasyPros ECR mean / sd / best / worst per player, with platform IDs attached. Restores the `ecr_*` column block without a FantasyPros subscription, and is the exact input for Gaussian-mixture tier clustering downstream. | small |
| Boris Chen fftiers S3 CSVs | His published tier number per player per format. A battle-tested tier label to carry now and to validate our own clustering against later. | trivial |
| Sleeper trending adds endpoint | `trend_add_count`: market-heat signal that leads ADP by days near draft time. | trivial |
| nflverse `import_draft_picks` | Rookie draft capital (`draft_round`, `draft_overall`). | trivial |
| ffopportunity releases (nflverse) | 2025 expected fantasy points (`xfp_2025`) and actual-minus-expected (`fp_over_xfp_2025`): the standard regression/luck adjustment before VORP. | small |

Enrichments to already-planned sources:

- FFC: also keep `adp_*_high`, `adp_*_low`, `times_drafted` per format (already in the
  JSON) plus snapshot metadata (`total_drafts`, `start_date`, `end_date`) so staleness
  and sample size are queryable facts. Trivial.
- ID crosswalk: carry `fantasypros_id`, `yahoo_id` alongside `sleeper_id`, `espn_id`
  from `import_ids()`. Trivial; shrinks the fuzzy-matching surface for any future source.

Optional module (medium, flagged off by default until wanted): `ffc_boards`, which
pulls a few hundred completed FFC mock-draft boards (public, free, updated every 30
min) into a pick-level `draft_picks.parquet`. This is the only free path to an
*empirical* survival curve instead of a normal-distribution assumption, and the
normal assumption is weakest exactly in the round-2/3 zone where picks 24/25 live.
Also the training data any future opponent-model simulator wants.

Explicitly rejected after research: Underdog ADP (best-ball skew, login-gated),
Vegas win totals (free feed dead since 2020; keyed API not worth it), scraping
FantasyPros HTML (DynastyProcess republishes the same data cleanly), per-player
stat columns for K/DST (team-level rows suffice; weekly streaming value dominates),
MFL ADP (redundant with FFC + ESPN).

Revised estimate: +1.5 h core additions (total ~10 h); `ffc_boards` is +2 h more if
enabled.

## Definition of done (unchanged from kickoff, league-agnostic reading)

`make refresh && make validate` succeeds from a clean clone with no env vars set,
produces `players.parquet` with 300+ players fully populated on identity, ADP (from
enabled sources), and 2025 stat columns, and "who is likely on the board at pick 24"
is answerable with a single DuckDB query using whichever ADP column the caller picks.
