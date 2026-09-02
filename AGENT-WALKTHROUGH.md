# Agent walkthrough: fantasy-draft-data

Written 2026-09-02 for whoever (human or agent) picks this repo up from a fresh
clone. It explains what is here, how to run it, what the outputs mean, which
parts are worth taking on their own, and which parts still carry the original
owner's league and should be changed before you rely on them.

Read this first. Then `docs/next.md` (what to build on top), `docs/design.md`
(the full column dictionary), and `docs/research-2026-08-26.md` (methods and
source URLs for survival models, tiers, and VORP).

## 1. What this is, in three sentences

A Python pipeline that pulls fantasy football draft inputs from nine free,
keyless sources, matches every player onto one canonical ID, and writes two
Parquet tables: one row per player with ADP, expert ranks, tiers, 2025 stats
and scoring-variant points side by side, and one row per pick from 290 real
12-team mock drafts. It is league-agnostic: PPR, half-PPR and standard are all
carried, passing TDs at both 4 and 6, and no roster or scoring is baked in.
There is no draft engine, projections, or optimizer here; this is the data
layer the next module builds on.

## 2. Quickstart

Everything runs from the repo root. Requires Python 3.11+ and `uv`.

```bash
uv sync            # install deps into .venv
make refresh       # fetch all sources, then build data/processed/
make validate      # sanity checks; expect ALL PASS
make test          # 7 unit tests
make board         # data/processed/board.html, a sortable browser view
make query SQL="SELECT name, team, position, adp_ffc_half, ecr FROM players ORDER BY ecr LIMIT 15"
```

Notes on the first refresh:

- **No data ships in the repo.** `data/` is gitignored. Nothing exists until
  `make refresh` runs. It needs network access and no API keys.
- The first run downloads roughly 90 MB of raw responses (ESPN and Sleeper
  dumps are the bulk) and fetches ~300 completed mock-draft board pages at a
  polite 0.25 s pace. Expect several minutes. Boards are immutable and cached
  forever, so later refreshes only pick up new ones.
- Raw responses under 12 hours old are reused (`sources.toml` `[cache]`).
  `make refresh` re-fetches only what is stale; `uv run draft-data refresh --force`
  ignores the cache. Re-run with `--force` the morning of a draft, since FFC
  ADP is a trailing 7-day window and camp news moves it within a day.
- One source failing does not stop the refresh. The others complete, the
  failed source's columns come out null, and the exit code is 1. ESPN is the
  one most likely to break (undocumented endpoint).
- `make refresh-<source>` refreshes one source (`make refresh-ffc`).

## 3. Repo map

```
sources.toml                 source registry: enabled flags and per-source options
Makefile                     the entry points above
src/draft_data/
  cli/                       refresh, validate, query subcommands (draft-data CLI)
  sources/<name>.py          one module per source: fetch() caches raw, parse() returns DataFrames
  normalize/ids.py           canonical ID master table + name matcher for ID-less sources
  normalize/scoring.py       point formulas for every carried scoring variant
  normalize/build.py         joins everything and writes data/processed/
  board_template.html        editable source for the generated board pages
scripts/build_board.py       generates board.html (+ one per leagues/*.json if present)
docs/                        design, decisions, next-steps brief, research sweep
tests/                       matcher, team aliases, DST handling, scoring variants
data/raw/<source>/           gitignored, timestamped raw responses
data/processed/              gitignored outputs, described in section 4
```

Rule the repo follows: edit generators, never outputs. Board HTML comes from
the template; processed files come from `make refresh`.

## 4. Outputs

All under `data/processed/` after a refresh. Numbers below are from the
2026-08-27 build and will differ slightly on yours.

### players.parquet (and players.csv mirror)

One row per player, 1,026 rows by 91 columns. Positions: WR 369, RB 245,
TE 198, QB 127, K 56, DST 31. A row exists if the player has any ADP, rank or
tier signal, or played a 2025 game.

| Column group | Columns | Notes |
|---|---|---|
| Identity | `player_id`, `name`, `team`, `position`, `bye_week` | `player_id` is the nflverse gsis id; defenses are `DST_<team>` |
| Crosswalk | `gsis_id`, `sleeper_id`, `espn_id`, `yahoo_id`, `fantasypros_id`, `pfr_id`, `mfl_id` | join keys to other platforms |
| Status | `status`, `status_sleeper`, `injury_status`, `injury_note`, `trend_add_count` | Sleeper; trend = adds in the last 48 h, a market-heat signal |
| Draft capital | `draft_year`, `draft_round`, `draft_pick` | rookies have these and null 2025 stats |
| ESPN | `adp_espn`, `rank_espn_std`, `rank_espn_ppr` | point estimate, no sd; 984 players deep |
| ECR | `ecr`, `ecr_sd`, `ecr_best`, `ecr_worst` | FantasyPros consensus via DynastyProcess; **PPR flavored**; 516 players |
| FFC ADP | `adp_ffc_{ppr,half,std}` plus `_sd`, `_high`, `_low`, `_n` | mean, sd, tails, sample size per format; roughly 220 to 270 players per format, which is the site's real depth |
| Expert ranks | `rank_harris_std`, `rank_harris_ppr` | Harris Football; ~250 players; no kickers |
| Tiers | `tier_bc_{ppr,half,std}` | Boris Chen Gaussian-mixture tier number; ~200 players |
| 2025 stats | `g`, `targets`, `receptions`, `rec_yards`, `rec_td`, `rush_att`, `rush_yards`, `rush_td`, `pass_att`, `pass_yards`, `pass_td`, `pass_int`, `two_pt`, `fumbles_lost`, `target_share`, `wopr`, `snap_pct`, `rz_carries`, `rz_targets`, `rz_touches` | nflverse regular season aggregates |
| Expected points | `fp_ffv_2025`, `xfp_2025`, `fp_over_xfp_2025` | ffopportunity; negative `fp_over_xfp` suggests positive regression |
| Points | `pts_2025_{std,half,ppr}_{pass4,pass6}` and matching `ppg_` | computed from the raw stats block, so any custom rule can be recomputed |
| Staleness | `fetched_at_<source>` | one per enabled source |

Scoring base used for the `pts_` columns: 0.04 per pass yard, -2 per INT,
0.1 per rush or receiving yard, 6 per rush or receiving TD, 2 per two-point,
-2 per fumble lost; reception 0 / 0.5 / 1 by format; pass TD 4 or 6. If your
league has bonuses or TE premium, recompute from the raw stats block.

### draft_picks.parquet

44,892 picks from 290 completed FFC 12-team mock drafts (about 100 per format).
Columns: `draft_id`, `format` (ppr/half/std), `teams`, `round`, `pick_in_round`,
`pick_overall`, `name`, `position`, `team`, `player_id`. Player match rate is
100%. This is the only free pick-level draft log, and it is what makes an
empirical "still on the board at pick N" estimate possible instead of a
normal-distribution assumption.

### The rest

- `id_match_review.csv`: every fuzzy or judgment ID match. Seven rows in the
  reference build. Worth one human glance after each refresh.
- `meta.json`: build timestamp and the FFC ADP sample window per format
  (total drafts, start and end dates). Check this before trusting ADP.
- `league.json`: roster defaults and, currently, the original owner's draft
  slot and keepers. See section 8. Nothing reads it except the board script.
- `board.html`: sortable table of every player with ADP, ECR, tier, Harris
  rank, empirical availability at two picks, 2025 PPG, luck, and trend heat.
  Open it in a browser. The availability columns default to picks 24 and 26.

## 5. Sources

| Source | What it contributes | How it joins | Fragility |
|---|---|---|---|
| nflverse (`nflreadpy`) | canonical IDs, 2025 stats, snap %, red-zone usage, byes, ID crosswalk | is the master table | stable, maintained |
| Sleeper | status and injury flags, trending adds, second crosswalk, DST rows | exact `sleeper_id` | stable public API |
| FFC | ADP mean/sd/high/low/n per format, sample window | name + team + position | stable REST API, free with attribution |
| ESPN | ADP point estimate and platform ranks | exact `espn_id` | undocumented endpoint, may break any week |
| Harris Football | expert ranks std and PPR per position | name + team + position, fuzzy fallback | HTML parse, most fragile merge |
| DynastyProcess | FantasyPros ECR mean/sd/best/worst | `fantasypros_id`, name fallback | weekly GitHub refresh, GPL-3 data |
| Boris Chen | tier number per format | name + position (his CSVs carry no team) | S3 CSVs, stable |
| ffopportunity | 2025 expected points and actual minus expected | exact gsis id | nflverse release asset |
| FFC boards | pick-level mock draft logs | name + team + position | HTML parse of immutable pages |

Any source can be disabled in `sources.toml` with `enabled = false`. Its
columns come out null and nothing else breaks, except nflverse and Sleeper,
which the master table requires.

## 6. Query recipes

`make query` opens DuckDB with two views: `players` and `picks`. From Python,
read the Parquet files directly with pandas or polars.

Best available by ECR at half-PPR, with ADP and tier:

```bash
make query SQL="SELECT name, position, team, ecr, adp_ffc_half, adp_ffc_half_sd, tier_bc_half FROM players WHERE ecr IS NOT NULL ORDER BY ecr LIMIT 40"
```

Empirical availability: share of half-PPR mock drafts in which a player was
still on the board when pick 30 came up (this is what board.html shows):

```bash
make query SQL="SELECT name, position, COUNT(*) AS boards, ROUND(100.0 * AVG(CASE WHEN pick_overall >= 30 THEN 1 ELSE 0 END), 1) AS pct_available_at_30 FROM picks WHERE format = 'half' GROUP BY name, position HAVING COUNT(*) >= 20 ORDER BY pct_available_at_30 DESC, boards DESC LIMIT 40"
```

Regression candidates: players who scored well under expectation last year:

```bash
make query SQL="SELECT name, position, team, xfp_2025, fp_ffv_2025, fp_over_xfp_2025, adp_ffc_ppr FROM players WHERE fp_over_xfp_2025 IS NOT NULL AND adp_ffc_ppr IS NOT NULL ORDER BY fp_over_xfp_2025 LIMIT 25"
```

Parametric availability (normal CDF on FFC ADP), in Python:

```python
import math, pandas as pd
p = pd.read_parquet("data/processed/players.parquet")
pick = 30
fmt = "half"
adp, sd = p[f"adp_ffc_{fmt}"], p[f"adp_ffc_{fmt}_sd"].fillna(p[f"adp_ffc_{fmt}"] / 4)
p["p_available"] = [
    1 - 0.5 * (1 + math.erf((pick - a) / (s * math.sqrt(2)))) if pd.notna(a) else None
    for a, s in zip(adp, sd)
]
print(p.dropna(subset=["p_available"]).sort_values("ecr")
        [["name", "position", "ecr", f"adp_ffc_{fmt}", "p_available"]].head(40).to_string())
```

Run that with `uv run python -c '...'` or as a script from the repo root.

## 7. Known quirks, in order of how often they bite

- **FFC depth is roughly 220 to 270 players per format.** Absence means FFC has no data, not
  "last pick". Below that, use `adp_espn` (984 deep) or `ecr` (516 deep).
- **ECR is PPR only.** No free per-format consensus exists. Per-format signal
  comes from FFC ADP and Boris Chen tiers.
- **Do not mix FFC and ESPN ADP in one distribution.** Different drafter
  populations; ESPN runs later on the same players.
- **Public ADP knows nothing about your league's keepers.** Remove all kept
  players from the pool and from any survival denominator before modeling.
- **DSTs are team-level rows** with no player stats. Kickers have stats but no
  Harris rank.
- **Rookies** have null 2025 stats and carry draft capital instead.
- **The normal-CDF assumption is worst in rounds 2 and 3**, which is exactly
  where the empirical `picks` table earns its keep.

## 8. What is specific to the original owner's league, and what to change

The data is clean. The code and docs still name the original league in a few
places. None of it is sensitive, but two of them affect behavior.

| Where | What | Effect on you | Fix |
|---|---|---|---|
| `src/draft_data/cli/validate.py` line 9 | `KEEPERS = ["Zay Flowers", "Chase Brown"]` | `make validate` asserts those two players exist; harmless while they are in the pool, misleading otherwise | replace with your keepers or delete the loop |
| `src/draft_data/normalize/build.py` near line 185 | writes `league.json` with pick 1.01 and those keepers | `build_board.py` stars them as "your keeper" on the default board | edit the `my_draft` block, or point the board at your own `leagues/<slug>.json` |
| `scripts/build_board.py` | default availability picks (24, 26); reads keepers from `league.json`; builds one extra board per `leagues/*.json` | cosmetic | create `leagues/mine.json` with `title`, `slug`, `teams`, `default_format`, `avail_picks`, `keepers` (list of `{"player", "round", "pos"}`), `remove_keepers` |
| `docs/*.md` | mentions of Zay Flowers, Chase Brown, pick 1.01, picks 24/25 | context only | read "picks 24/25" as "the picks you care about" |
| `tests/test_normalize.py` | those names as fixtures | none | leave |

## 9. Taking pieces on their own

Each of these stands alone if you only want part of the repo:

- **The ID matcher** (`normalize/ids.py`): master table from nflverse plus
  Sleeper, team-code aliases across platforms, nickname normalization, DST
  naming, exact-then-fuzzy matching with every fuzzy hit logged. Reusable for
  any name-only source you add.
- **The scoring module** (`normalize/scoring.py`): 31 lines, takes a stats
  DataFrame, returns every variant. Add bonuses by editing the base formula.
- **Any single source module**: each exposes `fetch()` and `parse()` with a
  documented return shape in its docstring. The FFC boards scraper is the
  one you cannot get elsewhere for free.
- **The board template** (`board_template.html` + `scripts/build_board.py`):
  a working sortable table over the player rows, theme aware, no build step.

## 10. What to build next

`docs/next.md` lays this out in detail. Short version, in the order that
pays off fastest for a draft:

1. Survival model per pick: normal CDF on FFC ADP as the baseline, corrected by
   the empirical `picks` distribution in rounds 2 and 3.
2. Replacement level and VORP from your roster settings, using `pts_2025_*`
   adjusted by `fp_over_xfp_2025`, or rank-implied points from `ecr`.
3. Tier breaks: start with `tier_bc_*`, or run your own Gaussian mixture on
   `ecr` and `ecr_sd`.
4. Keeper removal from the pool and from survival denominators.

Open-source simulators and papers for each step are linked in
`docs/research-2026-08-26.md`.

## 11. Attribution

FFC ADP is free with attribution. DynastyProcess data is GPL-3. nflverse data
is community maintained. If any of this ends up in something public, credit
those three. Everything here is personal, non-commercial use.
