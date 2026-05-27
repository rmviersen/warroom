@AGENTS.md

# WARroom — Claude / agent briefing

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
- **Brand color `#b8922a` (gold):** reserve **only** for WARroom proprietary metrics in UI — **CQI**, **Stuff+**, **bWPR**, **fWPR**, **pWPR**, **WPR** (not general chrome unless product owner says otherwise).
- **Script roles:** **`seed_*`** → counting/stat lines only · **`calc_*`** → derived rates + **WPR** / **CQI** / **Stuff+** — do not blur.
- **`player_id`:** **MLBAM** integer everywhere — no other player id scheme.
- **bWPR positional adjustment:** innings-weighted from **`player_fielding_seasons`**, **`inn ≥ 20`** per defensive line; otherwise fall back to **`players.position`** (DH / bench cases).

---

## Environment variables

| File | Vars | Purpose |
|------|------|---------|
| **`.env.local`** (repo root) | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_MLB_API_BASE` | Next.js builds + browser-safe reads (RLS on) |
| **`pipeline/.env`** | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Python ETL — **service role bypasses RLS**; never expose to client |

Never commit secrets.

---

## Pipeline daily refresh sequence (steps 1–7)

Assume `SEASON`/flags per script CLI. Matches **`.github/workflows/daily_refresh.yml`** automation (step 7 is weekly there unless dispatched).

1. **`seed_game_logs.py`**
2. **`backfill_statcast.py`**
3. **`aggregate_statcast_batting.py`**, **`aggregate_statcast_pitching.py`**
4. **`calc_batting_metrics.py`**, **`calc_pitching_metrics.py`**
5. **`seed_player_batting_seasons.py`**, **`seed_player_pitching_seasons.py`**
6. **`calc_batting_season_metrics.py`**, **`calc_pitching_season_metrics.py`**
7. **`calc_league_averages.py`** — in GA: **Mondays** (`date -u +%u` = `1`, UTC) **or** `workflow_dispatch`

**Also** run **`seed_player_fielding_seasons.py`** when box/fielding counting lines change. For **fWPR**: **`seed_statcast_oaa.py`**, **`calc_fielding_season_metrics.py`**; catcher: **`seed_statcast_catcher_poptime.py`**. Stuff+ denominators: **`calc_league_pitch_type_averages.py`** (periodic). See **`HANDOFF.md`**.

---

## Key Supabase RPCs (full list)

| RPC | Purpose |
|-----|---------|
| `upsert_statcast_batting_aggregates` | Merge BBE/count aggregates into **`statcast_batting`**; partial upsert — leaderboard-only columns preserved when omitted. |
| `upsert_statcast_pitching_aggregates` | Upsert **`statcast_pitching`** pitcher-season rollup. |
| `upsert_statcast_pitching_arsenal` | Upsert **`statcast_pitching_arsenal`** per pitch type / hand. |
| `upsert_player_batting_seasons` | Partial upsert **`player_batting_seasons`** (**`bwpr`**, **`fwpr`**, rates, counting stats — no null-clobber). |
| `upsert_player_pitching_seasons` | Partial upsert **`player_pitching_seasons`** (**`pwpr`**, etc.). |
| `get_batter_statcast_percentiles` | Percentile JSON for batter Statcast UI / API. |
| `get_pitcher_statcast_percentiles` | Percentile JSON for pitcher Statcast UI / API. |

All take standard PostgREST `rpc()` JSON args as in **`SCHEMA.md`** / migrations.

---

## Metric formulas (one paragraph each)

**CQI** — **100 ≈ league average** contact-quality index. Builds three ratios versus league **`lgAvgEV`**, **`lgBarrelRate`**, **`lgHardHitRate`** (checked-in / fetched league bundle), weighted **35% EV / 50% barrels / 15% hard-hit**, scaled to **`100 × (0.35 r_EV + 0.5 r_barrel + 0.15 r_HH)`**; gated to Statcast-modern seasons (**`STATCAST_MIN_SEASON`** ≥ **2015**).

**Stuff+** — **100 ≈ league average** for each pitch type vs **`league_pitch_type_averages`** (hand-split). Velocity and spin scale as simple ratios vs league means; horizontal / vertical movement use **`abs(pitch)/abs(league)`** so break direction/hand cancel. Combined as **`100 × (0.4 r_velo + 0.3 r_spin + 0.15 r_hmov + 0.15 r_vmov)`**.

**bWPR** — Offensive WPR hybrid: **`RPW = 9 × (lgR/lgIP) × 1.5 + 3`**; **batting runs** = `(wOBA − lgwOBA) / wOBA_scale × PA / park_factor`; **replacement runs** = `(570 × mlbGames/2430) × (RPW/lgPA) × PA`; **positional runs** = `adj_162 × games/162` where **`adj_162`** is innings-weighted Baseball-Reference-style positional runs-per-162 from **`player_fielding_seasons`** (**≥20** innings per line), else **`players.position`**. **WPR** = `(batting_runs + positional_runs + replacement_runs) / RPW` (rounded).

**fWPR** — Fielding wins: **fielding runs ÷ RPW** (same RPW convention), written onto **`player_batting_seasons`**. **2016+** with **`statcast_fielding_oaa`**: sum **`fielding_runs_prevented`**; else RF/9 z-score vs **`player_fielding_seasons`** position-season leagues — add **`z × (inn/9) × 0.1`** per defensive stint.

**pWPR** — Pitching WPR on FIP-vs-league: **`(lgFIP − FIP)/9 × IP / park`** for runs above avg; Fangraphs-style **replacement** with marginal constant **1000**, schedule-scaled **`mlbGames`**, and **`BF_proxy`**; divide by **same RPW**. **`pwpr` ≈ `(RAA_FIP + replacement_runs) / RPW`** (rounded).

---

## Validation targets (`season ≈ 2026`)

Sanity-check after pipelines (**MLBAM** ids only):

| Player | Id | Metrics | Rough expectation (warehouse snapshot drift OK) |
|--------|-----|---------|------------------------------------------------|
| Aaron Judge | `592450` | bWPR, fWPR, CQI | Elite bat: **bWPR** roughly **low-mid-single digits early season** (e.g. warehouse once showed **~2.1**); **fWPR** small (**≈ −0.x to +0.x OF noise**); **CQI** can sit **far above 100** when ratios spike (e.g. **~190–210** ingest-dependent). |
| Paul Skenes | `694973` | pWPR, Stuff+ | Elites: **pwpr** builds with IP (e.g. **~2+** plausible full ace year; partial season often **~1–3** range); **`statcast_pitching.stuff_plus`** commonly **≈105–120+** (**100** = average; snapshot **~114** plausible). |

---

## Deferred / backlog

**brWPR**, **Total WPR** (`wpr` column) rollup, production **Vercel** rollout, automated **social** posting, **CQI calibration**. GitHub Actions does **not** yet run **`seed_statcast_oaa.py`**, **`calc_fielding_season_metrics.py`**, **`seed_statcast_catcher_poptime.py`**, **`calc_league_pitch_type_averages.py`** — run those manually until CI matches **`HANDOFF.md`**. **Next-session task:** wire these scripts into **`.github/workflows/daily_refresh.yml`** (ordering per **`HANDOFF.md`** §4.4 vs step 7 / weekly jobs).

---

## What NOT to do

- Never depend on **FanGraphs** bulk scrape/API (**403**/fragile).
- Never use **Lahman** paths called **broken** in this codebase.
- Never run **`backfill_statcast_historical.py`** unless **explicitly instructed** — rewinds years of **`statcast_pitches`** footprint.
- Never move **derived metrics** (**bWPR**, **fWPR**, **pWPR**, **CQI**, **Stuff+**, OPS+, …) into **`seed_*`** — **`calc_*`** only.
