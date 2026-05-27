# WARroom — Cursor Frontend Briefing

> **Your branch: `feat/frontend-ui`**
> Always work on this branch. Never commit to `main` directly.
> Claude Code works on `feat/pipeline-wpr` (backend/database) — those branches do not overlap.

---

## What this project is

WARroom is an MLB analytics platform. It pulls live MLB schedule/standings data and Statcast data from a Supabase Postgres database, and displays it in a dark-themed Next.js app. The core product is a set of proprietary WPR metrics (Wins above replacement, WARroom-style) — bWPR (batting), fWPR (fielding), brWPR (baserunning), pWPR (pitching).

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

## Repo structure — frontend only

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
      players/
        route.ts                      ← GET /api/players
        [id]/route.ts                 ← GET /api/players/[id]
        [id]/pitches/route.ts         ← GET /api/players/[id]/pitches
      schedule/route.ts               ← GET /api/schedule (MLB API)
      standings/route.ts              ← GET /api/standings (MLB API)
      statcast/
        leaderboard/route.ts
        pitches/route.ts
      teams/
        route.ts
        [id]/route.ts
        [id]/statcast/route.ts
    leaderboards/
      batting/page.tsx                ← bWPR / batting leaderboard
      pitching/page.tsx               ← pWPR / pitching leaderboard
    players/
      page.tsx                        ← player search/list
      [id]/page.tsx                   ← individual player profile
    statcast/page.tsx
    teams/
      page.tsx
      [id]/page.tsx
  components/
    layout/
      Navbar.tsx                      ← sticky top nav; has dropdown for Leaderboards
      Footer.tsx
    ui/
      BatterStatcastSection.tsx
      PitcherStatcastSection.tsx
      PercentileBar.tsx
      WARroomLogo.tsx
  lib/
    supabase.ts                       ← Supabase browser client (anon key)
    mlb-api.ts                        ← MLB Stats API helpers
    mlb-images.ts                     ← team logo URL helper
    mlb-player-stats.ts
    mlb-team-stats.ts
    formulas/
      batting.ts
      pitching.ts
      fielding.ts
      index.ts
  types/
    index.ts                          ← shared TypeScript types
```

---

## Brand & design conventions

### Colors
| Use | Value |
|-----|-------|
| Navy (primary brand) | `#1e3a6b` |
| Gold — **WPR metrics ONLY** | `#b8922a` (use `#c9a84c` / `#c9a84c` for nav accents — check existing Navbar) |
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
- **Leaderboards dropdown** reveals: Batting · Pitching (hover-activated)

### Adding a new leaderboard to the dropdown
Edit the `LeaderboardsDropdown` component in `Navbar.tsx` and add a new `<Link>` entry. Match the existing `subCls()` pattern for active state styling.

---

## Available data — what Supabase has

All data is read via the API routes (which use the service role server-side) or directly via `src/lib/supabase.ts` (anon key, respects RLS — public read is enabled on all tables).

### Key tables and their useful columns

**`player_batting_seasons`** — one row per player per season per team
- `player_id` (MLBAM int), `season`, `team_id`
- Counting stats: `g`, `pa`, `ab`, `h`, `hr`, `rbi`, `sb`, `cs`, `bb`, `so`, `avg`, `obp`, `slg`, `ops`
- WPR metrics: **`bwpr`**, **`fwpr`**, **`brwpr`** (all stored; `wpr` total coming soon)

**`player_pitching_seasons`** — one row per pitcher per season per team
- `player_id`, `season`, `team_id`
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

**`players`** — Player registry
- `id` (MLBAM), `full_name`, `team`, `team_id`, `position`, `bats`, `throws`

**`teams`** — Team registry
- `id` (MLBAM), `name`, `abbreviation`, `team_code`

---

## What to build on `feat/frontend-ui`

### Priority 1 — Baserunning leaderboard page
**File to create:** `src/app/leaderboards/baserunning/page.tsx`
**API route to create:** `src/app/api/leaderboards/baserunning/route.ts`

Query `player_batting_seasons` joined with `players` for `brwpr`, `sb`, `cs`. Show columns: Rank, Player, Team, Season, SB, CS, brWPR (gold). Filter by season (default 2026). Sort by brWPR descending. Add to the Navbar Leaderboards dropdown.

### Priority 2 — Add brWPR column to batting leaderboard
The batting leaderboard at `/leaderboards/batting` currently shows bWPR. Add `brwpr` as a column alongside `bwpr` and `fwpr` to give a more complete picture.

### Priority 3 — Player profile: brWPR & sprint speed section
In `src/app/players/[id]/page.tsx`, add a baserunning section that shows:
- brWPR (gold, bold)
- Sprint speed (if available from `statcast_running` — 2015+)
- SB / CS / bolt rate

### Priority 4 — WPR total rollup display (when backend delivers it)
The `wpr` column on `player_batting_seasons` will be populated by the backend pipeline soon. Once it is, add a "Total WPR" display on player profiles and a combined WPR leaderboard.

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

## Merging back to main

When your frontend work is ready:
1. Commit your changes on `feat/frontend-ui`
2. Push: `git push origin feat/frontend-ui`
3. Tell Rees — he will coordinate the merge with Claude Code

Do not merge `feat/pipeline-wpr` into `feat/frontend-ui` or vice versa — they will both merge into `main` independently.
