# WARroom — Developer handoff documentation

This document orients a new maintainer to the **WARroom** codebase: a Next.js frontend backed by **Supabase** (Postgres + realtime), with a **Python/pandas/pybaseball ETL** pipeline that ingests MLB Statcast pitch data and maintains derived leaderboards and player-season metrics.

Canonical schema notes, RLS, RPC contracts, and migration hints live in **`SCHEMA.md`** (read alongside this file).

---

## 1. What the platform does

| Layer | Role |
|-------|------|
| **Web app** (`src/`) | Browse players, teams, standings, Statcast explorer with live pitch updates, batting leaderboards |
| **API routes** (`src/app/api/`) | Server-side aggregation: MLB Stats API + Supabase reads |
| **Supabase** | Primary data store: Statcast pitches, Statcast batting/pitching aggregates, historical player/team seasons, game logs, park factors, league averages |
| **Pipeline** (`pipeline/`) | Scheduled and manual jobs: Statcast ETL, aggregates, leaderboards seeding, derived metrics (wOBA, OPS+, WPR, CQI, Stuff+, etc.) |

**Identifiers:** Player / team ids follow **MLBAM** (Major League Baseball Advanced Media) integers. Many tables use **soft references** (no FK to `players.id`) so Statcast rows can exist before roster rows.

---

## 2. Repository layout

```
warroom/
├── HANDOFF.md              ← this file
├── SCHEMA.md               ← database tables, indexes, RLS, RPC behavior, realtime
├── README.md               ← default create-next-app readme (not operational)
├── package.json            ← Next.js 16, React 19, Supabase JS, Tailwind 4
├── tsconfig.json
├── .env.local              ← local Next env (not committed; see §5)
│
├── src/
│   ├── app/                ← App Router pages + API routes
│   ├── components/         ← UI (layout, Statcast sections, charts)
│   ├── lib/                ← supabase client, MLB fetch, formulas, realtime hook
│   └── types/index.ts      ← shared TS types for API responses / tables
│
├── supabase/migrations/    ← ordered SQL migrations (source of truth for DB evolution)
│
└── pipeline/               ← Python ETL + calculations
    ├── .env                ← service role + Supabase URL (not committed)
    ├── config.py           ← loads pipeline/.env
    ├── db.py               ← Supabase client (service role)
    ├── requirements.txt
    ├── calculations/       ← batting / pitching / fielding / league JSON
    └── *.py                ← seeders, aggregators, metric runners, scheduler
```

---

## 3. Technology stack

| Area | Stack |
|------|--------|
| Frontend | Next.js **16** (App Router), React **19**, TypeScript |
| Styling | Tailwind CSS **4** (`@tailwindcss/postcss`), `globals.css` |
| Charts | Recharts (where used) |
| Browser DB | `@supabase/supabase-js` with **anon key** (+ optional Realtime) |
| Server API | Route handlers call Supabase anon client + `NEXT_PUBLIC_MLB_API_BASE` |
| Database | Supabase Postgres, Row Level Security (public read on most stats tables) |
| Pipeline | Python 3; **pybaseball** (Savant); **pandas**; **supabase-py**; **APScheduler** (blocking cron) |

**Agent hints:** Root `AGENTS.md` points at Next.js in-repo docs under `node_modules/next/dist/docs/` — this repo may use conventions newer than generic training cutoff.

---

## 4. Environment variables

### 4.1 Next.js (`warroom/.env.local`)

Required for builds / local dev:

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Public anon key (RLS applies) |
| `NEXT_PUBLIC_MLB_API_BASE` | MLB Stats API base URL (e.g. `https://statsapi.mlb.com/api/v1`) |

### 4.2 Pipeline (`warroom/pipeline/.env`)

| Variable | Purpose |
|----------|---------|
| `SUPABASE_URL` | Same project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | **Server-only** — bypasses RLS for ETL writes |

**Never** expose the service role key to the browser or commit it.

---

## 5. External connections

| System | Usage | Typical entry point |
|--------|--------|---------------------|
| **Supabase Postgres** | All persisted stats | `src/lib/supabase.ts` (anon), `pipeline/db.py` (service) |
| **Supabase Realtime** | Live `statcast_pitches` inserts on explorer | `src/lib/supabase-realtime.ts`, publication setup in `SCHEMA.md` |
| **MLB Stats API** | Live season lines, teams, standings, schedules | `src/lib/mlb-api.ts` (`mlbFetch`) |
| **Baseball Savant** (via **pybaseball**) | Pitch-by-pitch Statcast CSV for date ranges | `pipeline/statcast_pipeline.py` |

---

## 6. Database & migrations

- **Living documentation:** **`SCHEMA.md`** — tables, views, uniqueness for upserts, which columns are “owned” by which loader, RPC signatures, partial upsert semantics, realtime publication notes.
- **Executable history:** **`supabase/migrations/*.sql`** — apply in timestamp order when provisioning a fresh project.

Notable migration themes:

- Statcast pitches natural key `(game_pk, at_bat_number, pitch_number)`; batter/pitcher columns renamed to `batter_id`, `pitcher_id` (`20260519100000_*`).
- Statcast pitching + arsenal + league pitch-type averages (hand-split `p_throws`) (`202605191*`).
- Partial upserts for Statcast batting/pitching RPCs (`2026052210*`) — omitted JSON keys preserve existing DB values on conflict.
- Partial upserts for `player_*_seasons` (`20260522130000_*`).
- `player_batting_seasons.war` → **`bwpr`**, **`fwpr`**, **`brwpr`**, **`wpr`**; pitching `war` → **`pwpr`** (`20260522150000_*`).
- League warehouse tables **`league_batting_averages`**, **`league_pitching_averages`** (`20260522140000_*`).
- Statcast percentile RPCs: **`get_batter_statcast_percentiles`**, **`get_pitcher_statcast_percentiles`** (`20260522160000_*`, `20260522170000_*`) — consumed by `GET /api/players/[id]`.

Grant **execute** on new RPCs to `anon` / `authenticated` as needed if PostgREST returns permission errors.

---

## 7. Python pipeline (`pipeline/`)

All scripts assume `pipeline/.env` is loadable (`import config` triggers `python-dotenv`).

### 7.1 Core infrastructure

| File | Purpose |
|------|---------|
| `config.py` | `SUPABASE_*`, Eastern game-hour window, poll interval |
| `db.py` | Singleton `create_client(url, SERVICE_ROLE_KEY)` |
| `statcast_pipeline.py` | Daily Statcast fetch → normalized rows → batched upsert into `statcast_pitches` |
| `scheduler.py` | APScheduler cron: Eastern hours, every `POLL_INTERVAL_MINUTES`, calls `run_pipeline` |

### 7.2 Statcast aggregation & leaderboards

| File | Purpose |
|------|---------|
| `aggregate_statcast_batting.py` | From `statcast_pitches`: BBE aggregates → `upsert_statcast_batting_aggregates` (Savant barrel math documented in-file) |
| `aggregate_statcast_pitching.py` | Pitcher-season and arsenal rollup → pitching RPCs |
| `seed_statcast_batting.py` | pybaseball **leaderboard** fields for `statcast_batting` (xSTATS, sprint, names, team) — distinct from aggregates ownership in `SCHEMA.md` |

### 7.3 Historical / reference seeding

| File | Purpose |
|------|---------|
| `seed_players.py`, `seed_teams.py`, `seed_missing_players.py`, `fix_missing_players.py` | Roster / id hygiene |
| `seed_historical_players.py` | Bulk historical player bios |
| `seed_game_logs.py`, `enrich_game_logs.py` | Box scores / game tally (feeds **`game_logs`** for replacement-level game counts / PA floors) |
| `seed_*_seasons.py` (player batting/pitching/fielding/position; team batting/pitching/fielding) | Warehouse season totals from pybaseball or similar |

### 7.4 Derived metrics (warehouse)

| File | Purpose |
|------|---------|
| `calc_league_averages.py` | Fills **`league_batting_averages`** / **`league_pitching_averages`** from aggregated season tables |
| `calc_league_pitch_type_averages.py` | **`league_pitch_type_averages`** — handedness-split baselines for movement / Stuff+ |
| `calc_batting_metrics.py`, `calc_pitching_metrics.py` | Row-level patches (e.g. CQI on batting lines tied to Statcast) |
| `calc_batting_season_metrics.py` | Reads `player_batting_seasons` counts → rates, OPS+, wRC+, **bwpr** via `calc_batting_war`, partial upsert |
| `calc_pitching_season_metrics.py` | Pitching rates, ERA+, **pwpr**, Stuff+ season rollup; uses league tables + **`park_factors`** |
| `calc_park_factors.py` | Computes / loads park run environment into **`park_factors`** |

### 7.5 Utilities / one-offs

| File | Purpose |
|------|---------|
| `backfill_statcast.py`, `backfill_statcast_historical.py`, `rerun_dates.py` | Date-range replays |
| `test_stat_splits.py` | Split testing helper |

---

## 8. Calculations

### 8.1 Python (`pipeline/calculations/`)

| Module | Highlights |
|--------|------------|
| **`constants.py`** | Season thresholds (e.g. Statcast min year), FanGraphs-style **wOBA weights** (`get_woba_weights`), **FIP constant** (`get_fip_constant`) |
| **`fetch_league_averages.py`** | Loads **`league_averages.json`** (checked-in bundle) plus integration with **`calc_league_averages`**-filled DB tables |
| **`batting_calcs.py`** | ISO, BABIP, wOBA, OPS+, wRC+, **CQI** (Statcast vs league baseline), **`calc_batting_war`** (positional WPR; uses **`get_mlb_games_played`** rules: 2020→900, pre-2022→2430, else count from **`game_logs`**) |
| **`pitching_calcs.py`** | K/9, BB/9, HR/9, WHIP, FIP, ERA+ (`100 × lgERA / ERA / park_factor`), **`calc_pitching_war`**, LOB%, **`calc_stuff_plus`** (arsenal vs `league_pitch_type_averages`) |
| **`fielding_calcs.py`** | FIELD%, RF/9, RF/G — basic derived fielding |

**WPR naming:** DB columns **`bwpr`**, **`pwpr`**, and rollups **`fwpr`**, **`brwpr`**, **`wpr`** (see migration `20260522150000_*`). Older docs may still say “WAR”; code comments in season-metric scripts use WPR terminology.

### 8.2 TypeScript (`src/lib/formulas/`)

Duplicate or UI-adjacent formula helpers for batting / pitching / fielding (used where the frontend computes display-only values). Prefer **pipeline + DB** as source of truth for published metrics.

---

## 9. Next.js application

### 9.1 Pages (`src/app/`)

| Route | Description |
|-------|-------------|
| `/` | Home |
| `/players` | Player list |
| `/players/[id]` | Profile: MLB season stats table, **`BatterStatcastSection`** or **`PitcherStatcastSection`** (percentiles from RPCs), recent pitches |
| `/teams`, `/teams/[id]` | Team browsing + Statcast-backed team API consumers |
| `/statcast` | Explorer: realtime pitch feed (`useStatcastRealtime`) |
| `/leaderboards/batting` | Statcast batting leaderboard API consumer |

Layouts: `layout.tsx`, `Navbar`, `Footer`.

### 9.2 API routes (`src/app/api/`)

| Route | Role |
|-------|------|
| `players/route.ts` | List/search players |
| `players/[id]/route.ts` | MLB person hydrate + Supabase (`statcast_batting`, `players`, historical seasons), RPCs **`get_batter_statcast_percentiles`**, **`get_pitcher_statcast_percentiles`** |
| `players/[id]/pitches/route.ts` | Recent pitch rows for profile |
| `statcast/pitches/route.ts` | Pitch queries for explorer |
| `statcast/leaderboard/route.ts` | Leaderboard payloads |
| `leaderboards/batting/route.ts` | Batting board |
| `teams/*`, `standings/route.ts`, `schedule/route.ts` | MLB-facing aggregates |

Types for JSON bodies live in **`src/types/index.ts`**.

### 9.3 Key UI components (`src/components/ui/`)

| Component | Role |
|-----------|------|
| `BatterStatcastSection.tsx` | Renders **`batterPercentiles`** JSON from API |
| `PitcherStatcastSection.tsx` | Renders **`pitcherPercentiles`** (overall + arsenal) |
| `PercentileBar.tsx` | Shared percentile visuals |

---

## 10. Data ownership (quick reference)

Avoid double-writing incompatible columns:

- **`aggregate_statcast_batting`** (RPC `upsert_statcast_batting_aggregates`): PA, EV, barrels, hard-hit, launch angle aggregates — **not** xSTATS/sprint/name/team.
- **`seed_statcast_batting`**: leaderboard-owned columns including xBA/xSLG/xwOBA, sprint, display metadata.
- **`calc_batting_metrics`**: can own **CQI** on appropriate rows when Statcast is present.

See **`SCHEMA.md`** for the authoritative split per table/RPC.

---

## 11. Local development

### 11.1 Web

```bash
cd warroom
npm install
# create .env.local with NEXT_PUBLIC_* vars
npm run dev
```

### 11.2 Pipeline

```bash
cd warroom/pipeline
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
# create .env with SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY

python statcast_pipeline.py    # typical one-shot (see module for CLI)
python scheduler.py           # long-running poller + immediate first run
```

Individual scripts expose `argparse` CLIs (`--season`, `--start-date`, etc.); inspect `if __name__ == "__main__"` blocks.

### 11.3 Quality gates

```bash
cd warroom
npm run lint
npx tsc --noEmit
```

---

## 12. Operations checklist for a new environment

1. Create Supabase project; run **`supabase/migrations`** in order.
2. Configure Realtime publication for Statcast tables if live explorer is needed (`SCHEMA.md` snippet).
3. Add RLS policies if new tables lack them (mirror existing patterns — public SELECT for stats tables).
4. Set Next.js **`NEXT_PUBLIC_*`** and pipeline **service role** secrets.
5. Seed reference data: teams, players, game logs (for denominator logic), league averages tables.
6. Run Statcast ETL + aggregates + seasonal metric calculators in dependency order for the seasons you care about.
7. Verify PostgREST: RPC **`get_*_statcast_percentiles`** executable by anon/authenticated roles.

---

## 13. Glossary

| Term | Meaning |
|------|---------|
| **WPR** | Wins above Replacement (positional branding in DB; batting `bwpr`, pitching `pwpr`, total placeholder `wpr`) |
| **CQI** | Contact Quality Index (100 = league average) — batting/Statcast context |
| **Stuff+** | Pitch movement/velo/spin composite vs handedness-split league averages |
| **Soft reference** | Logical MLBAM id link without enforcing FK to `players` |

---

## 14. What this handoff intentionally does **not** duplicate

- **Full DDL:** see **`SCHEMA.md`** (and migrations for exact incremental changes).
- **Line-by-line every source file:** use this document as the map; open files by concern area (§2, §7, §9).
- **Committed secrets:** `.env.local` / `pipeline/.env` are absent from git — recreate from §4.

---

*Last oriented to repo layout as of handoff authoring. Update this file when you add major subsystems or change env/contract surfaces.*
