# Interview decisions

Recorded 2026-08-26 during the data-layer kickoff interview. Each entry is a ruling;
change it here first if it changes.

## Block A: league facts

| # | Question | Ruling |
|---|---|---|
| A1 | Draft date | Not a constraint. No deadline pressure on the build. |
| A2 | Teams / format | Snake, pick 1.01, keepers occupy round slots (Zay Flowers R4, Chase Brown R5). Team count not recorded because of A-pivot below. |
| A3 | Scoring | **League-agnostic pivot**: the data layer carries all variants (PPR / half / standard, passing TD at both 4 and 6) instead of baking in one league's scoring. |
| A4 | Starting roster | Reference defaults only, not baked in: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 K, 1 DEF/ST, 7 bench. |
| A5 | Other teams' keepers | Not collected; belongs to the league-specific layer. |

**The pivot (overrides the original prompt's league.json intent):** the data model is
independent of the specific league. This layer delivers clean, normalized, multi-format
data; the next layer applies league settings. `league.json` becomes a defaults snapshot
the next layer overrides, never a source of truth for scoring.

## Block B: sources

| Source | Ruling | Notes |
|---|---|---|
| nflverse (`nfl_data_py`) | **In** (baseline) | IDs, 2025 stats, bye weeks. Free, no key. |
| FFC ADP | **In** | Free API. PPR / half / standard, includes std-dev. |
| ESPN ADP | **In** | User wanted it "if possible without much fuss". Verified 2026-08-26: public `leaguedefaults` JSON endpoint works with no auth. Unofficial; may break. Point estimate only, no std-dev. |
| Sleeper | **In** | Status/injury flags, secondary ID crosswalk. Free. |
| Harris Football | **In** | Verified 2026-08-26: plain-text ranking lists per position, Standard + PPR, ~80 per position, no bot-block. No player IDs, so rows go through the fuzzy matcher with review CSV. |
| FantasyPros | **Out** | No HOF subscription; user chose to skip entirely (no CSV fallback either). |
| Fantasy Footballers | **Out** | Rankings are behind the paid UDK; user does not subscribe. |
| Underdog / Yahoo / paid | **Out** | Not requested; scraping recommended against. |

- **No baked-in primary ADP.** The layer carries `adp_espn_*` and `adp_ffc_*` (+ sd)
  side by side; the next layer picks. Survival modeling note: only FFC provides std-dev.
- **Sources are removable.** Every source is a module behind `sources.toml` with an
  `enabled` flag, plus `make refresh-<source>`. Disabling a source nulls its columns
  and nothing else breaks.
- v1 scope: **rank + ADP + prev-season stats**. No projections (would have required
  FantasyPros API access).

## Block C: stack and workflow

| # | Question | Ruling |
|---|---|---|
| C9 | Language | Python via uv (nfl_data_py, pandas). |
| C10 | Storage | Parquet artifact + DuckDB query layer; CSV mirrors for eyeballing. |
| C11 | Refresh cadence | Manual `make refresh` (default, not explicitly discussed; no scheduler). |
| C12 | Where it lives | New folder `~/work/fantasy-draft-data`, git init, commit as we go, push as a new private GitHub repo per the personal repo standard (folder-to-repo skill applies naming and pre-commit secret scan). |
| C13 | Conventions | Defaults proposed and not objected to: ruff, pytest, no pre-commit hooks. |

## Amendment 1 ruling (2026-08-26)

Approved in full, **including the optional `ffc_boards` module** (empirical pick-log
capture from FFC completed mock boards, enabled). New sources in: DynastyProcess ECR,
Boris Chen tiers, Sleeper trending adds, rookie draft capital, ffopportunity xFP,
FFC high/low/times_drafted + snapshot metadata, extended ID crosswalk. Rejections in
`design.md` Amendment 1 stand.

## Standing constraints (from the kickoff prompt)

- Never touch raw credentials; env vars only; stop and name the var if missing.
- Never scrape ClickyDraft, or any bot-blocked site.
- Evidence after every build step: real command output, row counts, sample rows.
- Check before: paid API calls beyond a smoke test, rate-limit risks, deleting files,
  dependencies outside the agreed stack.
- No draft engine, survival model, or UI in this session.
