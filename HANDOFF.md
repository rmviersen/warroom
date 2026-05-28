# WARroom — Developer handoff

This document orients maintainers on **WARroom**: a Next.js app on **Supabase** (Postgres + RLS + RPCs), with a **Python** ETL that ingests Statcast pitch data and maintains derived warehouse metrics (`player_*_seasons`, leaderboards, WPR-family stats).

Canonical DDL, RPC contracts, and partial-upsert semantics: **`SCHEMA.md`**. Repo agent rules: **`AGENTS.md`**.

**Database snapshot:** row counts below were queried live against the project Supabase (PostgREST) on **2026-05-25**. Re-run counts before publishing; `statcast_pitches` is large — use `select("id", count="exact", head=True)` (a bare `*` head count can 500).

---

## 1. Full stack overview

| Layer | Role |
|-------|------|
| **Web** (`src/`) | App Router UI: players, teams, Statcast explorer, leaderboards |
| **API** (`src/app/api/`) | Route handlers: Supabase reads + MLB Stats API |
| **Supabase** | Postgres: pitches, Statcast leaderboards, season warehouses, game logs, park factors, league tables |
| **Pipeline** (`pipeline/`) | Python 3: pybaseball/pandas, service-role Supabase client, optional **APScheduler** poller |

| Area | Stack (current `package.json`) |
|------|--------------------------------|
| Frontend | **Next.js 16** (App Router), **React 19**, TypeScript — same product shape older docs summarized as “Next + Supabase + Python + Tailwind” |
| Styling | **Tailwind CSS 4** (`@tailwindcss/postcss`), `globals.css` |
| Charts | Recharts (where used) |
| DB client (browser) | `@supabase/supabase-js` (+ `@supabase/ssr` as needed) |
| Pipeline | `supabase-py`, `pandas`, `pybaseball`, `APScheduler` |

---

## 2. Database snapshot — row counts & season coverage

**No season axis:** `players`, `teams` — current warehouse roster / franchise table snapshots (not year-scoped).

| Table | Rows | Season / date coverage |
|-------|------|-------------------------|
| `players` | 8,873 | — |
| `teams` | 30 | — |
| `game_logs` | 84,056 | **1990-04-09 → 2026-05-24** (`game_date`; calendar years **1990–2026** in DB) |
| `park_factors` | 1,088 | **1990–2026** |
| `statcast_pitches` | **7,692,407** | **2015-04-05 → 2026-05-24** (`game_date`) |
| `statcast_batting` | 10,825 | **2015–2026** |
| `statcast_pitching` | 9,942 | **2015–2026** |
| `statcast_pitching_arsenal` | 42,026 | **2015–2026** |
| `league_pitch_type_averages` | 333 | **2015–2026** |
| `league_batting_averages` | 37 | **1990–2026** |
| `league_pitching_averages` | 37 | **1990–2026** |
| `player_batting_seasons` | 38,452 | **1990–2026** |
| `player_pitching_seasons` | 24,345 | **1990–2026** |
| `player_fielding_seasons` | 80,019 | **1990–2026** |
| `statcast_fielding_oaa` | 5,914 | **2016–2026** |
| `statcast_catcher_defense` | 852 | **2016–2026** |
| `player_position_seasons` | 582 | **2024 only** (partial seed — expand when multi-year splits matter) |

**Views:** `statcast_pitch_season_averages` aggregates pitch-level columns by calendar year extracted from `statcast_pitches.game_date` (see **`SCHEMA.md`**).

---

## 3. WARroom proprietary metrics (formulas)

**Naming:** Warehouse columns **`bwpr`**, **`pwpr`**, **`fwpr`**, placeholder **`brwpr`**, and total **`wpr`** (see migrations `20260522150000_*`). Code and newer docs say **WPR**; FanGraphs/BR-style guts inside the formulas below.

### 3.1 CQI — Contact Quality Index (`calc_cqi` in `pipeline/calculations/batting_calcs.py`)

- **Defined only when** `season >= STATCAST_MIN_SEASON` (**2015**, `pipeline/calculations/constants.py`) and league baselines exist in `get_league_averages(season)` (`lgAvgEV`, `lgBarrelRate`, `lgHardHitRate` — aligned with **`league_averages.json`** / Savant units).
- **Formula:** \( \text{CQI} = 100 \times (0.35\,r_{EV} + 0.5\,r_{barrel} + 0.15\,r_{HH}) \) where each \(r\) is the player rate ÷ league rate.
- **Calibration note:** League JSON / DB league rows must stay in sync with Savant exports; treat CQI as **under ongoing validation** (see §10).

### 3.2 Stuff+ (`calc_stuff_plus` in `pipeline/calculations/pitching_calcs.py`)

Per pitch type, **100 = league average** for that type (handedness-split league row from `league_pitch_type_averages`):

- Ratios: `velo/lg_velo`, `spin/lg_spin`, horizontal movement `abs(pitcher)/abs(league)`, vertical movement `abs(pitcher)/abs(league)`.
- **Weights:** velocity **40%**, spin **30%**, horizontal break **15%**, vertical break **15%**.
- **Formula:** `100 × (0.4×r_v + 0.3×r_s + 0.15×r_h + 0.15×r_z)`.

Season rollup (`stuff_plus` on `statcast_pitching` / arsenal rows) is produced in **`calc_pitching_season_metrics.py`** together with **`pwpr`**.

### 3.3 bWPR — batting (`calc_batting_war` in `pipeline/calculations/batting_calcs.py`)

Position-player **offensive** wins (hybrid; FanGraphs-style RPW/replacement):

- **Batting runs (park-adjusted):** `(wOBA − lgwOBA) / wOBA_scale × PA / park_factor` with FanGraphs guts `wOBA_scale` (`get_woba_scale(season)`).
- **Runs per win:** `RPW = 9 × (lgR / lgIP) × 1.5 + 3` using league pitching innings.
- **Replacement runs:** `(570 × (mlb_games/2430)) × (RPW / lg_pa) × PA`. `mlb_games` from **`get_mlb_games_played`** (2020 → 900, pre-2022 → 2430, else **`game_logs`** tally) — same helper family as season metric scripts.
- **Positional adjustment (Baseball-Reference-style runs per 162 games):** `adj_162 × (G/162)`.
  - **`adj_162`** is **innings-weighted** across defensive splits from **`player_fielding_seasons`**: only positions with **`inn ≥ 20`** count; weights are innings shares × BR-style **`_BATTING_POSITION_ADJ_PER_162`** lookup.
  - If **no** position clears the 20-inning bar, **`players.position`** supplies the fallback key (covers **DH** and pure bat-only rows without fielding splits in the warehouse).

**Orchestration:** **`calc_batting_season_metrics.py`** loads fielding splits via `load_fielding_splits`, hydrates positions from **`players`**, writes **`bwpr`** (and rates) via `upsert_player_batting_seasons`.

### 3.4 pWPR — pitching (`calc_pitching_war` in `pipeline/calculations/pitching_calcs.py`)

Simplified FanGraphs-style pitching value on a **FIP** basis vs league (see docstring):

- Runs above league average: `(lgFIP − FIP) / 9 × IP / park_factor`.
- `RPW` as in batting (**9 × (lgR/lgIP) × 1.5 + 3**).
- Replacement side uses constant **1000** (marginal pitchers): `(1000 × (mlb_games/2430)) × (RPW/lg_pa) × BF_proxy` with `BF_proxy = (lg_pa/lg_IP) × IP`.
- **`WAR_pitch = (RAA_FIP + replacement_runs) / RPW`** (stored as **`pwpr`** rounded to 1 decimal).

**Orchestration:** **`calc_pitching_season_metrics.py`** (uses **`league_pitching_averages`**, **`park_factors`**, FIP constants).

### 3.5 fWPR — fielding (`pipeline/calc_fielding_season_metrics.py`)

Writes **`fwpr`** onto **`player_batting_seasons`** (partial upsert) using the same **`RPW`** definition as **`calc_batting_war`** / **`calc_pitching_war`**.

- **`season ≥ 2016`** and Statcast **`statcast_fielding_oaa`** has **any** row for that **`player_id`**: sum **`fielding_runs_prevented`** → **`fwpr = round(fruns / RPW, 1)`**.
- **Otherwise:** **RF/9 z-score fallback** vs position-season leagues built from **`player_fielding_seasons`**: per appearance `z × (inn/9) × 0.1`, summed (see `fielding_runs_via_rf9_fallback`).

Runs only when **`league_batting_averages`** and **`lg_ip`** resolve for that season.

### 3.6 WPR component status

| Component | Code / column | Status |
|-----------|----------------|--------|
| **bWPR** | `bwpr`, `calc_batting_season_metrics` | **Shipped** |
| **fWPR** | `fwpr`, `calc_fielding_season_metrics` | **Shipped** |
| **pWPR** | `pwpr`, `calc_pitching_season_metrics` | **Shipped** |
| **brWPR** | `brwpr`, `calc_baserunning_season_metrics` | **Shipped** |
| **Total WPR** | `wpr`, `calc_wpr_season_metrics` | **Shipped** — `bwpr + fwpr + brwpr`; 38,457 rows 1990–2026 |

---

## 4. Pipeline architecture

### 4.1 Two structural refactors (how the warehouse stays safe)

1. **Partial-upsert RPCs** — SECURITY DEFINER upserts (`upsert_statcast_*`, `upsert_player_*_seasons`) **merge** rows so **omitted JSON keys keep prior DB values** (`COALESCE(EXCLUDED.col, existing.col)` pattern). Scripts can PATCH **`fwpr`** or **`bwpr`** without sending full historical counting stat payloads. Migration family **`202605221*`** in `supabase/migrations/`.
2. **Split offensive vs defensive batting value** — **`calc_batting_season_metrics.py`** owns **`bwpr`** (+ rate stats); **`calc_fielding_season_metrics.py`** owns **`fwpr`**. Both target the **same** `player_batting_seasons` conflict key `(player_id, season, team_id)` without clobbering each other’s columns.

### 4.2 Script inventory (`pipeline/`)

| Script | Role |
|--------|------|
| `config.py`, `db.py` | Env + Supabase service client |
| `statcast_pipeline.py` | Normalize Savant CSV → batched **`statcast_pitches`** upsert |
| `scheduler.py` | APScheduler cron (Eastern game window) calling `run_pipeline` |
| `aggregate_statcast_batting.py` | Pitch table → **`upsert_statcast_batting_aggregates`** (BBE aggregates) |
| `aggregate_statcast_pitching.py` | Pitch table → **`statcast_pitching`** + **`statcast_pitching_arsenal`** RPCs |
| `seed_statcast_batting.py` | Savant leaderboard fields for **`statcast_batting`** (xSTATS, sprint, metadata) |
| `calc_batting_metrics.py` | Row patches (e.g. **CQI** on batting lines tied to Statcast) |
| `calc_pitching_metrics.py` | Row patches for **`statcast_pitching`** / partial-upsert arsenals |
| `calc_league_averages.py` | Fills **`league_batting_averages`** / **`league_pitching_averages`** |
| `calc_league_pitch_type_averages.py` | **`league_pitch_type_averages`** (Stuff+ denominators); **not** in GitHub Actions yet |
| `calc_park_factors.py` | **`park_factors`** (run-environment); typically batch / on-demand |
| `calc_batting_season_metrics.py` | **`player_batting_seasons`** derivatives + **`bwpr`** |
| `calc_pitching_season_metrics.py` | **`player_pitching_seasons`** derivatives + **`pwpr`** + Stuff+ rollup |
| `calc_fielding_season_metrics.py` | **`fwpr`** from OAA (**2016+**) or RF/9 fallback (see §3.5) |
| `seed_statcast_running.py` | Savant sprint speed leaderboard → **`statcast_running`** (2015+) |
| `seed_statcast_baserunning_rv.py` | Savant baserunning run-value leaderboard → **`statcast_baserunning_rv`** (2016+) |
| `calc_baserunning_season_metrics.py` | **`brwpr`** — three-tier: Statcast RV (2016+), sprint+wSB (2015), wSB fallback |
| `calc_wpr_season_metrics.py` | **`wpr`** = `bwpr + fwpr + brwpr` (position-player total WPR) |
| `seed_statcast_oaa.py` | Loads **`statcast_fielding_oaa`** from Savant/defensive exports |
| `seed_statcast_catcher_poptime.py` | Loads **`statcast_catcher_defense`** |
| `seed_players.py`, `seed_teams.py`, `seed_missing_players.py`, `fix_missing_players.py` | Identity hygiene |
| `seed_historical_players.py` | Bulk historical bios → **`players`** |
| `seed_game_logs.py`, `enrich_game_logs.py` | **`game_logs`** box scores |
| `seed_player_batting_seasons.py`, `seed_player_pitching_seasons.py`, `seed_player_fielding_seasons.py` | Warehouse counting lines |
| `seed_player_position_seasons.py` | **`player_position_seasons`** (currently narrow year coverage — see §2) |
| `seed_team_batting_seasons.py`, `seed_team_pitching_seasons.py`, `seed_team_fielding_seasons.py` | Team warehouse lines |
| `backfill_statcast.py`, `backfill_statcast_historical.py`, `rerun_dates.py` | Date-range replay / bulk catch-up |
| `explore_fielding_data.py`, `test_stat_splits.py` | Diagnostics / probes |

### 4.3 `calculations/` modules

| Module | Role |
|--------|------|
| `constants.py` | `STATCAST_MIN_SEASON`, wOBA weights, FIP constant loader, park cache |
| `fetch_league_averages.py` | `league_averages.json` + DB league row helpers |
| `batting_calcs.py` | wOBA/OPS+/wRC+, **CQI**, **`calc_batting_war`**, positional weighting |
| `pitching_calcs.py` | FIP/ERA+/LOB%, **`calc_pitching_war`**, **`calc_stuff_plus`** |
| `fielding_calcs.py` | Basic FIELD% / RF rate helpers |
| `baserunning_calcs.py` | **`calc_wsb_runs`**, **`calc_sprint_runs`**, **`calc_baserunning_war`**; tier constants |

### 4.4 Recommended **daily refresh** order (deps)

**GitHub Actions** (`.github/workflows/daily_refresh.yml`) covers a **subset**. For a full warehouse day aligned with shipped metrics:

1. **`seed_game_logs.py`** (box score deltas)
2. **Statcast ingest:** `statcast_pipeline.py` (continuous poller **or** `backfill_statcast.py` — GA uses **`backfill_statcast.py`**)
3. **`aggregate_statcast_batting.py`** → **`aggregate_statcast_pitching.py`** (calendar season span)
4. **`calc_batting_metrics.py`** → **`calc_pitching_metrics.py`**
5. **`seed_player_batting_seasons.py`** → **`seed_player_pitching_seasons.py`** • **`seed_player_fielding_seasons.py`** as needed when box scores / pybaseball lines change (fielding **`fwpr`** depends on this)
6. **`calc_league_averages.py`** when league numerators refresh (GA: Mondays — see §6)
7. **`calc_pitching_season_metrics.py`** (**`pwpr`**, Stuff+)
8. **`calc_batting_season_metrics.py`** (**`bwpr`**)
9. **`seed_statcast_running.py`** → **`seed_statcast_baserunning_rv.py`** → **`calc_baserunning_season_metrics.py`** (**`brwpr`**) → **`calc_wpr_season_metrics.py`** (**`wpr`**)
10. **`seed_statcast_oaa.py`** → **`calc_fielding_season_metrics.py`** (**`fwpr`**); **`seed_statcast_catcher_poptime.py`** when refreshing catcher leaderboard inputs
11. **`calc_league_pitch_type_averages.py`** periodically (Stuff+ denominators — often weekly with aggregates)
12. **`calc_park_factors.py`** on schedule cadence tied to standings/park workload

Individual CLIs expose `--season`, `--start-season`, `--end-season`, etc.; read each `main()`.

---

## 5. Frontend state

### 5.1 Theme

| Token / area | Value |
|--------------|-------|
| Navbar background | **`#1e3a6b`** |
| Accent / underline / “WAR” wordmark gold | **`#c9a84c`** |
| Inactive nav text | **`#a8bdd8`** |
| `globals.css` body | **`#ffffff`** background, **`#0f2044`** text |

### 5.2 Pages (`src/app/**/page.tsx`)

| Route | Notes |
|-------|-------|
| `/` | Home |
| `/players`, `/players/[id]` | List + profile (season tables, Statcast percentile sections, recent pitches API) |
| `/teams`, `/teams/[id]` | Franchise browsing |
| `/statcast` | Explorer — realtime **`statcast_pitches`** subscription |
| `/leaderboards/batting`, `/leaderboards/pitching` | Leaderboard consumers |

### 5.3 Navbar

**`src/components/layout/Navbar.tsx`** — links: **Teams**, **Players**, **Leaderboards** (hover submenu: Batting, Pitching), **Statcast**. Brand styling: navy bar, gold **`WAR`**, white **`room`**.

### 5.4 API routes (representative)

`src/app/api/players/**/*.ts`, `statcast/**/*.ts`, `teams/**/*.ts`, **`leaderboards/batting`**, **`leaderboards/pitching`**, `standings`, `schedule`.

Types: **`src/types/index.ts`**.

---

## 6. GitHub Actions — Daily Data Refresh

**Workflow:** `.github/workflows/daily_refresh.yml`

| Setting | Value |
|---------|-------|
| **Schedule** | `cron: "0 8 * * *"` (**08:00 UTC daily**) |
| **`workflow_dispatch`** | Optional **`season`** input (default **`2026`**) |
| **`SEASON`** env | Dispatched input or **`2026`** |

**Step order:**

1. Install Python deps (`pipeline/requirements.txt`)
2. Write `pipeline/.env` from **`SUPABASE_URL`** / **`SUPABASE_SERVICE_ROLE_KEY`** secrets
3. **`seed_game_logs.py`**
4. **`backfill_statcast.py`** (skippable via `skip_statcast`; `continue-on-error: true`)
5. **`aggregate_statcast_batting.py`** (`$SEASON` only)
6. **`aggregate_statcast_pitching.py`** (`$SEASON` only)
7. **`calc_batting_metrics.py`**, **`calc_pitching_metrics.py`**
8. **`seed_player_batting_seasons.py`**, **`seed_player_pitching_seasons.py`** (continue-on-error)
9. **`calc_batting_season_metrics.py`**, **`calc_pitching_season_metrics.py`**

**Weekly league averages:** **`calc_league_averages.py`** runs only when **`date -u +%u` equals `1`** (Monday, UTC **or** on manual `workflow_dispatch`). That keeps **`league_batting_averages`** / **`league_pitching_averages`** refreshed without daily full recomputation load.

**Gaps vs §4.4:** No GA steps yet for **`seed_statcast_oaa`**, catcher seed, **`calc_fielding_season_metrics`**, **`calc_league_pitch_type_averages`**, or **`calc_park_factors`** — run those manually or extend the workflow when ready. **`seed_statcast_running`** and **`calc_baserunning_season_metrics`** are now wired into GA (after pitching season metrics).

---

## 7. Known issues & deferred work

| Item | Notes |
|------|--------|
| **CQI calibration** | Depends on **`league_averages.json`** / DB league Statcast denominators staying aligned with Savant; validate against known leaders |
| **brWPR not built** | Column exists as placeholder; needs baserunning model + warehouse inputs |
| **Total WPR (`wpr`) not built** | Waiting on **`brwpr`** + aggregation rule tying **`bwpr`**, **`pwpr`**, **`fwpr`**, **`brwpr`** |
| **Vercel** | Production deploy / env wiring **not finalized** |
| **Statcast explorer** | Client column naming vs SCHEMA drift — reconcile before exposing new Savant fields |
| **Player profile** | Enhancements backlog (presentation, comps, pitching/batting two-way UX) |
| **Two-way players** | Dedicated handling still thin — beware single `players.position` vs multi-role Statcast splits |
| **Social posting pipeline** | Not implemented |

---

## 8. Immediate next steps (priority order)

1. **brWPR exploration** — identify baserunning inputs (Statcast runners / retrosheet-class events), prototype runs component, warehouse column strategy
2. **Total WPR (`wpr`) calculation** — spec once **`brwpr`** exists (`wpr = f(bwpr, fwpr?, pwpr?, brwpr?)` accounting for pitchers who hit separate rows)
3. **Vercel deployment** — `NEXT_PUBLIC_*`, build verification, ISR/SSR choices for leaderboard pages
4. **Player profile UI** — richer WPR breakout, percentile copy, pitcher/batter mode polish

---

## 9. Key architecture decisions & learnings

- **Identifiers:** MLBAM integers everywhere; **soft references** dominate (no FK to `players` on pitch rows) so ETL ordering stays forgiving.
- **Single writer discipline:** Respect **`SCHEMA.md`** splits (e.g. aggregates vs leaderboard columns on **`statcast_batting`**). Never patch “owned elsewhere” columns from the wrong script.
- **Partial upserts are load-bearing:** They let **`fwpr`** and **`bwpr`** land in separate passes and let Statcast loaders patch deltas without wiping pybaseball-sourced counters.
- **RPW parity:** **`calc_batting_war`**, **`calc_pitching_war`**, and **`calc_fielding_season_metrics`** intentionally share **`RPW = 9×(lgR/lgIP)×1.5+3`** semantics so batting/pitching/fielding WPR fractions stay comparable once totals exist.
- **Fielding fWPR (`fwpr`) duality:** Where Statcast exists (**2016+**), prefer **`statcast_fielding_oaa.fielding_runs_prevented`**; RF/9 z-scores stabilize earlier seasons and fringe cases without Statcast bundles.
- **Next.js divergence:** **`AGENTS.md`** — read in-repo **`node_modules/next/dist/docs/`**; don’t assume pre-App-Router ergonomics.

---

## 10. Validation targets

Use these MLBAM IDs when sanity-checking published metrics:

| Player | MLBAM ID | Use for |
|--------|----------|---------|
| **Aaron Judge** | **`592450`** | **bWPR**, **fWPR**, **CQI** |
| **Paul Skenes** | **`694973`** | **pWPR**, **Stuff+** |

---

## 11. Repository map (abbrev.)

```
warroom/
├── HANDOFF.md
├── SCHEMA.md
├── AGENTS.md
├── package.json
├── src/app/          # Routes + api/
├── src/components/
├── src/lib/
├── supabase/migrations/
└── pipeline/
    ├── calculations/
    └── *.py          # Scripts in §4.2
```

---

## 12. Local dev cheatsheet

```bash
# Web
cd warroom && npm install && npm run dev   # requires .env.local NEXT_PUBLIC_* 

# Pipeline
cd warroom/pipeline
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
# pipeline/.env: SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY

python scheduler.py                         # Eastern-hour Statcast polling
python calc_fielding_season_metrics.py --start-season 2024 --end-season 2026
```

Quality gates: `npm run lint`, `npx tsc --noEmit`.

---

*Update this document when workflows, rollup formulas, or table ownership change materially.*
