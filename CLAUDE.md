@AGENTS.md

# WARroom — Claude / agent briefing

## Team structure & working norms

**Project lead:** Rees (the user). Limited coding/development background — all decisions and outputs must be explained in plain English before and after execution. Never assume prior knowledge of a command, tool, or concept.

**Claude Code role:** Senior engineer / architect. Responsible for planning, reviewing, and explaining work. Must surface trade-offs and get explicit approval from Rees before implementing anything non-trivial.

**Cursor role:** Hands-on developer. Executes implementations as directed.

**How to work:**
- Break all changes into small, clearly scoped pieces. No large multi-part implementations without step-by-step sign-off.
- Before running any command or making any edit, explain in plain English what it does and why.
- After completing any action, report back in plain English what changed, what it means, and what comes next.
- Major decisions (architecture, schema changes, new features, pipeline changes) must be proposed to Rees first — do not implement without a green light.
- When in doubt, stop and ask rather than proceed.

---

**Next.js quirks:** **`AGENTS.md`** (embedded docs under `node_modules/next/dist/docs/`).

---

## Project identity

**WARroom** — MLB analytics platform (Statcast-heavy warehouse + leaderboards + player tooling). Stack: **Next.js 16** (App Router — **`package.json`**) · **React 19** · **Supabase Postgres** · **Python** `pipeline/` · **Tailwind CSS 4**.

---

## Repo layout (key paths only)

| Path | Contents |
|------|-----------|
| `src/app/` | App Router routes + `api/` route handlers |
| `src/components/` | UI |
| `src/lib/` | Supabase client helpers, MLB fetch, formulas |
| `pipeline/` | ETL runners, seeds, calculators (see **`HANDOFF.md`** for detail) |
| `pipeline/calculations/` | Pure metric math (`batting_calcs.py`, `pitching_calcs.py`, …) |
| `supabase/migrations/` | Executable schema + RPC DDL (source of truth) |

Broad schema / RLS / column ownership: **`SCHEMA.md`**.

---

## Critical conventions

- **Upsert RPCs:** `COALESCE`/partial-merge semantics — **omitted payload keys preserve existing rows**; **never** overwrite with implicit `NULL` from missing keys on partial upserts. Details per RPC: **`SCHEMA.md`**.
- **PostgREST pagination:** `.range(offset, …)` batch size **`≤ 1000`** (Supabase default row cap). Never assume single-query full scans for large tables.
- **Brand color `#b8922a` (gold):** reserve **only** for WARroom proprietary metrics in UI — **CQI**, **Stuff+**, **bWPR**, **fWPR**, **brWPR**, **pWPR**, **WPR** (not general chrome unless product owner says otherwise).
- **Script roles:** **`seed_*`** → counting/stat lines only · **`calc_*`** → derived rates + **WPR** / **CQI** / **Stuff+** — do not blur.
- **`player_id`:** **MLBAM** integer everywhere — no other player id scheme.
- **bWPR positional adjustment:** innings-weighted from **`player_fielding_seasons`**, **`inn ≥ 20`** per defensive line; otherwise fall back to **`players.position`** (DH / bench cases).
- **Views never get RLS** — only base tables do. Views inherit security from their underlying tables' RLS policies. Supabase will flag views as "unrestricted" — this is a dashboard artifact, not a security hole. Views need `GRANT SELECT TO anon, authenticated` (already applied to all WPR views).
- **PostgREST + window functions in views:** `CASE WHEN ... THEN RANK() OVER (...)` inside a view causes PostgREST to return empty results silently via the anon key. Never put conditional window functions in views. Compute rankings in the API handler instead (see `teams/[id]/position-wpr/route.ts` as the canonical pattern).
- **`team_id` type coercion:** Supabase can return `team_id` as a string. Always use `Number(rowTeamId) === targetTeamId` (never strict `===`) when matching team IDs from query results.

---

## Environment variables

| File | Vars | Purpose |
|------|------|---------|
| **`.env.local`** (repo root) | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_MLB_API_BASE` | Next.js builds + browser-safe reads (RLS on) |
| **`pipeline/.env`** | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Python ETL — **service role bypasses RLS**; never expose to client |

Never commit secrets.

---

## Pipeline daily refresh sequence (full — matches `.github/workflows/daily_refresh.yml`)

Individual CLIs expose `--season`, `--start-season`, `--end-season` flags; read each `main()`.

1. **`seed_game_logs.py`**
2. **`backfill_statcast.py`** (`continue-on-error: true`; skippable via `skip_statcast` input)
3. **`aggregate_statcast_batting.py`**, **`aggregate_statcast_pitching.py`**
4. **`calc_batting_metrics.py`**, **`calc_pitching_metrics.py`**
5. **`seed_player_batting_seasons.py`**, **`seed_player_pitching_seasons.py`**, **`seed_player_fielding_seasons.py`** (`continue-on-error: true`)
6. **`seed_statcast_oaa.py`** (`continue-on-error: true`)
7. **`calc_batting_season_metrics.py`**, **`calc_pitching_season_metrics.py`**
8. **`calc_fielding_season_metrics.py`** — **fWPR** (`continue-on-error: true`)
9. **`seed_statcast_running.py`**, **`seed_statcast_baserunning_rv.py`** (`continue-on-error: true`)
10. **`calc_baserunning_season_metrics.py`** — **brWPR**
11. **`calc_wpr_season_metrics.py`** — **Total WPR** (`wpr = bwpr + fwpr + brwpr`)
12. **Weekly (Mondays or `workflow_dispatch`):** **`calc_league_averages.py`**, **`calc_league_pitch_type_averages.py`**

**Not yet in GA (run manually):** **`seed_statcast_catcher_poptime.py`**, **`calc_park_factors.py`**.

---

## Key Supabase RPCs (full list)

| RPC | Purpose |
|-----|---------|
| `upsert_statcast_batting_aggregates` | Merge BBE/count aggregates into **`statcast_batting`**; partial upsert — leaderboard-only columns preserved when omitted. |
| `upsert_statcast_pitching_aggregates` | Upsert **`statcast_pitching`** pitcher-season rollup. |
| `upsert_statcast_pitching_arsenal` | Upsert **`statcast_pitching_arsenal`** per pitch type / hand. |
| `upsert_player_batting_seasons` | Partial upsert **`player_batting_seasons`** (**`bwpr`**, **`fwpr`**, **`brwpr`**, **`wpr`**, rates, counting stats — no null-clobber). |
| `upsert_player_pitching_seasons` | Partial upsert **`player_pitching_seasons`** (**`pwpr`**, etc.). |
| `get_batter_statcast_percentiles` | Percentile JSON for batter Statcast UI / API. |
| `get_pitcher_statcast_percentiles` | Percentile JSON for pitcher Statcast UI / API. |

All take standard PostgREST `rpc()` JSON args as in **`SCHEMA.md`** / migrations.

---

## Key Supabase views (read-only, anon-accessible)

| View | Source tables | Purpose |
|------|--------------|---------|
| `player_season_wpr_totals` | `player_batting_seasons` FULL OUTER JOIN `player_pitching_seasons` | Unified Total WPR for all player types: `total_wpr = ROUND(COALESCE(wpr,0) + COALESCE(pwpr,0), 1)`. Covers position players, pitchers, and two-way players (Ohtani). |
| `team_position_wpr_season` | `player_batting_seasons`, `player_fielding_seasons`, `player_pitching_seasons`, `players`, `teams` | Innings-weighted team WPR per defensive position per season. Returns `team_id, season, position, bwpr, fwpr, brwpr, wpr, pwpr, player_count`. Excludes P/DH/PH/PR from position-player slots. |
| `team_position_wpr_players_season` | Same as above, unnested | Per-player contribution breakdown within each team/position. Returns `team_id, season, position, player_id, player_name, inn, inn_share, bwpr_attr, fwpr_attr, brwpr_attr, wpr_attr, pwpr_attr`. |

All views have `GRANT SELECT TO anon, authenticated`.

---

## Key API routes

| Route | File | Notes |
|-------|------|-------|
| `GET /api/teams/[id]/position-wpr?season=YYYY` | `src/app/api/teams/[id]/position-wpr/route.ts` | Fetches all 30 teams from `team_position_wpr_season`, computes per-position MLB-wide ranks in TypeScript (`rankDesc()`), returns target team's rows with rank fields. |
| `GET /api/teams/[id]/position-wpr/players?season=YYYY` | `src/app/api/teams/[id]/position-wpr/players/route.ts` | Per-player breakdown from `team_position_wpr_players_season`. |
| `GET /api/status` | `src/app/api/status/route.ts` | RAG (green/amber/red) health checks for all pipeline outputs. |

---

## Metric formulas (one paragraph each)

**CQI** — **100 ≈ league average** contact-quality index. Builds three ratios versus league **`lgAvgEV`**, **`lgBarrelRate`**, **`lgHardHitRate`** (checked-in / fetched league bundle), weighted **35% EV / 50% barrels / 15% hard-hit**, scaled to **`100 × (0.35 r_EV + 0.5 r_barrel + 0.15 r_HH)`**; gated to Statcast-modern seasons (**`STATCAST_MIN_SEASON`** ≥ **2015**).

**Stuff+** — **100 ≈ league average** for each pitch type vs **`league_pitch_type_averages`** (hand-split). Velocity and spin scale as simple ratios vs league means; horizontal / vertical movement use **`abs(pitch)/abs(league)`** so break direction/hand cancel. Combined as **`100 × (0.4 r_velo + 0.3 r_spin + 0.15 r_hmov + 0.15 r_vmov)`**.

**bWPR** — Offensive WPR hybrid: **`RPW = 9 × (lgR/lgIP) × 1.5 + 3`**; **batting runs** = `(wOBA − lgwOBA) / wOBA_scale × PA / park_factor`; **replacement runs** = `(570 × mlbGames/2430) × (RPW/lgPA) × PA`; **positional runs** = `adj_162 × games/162` where **`adj_162`** is innings-weighted Baseball-Reference-style positional runs-per-162 from **`player_fielding_seasons`** (**≥20** innings per line), else **`players.position`** (DH / bench cases). **WPR** = `(batting_runs + positional_runs + replacement_runs) / RPW` (rounded).

**fWPR** — Fielding wins: **fielding runs ÷ RPW** (same RPW convention), written onto **`player_batting_seasons`**. **2016+** with **`statcast_fielding_oaa`**: sum **`fielding_runs_prevented`**; else RF/9 z-score vs **`player_fielding_seasons`** position-season leagues — add **`z × (inn/9) × 0.1`** per defensive stint.

**brWPR** — Baserunning wins: three-tier model in **`calc_baserunning_season_metrics.py`**. **Tier 1 (2016+):** Statcast `statcast_baserunning_rv.running_runs` ÷ RPW. **Tier 2 (2015):** wSB runs + sprint-speed proxy from `statcast_running` ÷ RPW. **Tier 3 (pre-2015 / fallback):** wSB component only (stolen base run values vs league). Stored as **`brwpr`** on `player_batting_seasons`.

**Total WPR (`wpr`)** — Position-player WPR total: `wpr = bwpr + fwpr + brwpr`, computed in **`calc_wpr_season_metrics.py`** and stored as `wpr` on `player_batting_seasons`. The `player_season_wpr_totals` view combines this with `pwpr` for a unified cross-player leaderboard: `total_wpr = ROUND(COALESCE(wpr, 0) + COALESCE(pwpr, 0), 1)`.

**pWPR** — Pitching WPR on FIP-vs-league: **`(lgFIP − FIP)/9 × IP / park`** for runs above avg; Fangraphs-style **replacement** with marginal constant **1000**, schedule-scaled **`mlbGames`**, and **`BF_proxy`**; divide by **same RPW**. **`pwpr` ≈ `(RAA_FIP + replacement_runs) / RPW`** (rounded).

---

## Validation targets (`season ≈ 2026`)

Sanity-check after pipelines (**MLBAM** ids only):

| Player | Id | Metrics | Rough expectation (warehouse snapshot drift OK) |
|--------|-----|---------|------------------------------------------------|
| Aaron Judge | `592450` | bWPR, fWPR, brWPR, CQI | Elite bat: **bWPR** roughly **low-mid-single digits early season** (e.g. ~2.1); **fWPR** small (≈ −0.x to +0.x OF noise); **CQI** can sit **far above 100** (e.g. ~190–210 ingest-dependent). |
| Paul Skenes | `694973` | pWPR, Stuff+ | **pwpr** builds with IP (e.g. ~2+ plausible full ace year; partial season ~1–3); **`statcast_pitching.stuff_plus`** commonly ≈105–120+ (~114 plausible). |

---

## Deferred / backlog

- **Vercel deployment** — production deploy / env wiring not finalized
- **Auth on `/status` page** — currently public; add access control before platform publishes
- **Total WPR frontend leaderboard** — `player_season_wpr_totals` view is live; frontend display TBD
- **`seed_statcast_catcher_poptime.py`** — not in GitHub Actions yet; run manually
- **`calc_park_factors.py`** — not in GitHub Actions; run on schedule cadence
- **CQI calibration** — league averages must stay in sync with Savant; under ongoing validation
- **Two-way player handling** — Ohtani-class players need richer UX (separate batting/pitching panels)
- **Social posting pipeline** — not implemented
- **Statcast explorer column drift** — client column naming vs SCHEMA drift; reconcile before exposing new Savant fields

---

## What NOT to do

- Never depend on **FanGraphs** bulk scrape/API (**403**/fragile).
- Never use **Lahman** paths called **broken** in this codebase.
- Never run **`backfill_statcast_historical.py`** unless **explicitly instructed** — rewinds years of **`statcast_pitches`** footprint.
- Never move **derived metrics** (**bWPR**, **fWPR**, **brWPR**, **pWPR**, **CQI**, **Stuff+**, OPS+, …) into **`seed_*`** — **`calc_*`** only.
- Never put conditional window functions (`CASE WHEN ... THEN RANK() OVER (...)`) inside a Supabase view — PostgREST returns empty results silently.
- Never commit `pipeline/.env` or any file containing the service role key.
