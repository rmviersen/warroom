# WARroom — Cursor Frontend Briefing

> **Branch:** A new feature branch will be provided by Claude Code at the start of each session.
> Always work on that branch. Never commit to `main` directly.
> Claude Code owns `pipeline/`, `supabase/migrations/`, `SCHEMA.md`, `HANDOFF.md`, `CLAUDE.md` — do not touch those paths.

---

## What this project is

WARroom is an MLB analytics platform. It pulls live MLB schedule/standings data and Statcast data from a Supabase Postgres database, and displays it in a dark-themed Next.js app. The core product is a set of proprietary WPR metrics (WARroom-style wins above replacement) — bWPR (batting), fWPR (fielding), brWPR (baserunning), pWPR (pitching), and Total WPR.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Framework | **Next.js** (App Router) — see `node_modules/next/dist/docs/` for this version's docs |
| Language | **TypeScript** + **React 19** |
| Styling | **Tailwind CSS v4** |
| Database client | **Supabase** (`src/lib/supabase.ts` — anon key, RLS on) |
| Icons | **lucide-react** |
| Images | `next/image` |

**Important:** This Next.js version may differ from training data. Read `node_modules/next/dist/docs/` before writing any Next.js-specific code.

---

## How to run the dev server

From the repo root:
```
npm run dev
```
App runs at `http://localhost:3000`.

---

## Repo structure — frontend

```
src/
  app/
    layout.tsx                        ← root layout, wraps all pages in Navbar + Footer
    page.tsx                          ← homepage: today's games banner + AL/NL standings
    globals.css                       ← global styles
    api/
      leaderboards/
        batting/route.ts              ← GET /api/leaderboards/batting
        pitching/route.ts             ← GET /api/leaderboards/pitching
        baserunning/route.ts          ← GET /api/leaderboards/baserunning
      players/
        route.ts                      ← GET /api/players
        [id]/route.ts                 ← GET /api/players/[id]
        [id]/pitches/route.ts         ← GET /api/players/[id]/pitches
      schedule/route.ts               ← GET /api/schedule (MLB API)
      standings/route.ts              ← GET /api/standings (MLB API)
      statcast/
        leaderboard/route.ts
        pitches/route.ts
      status/route.ts                 ← GET /api/status (RAG pipeline health)
      teams/
        route.ts
        [id]/route.ts
        [id]/statcast/route.ts
        [id]/position-wpr/route.ts    ← GET /api/teams/[id]/position-wpr?season=YYYY
        [id]/position-wpr/players/route.ts  ← GET /api/teams/[id]/position-wpr/players?season=YYYY
    leaderboards/
      batting/page.tsx                ← bWPR / batting leaderboard
      pitching/page.tsx               ← pWPR / pitching leaderboard
      baserunning/page.tsx            ← brWPR / baserunning leaderboard
    players/
      page.tsx                        ← player search/list
      [id]/page.tsx                   ← individual player profile
    statcast/page.tsx
    status/page.tsx                   ← RAG health dashboard (pipeline status)
    teams/
      layout.tsx
      page.tsx
      [id]/page.tsx                   ← team overview with WPR by position (field view + table)
  components/
    layout/
      Navbar.tsx                      ← sticky top nav; Leaderboards dropdown
      Footer.tsx
    ui/
      BaseballFieldView.tsx           ← SVG baseball field with per-position WPR cards
      BatterStatcastSection.tsx
      PitcherStatcastSection.tsx
      PercentileBar.tsx
      PlayerCurrentSeasonPanel.tsx    ← current season stats + WPR panel for player profiles
      PlayerProfileBanner.tsx         ← player header with name, position, team, WPR summary
      TeamWprDiamond.tsx              ← team WPR by position table with expandable player rows
      WARroomLogo.tsx
  lib/
    supabase.ts                       ← Supabase browser client (anon key)
    mlb-api.ts                        ← MLB Stats API helpers
    mlb-images.ts                     ← team logo URL helper
    mlb-player-stats.ts
    mlb-team-stats.ts
    mlb-team-overview.ts              ← team-level data fetching helpers
    playoff-teams.ts                  ← playoff team list helpers
    formulas/
      batting.ts
      pitching.ts
      fielding.ts
      index.ts
  types/
    index.ts                          ← shared TypeScript types (TeamPositionWprRow, etc.)
```

---

## Brand & design conventions

### Colors
| Use | Value |
|-----|-------|
| Navy (primary brand) | `#1e3a6b` |
| Gold — **WPR metrics ONLY** | `#b8922a` |
| Accent / active states | Red (`red-500`, `red-400`, etc.) |
| Background dark | `gray-950`, `gray-900` |
| Text primary | `white`, `gray-100` |
| Text secondary | `gray-400`, `gray-500` |

**Critical:** The gold color (`#b8922a`) is **reserved exclusively** for WARroom proprietary metrics: **bWPR, fWPR, brWPR, pWPR, WPR, CQI, Stuff+**. Do not use it for general chrome, headings, or decorative elements.

### Design style
- Dark theme throughout — no light-mode variants needed
- Tables: dark borders (`border-gray-800`), subtle hover states (`hover:bg-gray-800/15`), `tabular-nums` for all numbers
- Cards: `rounded-lg border border-gray-800 bg-gray-900/40`
- Section headers: small red accent bar (`h-1 w-6 rounded-full bg-red-500`) before heading text
- Division leaders in standings get a left red border (`border-l-2 border-l-red-500`)
- Loading states: spinning border animation (`animate-spin border-red-500 border-t-transparent`)

---

## Navbar — current state

The Navbar (`src/components/layout/Navbar.tsx`) has:
- **WARroom** logo (left) → links to `/`
- Nav items (right): **Teams** · **Players** · **Leaderboards** (dropdown) · **Statcast**
- **Leaderboards dropdown** reveals: Batting · Pitching · Baserunning

### Adding a new leaderboard to the dropdown
Edit the `LeaderboardsDropdown` component in `Navbar.tsx` and add a new `<Link>` entry. Match the existing `subCls()` pattern for active state styling.

---

## Available data — what Supabase has

All data is read via the API routes (server-side) or directly via `src/lib/supabase.ts` (anon key, respects RLS — public read is enabled on all tables and views).

### Key tables and their useful columns

**`player_batting_seasons`** — one row per player per season per team
- `player_id` (MLBAM int), `season`, `team_id`, `team`
- Counting stats: `g`, `pa`, `ab`, `h`, `hr`, `rbi`, `sb`, `cs`, `bb`, `so`, `avg`, `obp`, `slg`, `ops`
- WPR metrics: **`bwpr`**, **`fwpr`**, **`brwpr`**, **`wpr`** (total = bwpr + fwpr + brwpr)

**`player_pitching_seasons`** — one row per pitcher per season per team
- `player_id`, `season`, `team_id`, `team`
- Stats: `w`, `l`, `era`, `g`, `gs`, `ip`, `so`, `bb`, `whip`, `fip`
- WPR metric: **`pwpr`**

**`statcast_batting`** — Statcast aggregates per batter-season
- `player_id`, `season`, `exit_velocity_avg`, `launch_angle_avg`, `barrel_rate`, `hard_hit_rate`, `xba`, `xslg`, `xwoba`
- WARroom metric: **`cqi`** (Contact Quality Index — gold color)

**`statcast_pitching`** — Statcast aggregates per pitcher-season
- `player_id`, `season`, `era`, `fip`, `xera`, `whiff_rate`, `chase_rate`, `k_rate`, `bb_rate`
- WARroom metric: **`stuff_plus`** (gold color)

**`statcast_running`** — Sprint speed data (2015+)
- `player_id`, `season`, `sprint_speed`, `hp_to_1b`, `bolts`, `competitive_runs`, `bolt_rate`

**`statcast_baserunning_rv`** — Statcast baserunning run values (2016+)
- `player_id`, `season`, `running_runs`, `extra_bases_taken`, `outs_made`, `bases_advanced`
- Source of **brWPR** for modern seasons

**`players`** — Player registry
- `id` (MLBAM), `full_name`, `team`, `team_id`, `position`, `bats`, `throws`

**`teams`** — Team registry
- `id` (MLBAM), `name`, `abbreviation`, `team_code`

### Key views (read the same way as tables via Supabase client)

**`player_season_wpr_totals`** — Unified WPR for every player type
- `player_id`, `player_name`, `season`, `team_id`, `team`
- `bwpr`, `fwpr`, `brwpr`, `wpr` (position player total), `pwpr` (pitching)
- **`total_wpr`** = `ROUND(COALESCE(wpr, 0) + COALESCE(pwpr, 0), 1)` — use this for cross-player WPR comparisons and leaderboards
- Covers position players, pitchers, and two-way players

**`team_position_wpr_season`** — Innings-weighted team WPR per defensive position
- `team_id`, `season`, `position`, `bwpr`, `fwpr`, `brwpr`, `wpr`, `pwpr`, `player_count`
- Used by `BaseballFieldView` and `TeamWprDiamond`
- **Do not query this directly for rankings** — the API route at `teams/[id]/position-wpr` computes MLB-wide ranks in TypeScript

**`team_position_wpr_players_season`** — Per-player contribution within each team/position
- `team_id`, `season`, `position`, `player_id`, `player_name`, `inn`, `inn_share`
- `bwpr_attr`, `fwpr_attr`, `brwpr_attr`, `wpr_attr`, `pwpr_attr`
- Used by expandable rows in `TeamWprDiamond`

---

## Position WPR — how the team page works

The team page (`src/app/teams/[id]/page.tsx`) loads team data first, then uses `stats.season` for downstream calls. **Never fire WPR or Statcast fetches in parallel with the team fetch** — you need `stats.season` before making those calls.

The position WPR API (`/api/teams/[id]/position-wpr`) returns:
```typescript
{
  positions: TeamPositionWprRow[],  // one per position (C, 1B, 2B, 3B, SS, LF, CF, RF, P)
  season: number
}
```

Each `TeamPositionWprRow` includes MLB-wide rank fields: `bwpr_rank`, `fwpr_rank`, `brwpr_rank`, `wpr_rank`, `pwpr_rank` (1 = best in MLB), and `team_count` (denominator, usually 30).

---

## What to build next (priority order)

### Priority 1 — Total WPR leaderboard
**File to create:** `src/app/leaderboards/wpr/page.tsx`
**API route to create:** `src/app/api/leaderboards/wpr/route.ts`

Query `player_season_wpr_totals` view. Show columns: Rank, Player, Team, Season, bWPR, fWPR, brWPR, pWPR, **Total WPR** (gold, bold). Filter by season (default 2026). Sort by `total_wpr` descending. Add to the Navbar Leaderboards dropdown. This is the flagship cross-player leaderboard — treat it as a hero feature.

### Priority 2 — Player profile: Total WPR summary card
In `src/app/players/[id]/page.tsx`, add a WPR summary section that shows all components a player has (bWPR + fWPR + brWPR + pWPR where applicable), with a bolded Total WPR line. Two-way players (Ohtani) will have both batting and pitching rows — handle both. Use `player_season_wpr_totals` as the data source.

### Priority 3 — Status page polish
`src/app/status/page.tsx` is functional but may need visual polish to match the rest of the platform. Ensure the RAG color coding (green/amber/red) is consistent with brand colors (use red for down, gold/amber for warning, green for healthy).

### Priority 4 — brWPR column on batting leaderboard
The batting leaderboard at `/leaderboards/batting` shows bWPR. Add `brwpr` and the `wpr` total as additional columns to give a more complete position-player picture.

---

## What NOT to touch

| Path | Reason |
|------|--------|
| `pipeline/` | Python ETL — Claude Code's domain |
| `supabase/migrations/` | Schema DDL — Claude Code's domain |
| `SCHEMA.md` | Schema documentation — Claude Code's domain |
| `HANDOFF.md` | Architecture docs — Claude Code's domain |
| `CLAUDE.md` | Claude Code instructions |
| `pipeline/.env` | Contains service role key — never touch |

---

## Environment variables (frontend)

All frontend env vars live in `.env.local` at the repo root (gitignored, already set up):
```
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
NEXT_PUBLIC_MLB_API_BASE=https://statsapi.mlb.com/api/v1
```

Never use the service role key in frontend code. The anon key + RLS is the correct pattern for browser-side Supabase reads.

---

## Known gotchas

- **`team_id` can be a string from Supabase** — always use `Number(id)` before comparing, never strict `===` against a number literal.
- **Load order on team page** — fetch team first to get `stats.season`, then fire WPR/Statcast calls with that season. Don't use `new Date().getFullYear()` as a fallback.
- **Views flagged as "unrestricted" in Supabase dashboard** — this is a known dashboard artifact for views. The views are secure; their underlying tables all have RLS enabled.
- **PostgREST row cap** — `.select()` returns a max of 1000 rows by default. Use `.range(offset, offset + 999)` for large tables.

---

## Merging back to main

When your frontend work is ready:
1. Commit your changes on the feature branch
2. Push: `git push origin <branch-name>`
3. Tell Rees — he will coordinate the merge with Claude Code

Do not merge feature branches into each other — they will each merge into `main` independently.
