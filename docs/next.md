# Hand-off: what the draft engine layer gets, and what it still needs

Written 2026-08-26 at the end of the data-layer build. The draft engine / league
layer is the next session's work; this file is its starting brief.

## What this layer guarantees

- `data/processed/players.parquet`: 1,026 players, one row each, canonical
  `player_id` (nflverse gsis; `DST_<team>` for defenses). 483 players fully
  populated on identity + bye + ADP + ECR (target was 300). `make validate` is
  ALL PASS as of the hand-off commit.
- `data/processed/draft_picks.parquet`: 44,892 real picks from 290 completed FFC
  12-team mock drafts (~100 boards per format), player-ID-matched at 100%.
- Every scoring variant carried: FFC ADP per format (with sd/high/low/n), 2025
  points for {ppr, half, std} x {pass TD 4, 6}, Boris Chen tier per format,
  Harris ranks (std + ppr), ESPN ADP + ranks, ECR (PPR cheatsheet) with sd.
- ID matching: 100% on every name-matched source; the 7 judgment calls are in
  `id_match_review.csv` and worth one human pass.

## What the engine should build on top

1. **Survival model for picks 24/25.** Two inputs are ready: parametric
   (`adp_ffc_*` mean + sd, with high/low bounding the tails) and empirical
   (`draft_picks.parquet` pick distributions). Research pointers in
   `docs/research-2026-08-26.md` section 1: normal-CDF baseline, then empirical
   correction in the round 2-3 zone where normality is worst.
2. **Replacement level / VORP.** Needs league settings (roster from
   `league.json` defaults) + a points basis: use `pts_2025_*` actuals adjusted by
   `fp_over_xfp_2025` (regression candidates), or rank-implied points from ECR.
3. **Tier logic.** `tier_bc_*` is a battle-tested label to start; `ecr` + `ecr_sd`
   are the inputs to run our own Gaussian mixture when we want custom tiers.
4. **Keeper handling.** `league.json` lists the keepers (Zay Flowers R4, Chase
   Brown R5, pick 1.01 snake). The engine must remove all keepers (mine AND other
   teams', once known) from the available pool and from survival denominators.

## Known gaps and quirks the engine must respect

- **FFC depth is ~237 players per format** (that's the site's real depth, not a
  bug). Deeper than that, use `adp_espn` (1,027 players) or ECR (518).
- **ECR is PPR-format** (FantasyPros PPR cheatsheet via DynastyProcess). There is
  no free per-format ECR; per-format signal comes from FFC ADP + Boris Chen tiers.
- **ESPN ADP is a point estimate** (no sd) from an unofficial endpoint that can
  break any week. Treat as secondary.
- **`adp_espn` early-window bias:** ESPN ADP runs "later" than FFC on the same
  players (different drafter population); do not mix the two in one distribution.
- **DSTs**: team-level rows only, no per-player stats by design. Kickers have
  stats but no Harris ranks (he doesn't rank K).
- **Keeper-distorted league ADP**: public ADP does not know this league's keepers;
  survival estimates for kept players are meaningless (they are never available).
- **Staleness**: `meta.json` has FFC's draft-sample window; `fetched_at_*` columns
  stamp every source. Re-run `make refresh --force` the morning of the draft.
- 2026 rookies have null 2025 stat columns (expected); `draft_round`/`draft_pick`
  carry their draft capital instead.

## Deviations from the approved design (documented, all upside)

- `nfl_data_py` -> `nflreadpy` (upstream deprecated the former in 2025; same
  nflverse data, maintained successor, also serves ECR/xFP/draft-capital loads).
- Added columns beyond the amendment: `wopr`, `rz_carries`, `rz_targets`,
  `draft_year/round/pick`, `rank_espn_std/ppr`, per-format FFC high/low/n.
- `league.json` gained nothing league-specific beyond the recorded defaults; the
  pivot to league-agnostic held.
