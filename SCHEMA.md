-- ==============================================
-- WARroom Database Schema
-- ==============================================

-- Players table
CREATE TABLE players (
  id BIGINT PRIMARY KEY,
  full_name TEXT NOT NULL,
  team TEXT,
  team_id BIGINT,
  position TEXT,
  jersey_number TEXT,
  bats TEXT,
  throws TEXT,
  birth_date DATE,
  debut_date DATE,
  final_game DATE,
  name_first TEXT,
  name_last TEXT,
  birth_city TEXT,
  birth_country TEXT,
  height TEXT,
  weight INTEGER,
  active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Teams table
CREATE TABLE teams (
  id BIGINT PRIMARY KEY,
  name TEXT NOT NULL,
  abbreviation TEXT,
  team_name TEXT,
  location_name TEXT,
  division TEXT,
  division_id BIGINT,
  league TEXT,
  league_id BIGINT,
  venue TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Statcast pitches table
-- batter_id / pitcher_id: MLBAM ids; soft references to players.id (no FKs). Use for joins when rows exist.
-- pitcher_name / batter_name: Savant string names (nullable).
-- Natural key for upserts: unique ``(game_pk, at_bat_number, pitch_number)`` (Savant pitch id).
CREATE TABLE statcast_pitches (
  id BIGSERIAL PRIMARY KEY,
  batter_id BIGINT,
  batter_name TEXT,
  pitcher_id BIGINT,
  pitcher_name TEXT,
  game_date DATE,
  game_pk BIGINT,
  at_bat_number INTEGER,
  pitch_number INTEGER,
  pitch_type TEXT,
  pitch_name TEXT,
  release_speed NUMERIC,
  release_spin_rate NUMERIC,
  pfx_x NUMERIC,
  pfx_z NUMERIC,
  plate_x NUMERIC,
  plate_z NUMERIC,
  launch_angle NUMERIC,
  launch_speed NUMERIC,
  hit_distance NUMERIC,
  events TEXT,
  description TEXT,
  zone INTEGER,
  stand TEXT,
  p_throws TEXT,
  home_team TEXT,
  away_team TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Statcast batting leaderboard table (``pa``: Savant attempts / expected-stats PA; see SCHEMA migration note)
-- player_id: soft reference to players.id (no FK), analogous to statcast_pitches.batter_id
CREATE TABLE statcast_batting (
  id BIGSERIAL PRIMARY KEY,
  player_id BIGINT,
  player_name TEXT,
  team_id BIGINT,
  season INTEGER,
  pa INTEGER,
  avg_exit_velocity NUMERIC,
  max_exit_velocity NUMERIC,
  avg_launch_angle NUMERIC,
  barrel_rate NUMERIC,
  hard_hit_rate NUMERIC,
  xba NUMERIC,
  xslg NUMERIC,
  xwoba NUMERIC,
  sprint_speed NUMERIC,
  cqi NUMERIC(6,2),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Statcast pitching aggregates by pitcher and season (leaderboard / Savant-style rates)
-- pitcher_id: soft reference to players.id (no FK), consistent with statcast_pitches.pitcher_id
-- Upserts: unique index on (pitcher_id, season) — ``idx_statcast_pitching_pitcher_season``
-- avg_fastball_velo: mean release_speed on pitch types FF, SI, FC only; spin/movement by type → statcast_pitching_arsenal
CREATE TABLE statcast_pitching (
  id BIGSERIAL PRIMARY KEY,
  pitcher_id BIGINT,
  pitcher_name TEXT,
  season INTEGER,
  pitches INTEGER,
  avg_fastball_velo NUMERIC,
  max_velo NUMERIC,
  whiff_rate NUMERIC,
  chase_rate NUMERIC,
  stuff_plus NUMERIC,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- League benchmarks by season, Savant ``pitch_type``, and pitcher handedness ``p_throws`` (warehouse table).
-- Splitting L/R avoids canceling horizontal movement when averaging ``pfx_x``. Populated by
-- ``pipeline/calc_league_pitch_type_averages.py``. Used as league denominators for ``stuff_plus_pitch`` on
-- ``statcast_pitching_arsenal`` (when present).
CREATE TABLE league_pitch_type_averages (
  id BIGSERIAL PRIMARY KEY,
  season INTEGER NOT NULL,
  pitch_type TEXT NOT NULL,
  p_throws TEXT,
  pitch_category TEXT NOT NULL,
  pitch_count INTEGER,
  avg_velo NUMERIC,
  avg_spin_rate NUMERIC,
  avg_h_movement NUMERIC,
  avg_v_movement NUMERIC,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Per-pitcher arsenal by ``pitch_type``, ``p_throws`` (handedness), and ``pitch_category``.
-- One row per ``(pitcher_id, season, pitch_type, p_throws)``. ``stuff_plus_pitch`` uses
-- ``league_pitch_type_averages`` rows with matching ``season``, ``pitch_type``, and ``p_throws``.
CREATE TABLE statcast_pitching_arsenal (
  id BIGSERIAL PRIMARY KEY,
  pitcher_id BIGINT NOT NULL,
  pitcher_name TEXT,
  season INTEGER NOT NULL,
  pitch_type TEXT NOT NULL,
  p_throws TEXT,
  pitch_category TEXT NOT NULL,
  pitches INTEGER,
  usage_rate NUMERIC,
  avg_velo NUMERIC,
  avg_spin_rate NUMERIC,
  avg_h_movement NUMERIC,
  avg_v_movement NUMERIC,
  whiff_rate NUMERIC,
  chase_rate NUMERIC,
  stuff_plus_pitch NUMERIC,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- League-level pitch aggregates by calendar season (aggregated from statcast_pitches).
-- AVG ignores NULLs per column so lg_avg_velo and lg_avg_spin_rate are independent.
CREATE OR REPLACE VIEW statcast_pitch_season_averages AS
SELECT
  EXTRACT(YEAR FROM game_date::date)::integer AS season,
  ROUND(AVG(release_speed)::numeric, 4)       AS lg_avg_velo,
  ROUND(AVG(release_spin_rate)::numeric, 4)   AS lg_avg_spin_rate,
  COUNT(*)                                     AS pitch_count,
  COUNT(release_speed)                         AS velo_count,
  COUNT(release_spin_rate)                     AS spin_count
FROM statcast_pitches
WHERE game_date IS NOT NULL
GROUP BY 1
ORDER BY season;

-- Game logs table
CREATE TABLE game_logs (
  id BIGSERIAL PRIMARY KEY,
  game_pk BIGINT UNIQUE,
  game_date DATE,
  home_team TEXT,
  home_team_id BIGINT,
  away_team TEXT,
  away_team_id BIGINT,
  home_score INTEGER,
  away_score INTEGER,
  home_hits INTEGER,
  home_hr INTEGER,
  home_bb INTEGER,
  home_so INTEGER,
  home_singles INTEGER,
  home_doubles INTEGER,
  home_triples INTEGER,
  away_hits INTEGER,
  away_hr INTEGER,
  away_bb INTEGER,
  away_so INTEGER,
  away_singles INTEGER,
  away_doubles INTEGER,
  away_triples INTEGER,
  status TEXT,
  venue TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Existing databases: nullable counting stats per side. Older installs may have used
-- ``home_home_runs`` / ``home_walks`` / ``home_strikeouts`` (and away analogs); run
-- ``supabase/migrations/20260512120000_game_logs_rename_box_score_columns.sql`` to rename
-- to ``home_hr`` / ``home_bb`` / ``home_so`` (and away analogs) and ``DROP`` any leftover legacy names.
```sql
ALTER TABLE public.game_logs
  ADD COLUMN IF NOT EXISTS home_hits INTEGER,
  ADD COLUMN IF NOT EXISTS home_hr INTEGER,
  ADD COLUMN IF NOT EXISTS home_bb INTEGER,
  ADD COLUMN IF NOT EXISTS home_so INTEGER,
  ADD COLUMN IF NOT EXISTS home_singles INTEGER,
  ADD COLUMN IF NOT EXISTS home_doubles INTEGER,
  ADD COLUMN IF NOT EXISTS home_triples INTEGER,
  ADD COLUMN IF NOT EXISTS away_hits INTEGER,
  ADD COLUMN IF NOT EXISTS away_hr INTEGER,
  ADD COLUMN IF NOT EXISTS away_bb INTEGER,
  ADD COLUMN IF NOT EXISTS away_so INTEGER,
  ADD COLUMN IF NOT EXISTS away_singles INTEGER,
  ADD COLUMN IF NOT EXISTS away_doubles INTEGER,
  ADD COLUMN IF NOT EXISTS away_triples INTEGER;
```

-- Social posts log table
CREATE TABLE social_posts (
  id BIGSERIAL PRIMARY KEY,
  platform TEXT NOT NULL,
  content TEXT,
  stat_type TEXT,
  player_id BIGINT,
  posted_at TIMESTAMPTZ DEFAULT NOW(),
  status TEXT DEFAULT 'pending',
  external_post_id TEXT
);

-- ==============================================
-- Historical stats (player / team season totals)
-- player_id / team_id: MLBAM-aligned soft references (no FK required).
-- ==============================================

CREATE TABLE player_batting_seasons (
  id BIGSERIAL PRIMARY KEY,
  player_id BIGINT NOT NULL,
  player_name TEXT,
  season INTEGER NOT NULL,
  team_id BIGINT,
  team TEXT,
  league TEXT,
  g INTEGER,
  ab INTEGER,
  pa INTEGER,
  r INTEGER,
  h INTEGER,
  doubles INTEGER,
  triples INTEGER,
  hr INTEGER,
  rbi INTEGER,
  sb INTEGER,
  cs INTEGER,
  bb INTEGER,
  so INTEGER,
  hbp INTEGER,
  avg NUMERIC(5,3),
  obp NUMERIC(5,3),
  slg NUMERIC(5,3),
  ops NUMERIC(5,3),
  babip NUMERIC(5,3),
  iso NUMERIC(5,3),
  bb_pct NUMERIC(5,1),
  k_pct NUMERIC(5,1),
  ops_plus INTEGER,
  woba NUMERIC(5,3),
  wrc_plus INTEGER,
  war NUMERIC(5,1),
  cqi NUMERIC(6,1),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Per-position batting performance (counting stats and rate metrics split by defensive ``position``).
-- Complements aggregate season lines in ``player_batting_seasons``; unlike ``player_fielding_seasons``,
-- rows here are batting-focused. ``player_id`` / ``team_id``: MLBAM-aligned soft references (no FK).
-- Note: with a unique index on ``(player_id, season, team_id, position)``, PostgreSQL treats
-- multiple NULL ``team_id`` values as distinct—avoid duplicate rows for ``team_id`` IS NULL if used.
CREATE TABLE player_position_seasons (
  id BIGSERIAL PRIMARY KEY,
  player_id BIGINT NOT NULL,
  player_name TEXT,
  season INTEGER NOT NULL,
  team_id BIGINT,
  team TEXT,
  position TEXT NOT NULL,
  g INTEGER,
  pa INTEGER,
  ab INTEGER,
  h INTEGER,
  doubles INTEGER,
  triples INTEGER,
  hr INTEGER,
  bb INTEGER,
  so INTEGER,
  hbp INTEGER,
  avg NUMERIC(5,3),
  obp NUMERIC(5,3),
  slg NUMERIC(5,3),
  ops NUMERIC(5,3),
  woba NUMERIC(5,3),
  ops_plus INTEGER,
  wrc_plus INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE player_pitching_seasons (
  id BIGSERIAL PRIMARY KEY,
  player_id BIGINT NOT NULL,
  player_name TEXT,
  season INTEGER NOT NULL,
  team_id BIGINT,
  team TEXT,
  league TEXT,
  w INTEGER,
  l INTEGER,
  era NUMERIC(5,2),
  g INTEGER,
  gs INTEGER,
  cg INTEGER,
  sho INTEGER,
  sv INTEGER,
  ip NUMERIC(6,1),
  h INTEGER,
  r INTEGER,
  er INTEGER,
  hr INTEGER,
  bb INTEGER,
  so INTEGER,
  whip NUMERIC(5,3),
  fip NUMERIC(5,2),
  xfip NUMERIC(5,2),
  k_per_9 NUMERIC(5,2),
  bb_per_9 NUMERIC(5,2),
  hr_per_9 NUMERIC(5,2),
  k_bb NUMERIC(5,2),
  era_plus INTEGER,
  war NUMERIC(5,1),
  lob_pct NUMERIC(5,1),
  stuff_plus NUMERIC(6,1),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE player_fielding_seasons (
  id BIGSERIAL PRIMARY KEY,
  player_id BIGINT NOT NULL,
  player_name TEXT,
  season INTEGER NOT NULL,
  team_id BIGINT,
  team TEXT,
  position TEXT,
  g INTEGER,
  gs INTEGER,
  inn NUMERIC(7,1),
  po INTEGER,
  a INTEGER,
  e INTEGER,
  dp INTEGER,
  fld_pct NUMERIC(5,3),
  rf_per_9 NUMERIC(5,2),
  rf_per_g NUMERIC(5,2),
  drs INTEGER,
  oaa INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE team_batting_seasons (
  id BIGSERIAL PRIMARY KEY,
  team_id BIGINT NOT NULL,
  team TEXT,
  season INTEGER NOT NULL,
  league TEXT,
  division TEXT,
  g INTEGER,
  ab INTEGER,
  pa INTEGER,
  r INTEGER,
  h INTEGER,
  doubles INTEGER,
  triples INTEGER,
  hr INTEGER,
  rbi INTEGER,
  sb INTEGER,
  cs INTEGER,
  bb INTEGER,
  so INTEGER,
  avg NUMERIC(5,3),
  obp NUMERIC(5,3),
  slg NUMERIC(5,3),
  ops NUMERIC(5,3),
  babip NUMERIC(5,3),
  iso NUMERIC(5,3),
  woba NUMERIC(5,3),
  ops_plus INTEGER,
  wrc_plus INTEGER,
  war NUMERIC(5,1),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE team_pitching_seasons (
  id BIGSERIAL PRIMARY KEY,
  team_id BIGINT NOT NULL,
  team TEXT,
  season INTEGER NOT NULL,
  league TEXT,
  division TEXT,
  w INTEGER,
  l INTEGER,
  era NUMERIC(5,2),
  g INTEGER,
  gs INTEGER,
  cg INTEGER,
  sho INTEGER,
  sv INTEGER,
  ip NUMERIC(6,1),
  h INTEGER,
  r INTEGER,
  er INTEGER,
  hr INTEGER,
  bb INTEGER,
  so INTEGER,
  whip NUMERIC(5,3),
  fip NUMERIC(5,2),
  k_per_9 NUMERIC(5,2),
  bb_per_9 NUMERIC(5,2),
  hr_per_9 NUMERIC(5,2),
  era_plus INTEGER,
  war NUMERIC(5,1),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE team_fielding_seasons (
  id BIGSERIAL PRIMARY KEY,
  team_id BIGINT NOT NULL,
  team TEXT,
  season INTEGER NOT NULL,
  league TEXT,
  g INTEGER,
  po INTEGER,
  a INTEGER,
  e INTEGER,
  dp INTEGER,
  fld_pct NUMERIC(5,3),
  drs INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Park factors by franchise and season (``team_id``: MLBAM id, soft reference to ``teams.id``).
-- ``runs_factor`` (formerly ``park_factor``) and component factors scale are left to the ETL / app
-- (e.g. FanGraphs-style index ÷100 vs 1.0 neutral multiplier). See migration
-- ``supabase/migrations/20260513120000_park_factors_runs_factor_and_components.sql``.
CREATE TABLE park_factors (
  id BIGSERIAL PRIMARY KEY,
  team_id BIGINT NOT NULL,
  team TEXT,
  season INTEGER NOT NULL,
  runs_factor NUMERIC(6,3),
  hr_factor NUMERIC(6,3),
  hits_factor NUMERIC(6,3),
  singles_factor NUMERIC(6,3),
  doubles_factor NUMERIC(6,3),
  triples_factor NUMERIC(6,3),
  bb_factor NUMERIC(6,3),
  so_factor NUMERIC(6,3),
  home_games INTEGER,
  away_games INTEGER,
  home_rs INTEGER,
  home_ra INTEGER,
  away_rs INTEGER,
  away_ra INTEGER,
  seasons_used INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Existing databases with ``park_factor``: run
-- ``supabase/migrations/20260513120000_park_factors_runs_factor_and_components.sql`` (idempotent).
```sql
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'park_factors'
      AND column_name = 'park_factor'
  )
  AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'park_factors'
      AND column_name = 'runs_factor'
  ) THEN
    ALTER TABLE public.park_factors RENAME COLUMN park_factor TO runs_factor;
  END IF;
END $$;

ALTER TABLE public.park_factors
  ADD COLUMN IF NOT EXISTS hr_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS hits_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS singles_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS doubles_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS triples_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS bb_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS so_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
```

CREATE UNIQUE INDEX player_batting_seasons_player_season_team
  ON player_batting_seasons (player_id, season, team_id);
CREATE UNIQUE INDEX player_position_seasons_player_season_team_pos
  ON player_position_seasons (player_id, season, team_id, position);
CREATE UNIQUE INDEX player_pitching_seasons_player_season_team
  ON player_pitching_seasons (player_id, season, team_id);
CREATE UNIQUE INDEX player_fielding_seasons_player_season_team_pos
  ON player_fielding_seasons (player_id, season, team_id, position);
CREATE UNIQUE INDEX team_batting_seasons_team_season
  ON team_batting_seasons (team_id, season);
CREATE UNIQUE INDEX team_pitching_seasons_team_season
  ON team_pitching_seasons (team_id, season);
CREATE UNIQUE INDEX team_fielding_seasons_team_season
  ON team_fielding_seasons (team_id, season);
CREATE UNIQUE INDEX park_factors_team_season
  ON park_factors (team_id, season);

CREATE INDEX idx_player_batting_player_id ON player_batting_seasons(player_id);
CREATE INDEX idx_player_batting_season ON player_batting_seasons(season);
CREATE INDEX idx_player_position_player_id ON player_position_seasons(player_id);
CREATE INDEX idx_player_position_season ON player_position_seasons(season);
CREATE INDEX idx_player_pitching_player_id ON player_pitching_seasons(player_id);
CREATE INDEX idx_player_pitching_season ON player_pitching_seasons(season);
CREATE INDEX idx_player_fielding_player_id ON player_fielding_seasons(player_id);
CREATE INDEX idx_team_batting_team_id ON team_batting_seasons(team_id);
CREATE INDEX idx_team_pitching_team_id ON team_pitching_seasons(team_id);
CREATE INDEX idx_park_factors_team_id ON park_factors(team_id);
CREATE INDEX idx_park_factors_season ON park_factors(season);

-- ==============================================
-- Foreign Key References
-- ==============================================

ALTER TABLE statcast_batting ADD CONSTRAINT fk_statcast_batting_team
  FOREIGN KEY (team_id) REFERENCES teams(id);

-- ==============================================
-- Drop player_id FK (existing databases)
-- ==============================================
-- New installs: omit REFERENCES on player_id in CREATE TABLE above.
-- Existing Supabase DBs that still have the old FK:

```sql
ALTER TABLE public.statcast_pitches
  DROP CONSTRAINT IF EXISTS statcast_pitches_player_id_fkey;

ALTER TABLE public.statcast_batting
  DROP CONSTRAINT IF EXISTS statcast_batting_player_id_fkey;
```

-- ==============================================
-- Indexes
-- ==============================================

CREATE INDEX idx_players_team_id ON players(team_id);
CREATE INDEX idx_statcast_pitches_batter_id ON statcast_pitches(batter_id);
CREATE INDEX idx_statcast_pitches_game_date ON statcast_pitches(game_date);
CREATE UNIQUE INDEX statcast_pitches_game_atbat_pitch_key
  ON statcast_pitches (game_pk, at_bat_number, pitch_number);
CREATE INDEX idx_statcast_batting_player_id ON statcast_batting(player_id);
CREATE INDEX idx_statcast_batting_season ON statcast_batting(season);
CREATE INDEX idx_statcast_pitching_pitcher_id ON statcast_pitching(pitcher_id);
CREATE INDEX idx_statcast_pitching_season ON statcast_pitching (season);
CREATE UNIQUE INDEX idx_league_pitch_type_averages_season_pitch_type_throws
  ON league_pitch_type_averages (season, pitch_type, p_throws);
CREATE INDEX idx_league_pitch_type_averages_season
  ON league_pitch_type_averages (season);
CREATE UNIQUE INDEX idx_statcast_pitching_arsenal_pitcher_season_pitch_throws
  ON statcast_pitching_arsenal (pitcher_id, season, pitch_type, p_throws);
CREATE INDEX idx_statcast_pitching_arsenal_pitcher_id
  ON statcast_pitching_arsenal (pitcher_id);
CREATE INDEX idx_statcast_pitching_arsenal_season
  ON statcast_pitching_arsenal (season);
CREATE INDEX idx_game_logs_game_date ON game_logs(game_date);

## ``statcast_pitches`` batter and pitcher columns

- ``batter_id``: MLBAM batter id. **Not** an enforced FK to ``players.id``; treat as a **soft reference** for optional joins (e.g. ``LEFT JOIN players ON players.id = statcast_pitches.batter_id``).
- ``pitcher_id``: MLBAM pitcher id when populated (nullable). Same soft-reference semantics as ``batter_id``.
- ``batter_name`` / ``pitcher_name``: Savant display strings (nullable).

## ``statcast_batting`` ``player_id``

``player_id`` is the MLBAM batter id for Statcast batting leaderboards. It is **not** an enforced foreign key to ``players.id`` in Supabase; values may exist before a matching ``players`` row. Treat it as a **soft reference** for optional joins (e.g. ``LEFT JOIN players ON players.id = statcast_batting.player_id``).

## ``statcast_pitching`` ``pitcher_id`` and indexes

Migration (column reshape): ``supabase/migrations/20260519180000_alter_statcast_pitching_columns.sql``.

``pitcher_id`` is the MLBAM pitcher id when populated (nullable). It is **not** an enforced foreign key to ``players.id``; semantics match ``statcast_pitches.pitcher_id`` (soft reference for optional joins). One row per pitcher per season is enforced by the **unique** index ``idx_statcast_pitching_pitcher_season`` on ``(pitcher_id, season)``. Pitcher lookups use non-unique index ``idx_statcast_pitching_pitcher_id`` (same pattern as ``idx_statcast_batting_player_id`` on ``statcast_batting``). Season filtering uses non-unique index ``idx_statcast_pitching_season``.

``avg_fastball_velo`` is the average ``release_speed`` on Savant pitch types **FF**, **SI**, and **FC** only. Season-level spin and horizontal/vertical movement averages are stored per ``pitch_type`` on ``statcast_pitching_arsenal`` (with league baselines in ``league_pitch_type_averages``).

## ``league_pitch_type_averages``

Migrations: ``supabase/migrations/20260519160000_create_league_pitch_type_averages.sql`` (creates table); ``supabase/migrations/20260519210000_league_pitch_type_averages_add_p_throws.sql`` (adds ``p_throws``, new unique key, truncates for re-seed).

Reference rows per ``(season, pitch_type, p_throws)`` with league mean velo, spin, and movement (``pfx_x`` / ``pfx_z``-style horizontal and vertical), plus ``pitch_category`` and ``pitch_count``. ``p_throws`` is Savant pitcher handedness (**L** / **R** or null if unknown) so ``avg_h_movement`` is not distorted by mixing LHP and RHP (sign-cancellation across the league). **Populated by** ``pipeline/calc_league_pitch_type_averages.py``. **Consumers:** ``stuff_plus_pitch`` (and related fields) on ``statcast_pitching_arsenal`` join on matching season, pitch type, and pitcher hand. Unique index ``idx_league_pitch_type_averages_season_pitch_type_throws`` supports idempotent upserts; non-unique ``idx_league_pitch_type_averages_season`` supports season-scoped reads.

## ``statcast_pitching_arsenal``

Migrations: ``supabase/migrations/20260519170000_create_statcast_pitching_arsenal.sql`` (creates table); ``supabase/migrations/20260519220000_statcast_pitching_arsenal_add_p_throws.sql`` (adds ``p_throws``, new unique key, truncates for re-seed).

One row per ``(pitcher_id, season, pitch_type, p_throws)`` (unique index ``idx_statcast_pitching_arsenal_pitcher_season_pitch_throws``). ``pitcher_id`` is a **soft reference** to ``players.id`` (no FK), consistent with ``statcast_pitching`` and ``statcast_pitches.pitcher_id``. ``p_throws`` is Savant pitcher handedness (**L** / **R** or null), stored so each row can join **``league_pitch_type_averages``** on ``season``, ``pitch_type``, and ``p_throws`` for the correct handedness baseline when computing ``stuff_plus_pitch``. Pitch-type metrics (velo, spin, movement, whiff/chase, usage) live on the row beside ``stuff_plus_pitch``. Non-unique indexes ``idx_statcast_pitching_arsenal_pitcher_id`` and ``idx_statcast_pitching_arsenal_season`` support pitcher- and season-scoped reads.

## Players extended bio / career columns (migration)

Optional historical fields (``player_id`` alignment with MLBAM). Not required for core app flows; enrich via ETL or manual SQL as needed.

```sql
ALTER TABLE public.players ADD COLUMN IF NOT EXISTS debut_date DATE;
ALTER TABLE public.players ADD COLUMN IF NOT EXISTS final_game DATE;
ALTER TABLE public.players ADD COLUMN IF NOT EXISTS name_first TEXT;
ALTER TABLE public.players ADD COLUMN IF NOT EXISTS name_last TEXT;
ALTER TABLE public.players ADD COLUMN IF NOT EXISTS birth_city TEXT;
ALTER TABLE public.players ADD COLUMN IF NOT EXISTS birth_country TEXT;
ALTER TABLE public.players ADD COLUMN IF NOT EXISTS height TEXT;
ALTER TABLE public.players ADD COLUMN IF NOT EXISTS weight INTEGER;

ALTER TABLE public.players ALTER COLUMN active SET DEFAULT true;
```

On the app, ``GET /api/players/[id]`` returns these as ``supabasePlayer`` when a row exists (soft reference / join aid to Statcast batter ids on pitch rows and ``statcast_batting.player_id``).

## statcast_batting ``pa`` column (migration)

For databases created before ``pa`` was added, run in Supabase SQL editor:

```sql
ALTER TABLE public.statcast_batting
  ADD COLUMN IF NOT EXISTS pa INTEGER;
```

- ``pa`` is populated by ``pipeline/seed_statcast_batting.py``: primary weight from Savant exit-velo / barrels **attempts**, fallback to expected-stats **pa**.

## statcast_batting ``cqi`` column (migration)

Contact Quality Index (100 = league average). For databases created before ``cqi`` was added:

```sql
ALTER TABLE public.statcast_batting
  ADD COLUMN IF NOT EXISTS cqi NUMERIC(6, 2);
```

Populate from ``calculations.batting_calcs.calc_cqi`` (exit velocity, barrel rate, hard-hit rate vs league baselines) when Statcast rows are present.

## ``upsert_statcast_batting_aggregates`` (RPC)

Migration: ``supabase/migrations/20260519140000_create_upsert_statcast_batting_aggregates_rpc.sql``.

``public.upsert_statcast_batting_aggregates(rows JSONB)`` returns ``void``. ``LANGUAGE plpgsql``, ``SECURITY DEFINER``. Pass a JSON array of objects; each element should include keys aligned with columns the RPC writes (e.g. ``player_id``, ``season``, ``pa``, ``avg_exit_velocity``, ``max_exit_velocity``, ``avg_launch_angle``, ``barrel_rate``, ``hard_hit_rate``, ``cqi``). Rows are inserted into ``statcast_batting`` or, on conflict on ``(player_id, season)`` (requires unique index ``statcast_batting_player_id_season_key``), only the aggregate fields below are updated.

**Owned by this RPC (aggregates — safe to upsert from pitch-level / derived stats):** ``pa``, ``avg_exit_velocity``, ``max_exit_velocity``, ``avg_launch_angle``, ``barrel_rate``, ``hard_hit_rate``, ``cqi``, ``updated_at``.

**Leaderboard-owned (omitted from INSERT/UPDATE — never overwritten by this RPC):** ``player_name``, ``team_id``, ``xba``, ``xslg``, ``xwoba``, ``sprint_speed``. Those stay under control of the pybaseball leaderboard seeder (``pipeline/seed_statcast_batting.py``).

## ``upsert_statcast_pitching_arsenal`` (RPC)

Migrations: ``supabase/migrations/20260519190000_create_upsert_statcast_pitching_arsenal_rpc.sql`` (initial); ``supabase/migrations/20260519220100_update_upsert_statcast_pitching_arsenal_for_p_throws.sql`` (adds ``p_throws`` to payload and conflict key, after table migration ``20260519220000_statcast_pitching_arsenal_add_p_throws.sql``).

``public.upsert_statcast_pitching_arsenal(rows JSONB)`` returns ``void``. ``LANGUAGE plpgsql``, ``SECURITY DEFINER``. Payload keys: ``pitcher_id``, ``pitcher_name``, ``season``, ``pitch_type``, ``p_throws``, ``pitch_category``, ``pitches``, ``usage_rate``, ``avg_velo``, ``avg_spin_rate``, ``avg_h_movement``, ``avg_v_movement``, ``whiff_rate``, ``chase_rate``, ``stuff_plus_pitch``. This RPC **owns all columns** on ``statcast_pitching_arsenal``. Conflict target: ``(pitcher_id, season, pitch_type, p_throws)`` (``idx_statcast_pitching_arsenal_pitcher_season_pitch_throws``). ``updated_at`` is ``NOW()`` on insert and update.

## ``upsert_statcast_pitching_aggregates`` (RPC)

Migration: ``supabase/migrations/20260519200000_create_upsert_statcast_pitching_aggregates_rpc.sql``.

``public.upsert_statcast_pitching_aggregates(rows JSONB)`` returns ``void``. ``LANGUAGE plpgsql``, ``SECURITY DEFINER``. Pass a JSON array of objects with keys for the pitcher-season rollup on ``statcast_pitching``: ``pitcher_id``, ``pitcher_name``, ``season``, ``pitches``, ``avg_fastball_velo``, ``max_velo``, ``whiff_rate``, ``chase_rate``, ``stuff_plus``. This RPC **owns all columns** on that table. On conflict on ``(pitcher_id, season)`` (unique index ``idx_statcast_pitching_pitcher_season``), every non-key field is updated from the payload. ``updated_at`` is set to ``NOW()`` on insert and update. Per-pitch-type detail remains on ``statcast_pitching_arsenal`` (via ``upsert_statcast_pitching_arsenal``).

## ``upsert_player_batting_seasons`` (RPC)

Migration: ``supabase/migrations/20260522130000_partial_upsert_player_season_rpcs.sql``.

``public.upsert_player_batting_seasons(rows JSONB)`` returns ``void``. ``LANGUAGE plpgsql``, ``SECURITY DEFINER``. Pass a JSON array of objects keyed like ``player_batting_seasons`` rows (omit fields you do not intend to overwrite). Conflict target ``(player_id, season, team_id)`` matches ``player_batting_seasons_player_season_team``. On conflict, **non-key** columns are set to ``COALESCE(EXCLUDED.col, existing.col)`` so omitted keys leave prior values (**partial upsert** — safe for scripts that patch derived metrics without resending counting stats). ``updated_at`` is ``NOW()`` on insert and update; ``created_at`` stays at the DB default / prior value on conflicts.

## ``upsert_player_pitching_seasons`` (RPC)

Migration: ``supabase/migrations/20260522130000_partial_upsert_player_season_rpcs.sql``.

``public.upsert_player_pitching_seasons(rows JSONB)`` returns ``void``. Same partial-upsert semantics as batting: omit JSON keys to preserve existing counting stats while updating derived columns. Conflict target ``(player_id, season, team_id)`` on ``player_pitching_seasons``. Payload keys align with columns on ``player_pitching_seasons`` (**``player_id`` / ``player_name``**, ``season``, ``team_id``, pitching counting columns, rate metrics, ``stuff_plus``, etc.).

-- ==============================================
-- Row Level Security
-- ==============================================

ALTER TABLE players ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE statcast_pitches ENABLE ROW LEVEL SECURITY;
ALTER TABLE statcast_batting ENABLE ROW LEVEL SECURITY;
ALTER TABLE statcast_pitching ENABLE ROW LEVEL SECURITY;
ALTER TABLE league_pitch_type_averages ENABLE ROW LEVEL SECURITY;
ALTER TABLE statcast_pitching_arsenal ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_batting_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_position_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_pitching_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_fielding_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_batting_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_pitching_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_fielding_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE park_factors ENABLE ROW LEVEL SECURITY;

-- ==============================================
-- Access Policies
-- ==============================================

CREATE POLICY "Public can read players"
  ON players FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read teams"
  ON teams FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read statcast pitches"
  ON statcast_pitches FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read statcast batting"
  ON statcast_batting FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read statcast pitching"
  ON statcast_pitching FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read league pitch type averages"
  ON league_pitch_type_averages FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read statcast pitching arsenal"
  ON statcast_pitching_arsenal FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read game logs"
  ON game_logs FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read player batting seasons"
  ON player_batting_seasons FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read player position seasons"
  ON player_position_seasons FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read player pitching seasons"
  ON player_pitching_seasons FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read player fielding seasons"
  ON player_fielding_seasons FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read team batting seasons"
  ON team_batting_seasons FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read team pitching seasons"
  ON team_pitching_seasons FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read team fielding seasons"
  ON team_fielding_seasons FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read park factors"
  ON park_factors FOR SELECT
  TO anon, authenticated
  USING (true);

-- Social posts are server-only
-- (service role key bypasses RLS automatically)

## Additional Indexes

```sql
-- Required for statcast_batting upserts on (player_id, season)
CREATE UNIQUE INDEX IF NOT EXISTS statcast_batting_player_id_season_key
  ON statcast_batting (player_id, season);

-- Required for statcast_pitching upserts on (pitcher_id, season)
CREATE UNIQUE INDEX IF NOT EXISTS idx_statcast_pitching_pitcher_season
  ON statcast_pitching (pitcher_id, season);

-- Required for league_pitch_type_averages upserts on (season, pitch_type, p_throws)
CREATE UNIQUE INDEX IF NOT EXISTS idx_league_pitch_type_averages_season_pitch_type_throws
  ON league_pitch_type_averages (season, pitch_type, p_throws);

-- Required for statcast_pitching_arsenal upserts on (pitcher_id, season, pitch_type, p_throws)
CREATE UNIQUE INDEX IF NOT EXISTS idx_statcast_pitching_arsenal_pitcher_season_pitch_throws
  ON statcast_pitching_arsenal (pitcher_id, season, pitch_type, p_throws);
```
## Real-Time Configuration

The following tables are added to the Supabase real-time publication
to enable live updates in the frontend during games:

```sql
-- Enable real-time on Statcast tables (idempotent)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime'
      AND schemaname = 'public'
      AND tablename = 'statcast_pitches'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.statcast_pitches;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime'
      AND schemaname = 'public'
      AND tablename = 'statcast_batting'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.statcast_batting;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime'
      AND schemaname = 'public'
      AND tablename = 'statcast_pitching'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.statcast_pitching;
  END IF;
END $$;
```

### Real-Time Behavior
- `statcast_pitches` — triggers the LIVE badge and toast notification 
  on the Statcast explorer page
- `statcast_batting` — triggers leaderboard refetch when aggregated 
  batting metrics are updated by the pipeline
- `statcast_pitching` — triggers refetch when aggregated pitching 
  metrics are updated by the pipeline
- The existing RLS SELECT policy on Statcast leaderboard tables covers real-time events
- The frontend uses the anon key for subscriptions

## Historical season tables (reference)

Season-level totals for players are stored in ``player_batting_seasons``, ``player_pitching_seasons``, and ``player_fielding_seasons``; **per-position batting splits** (when populated) in ``player_position_seasons``; franchise seasons in ``team_batting_seasons``, ``team_pitching_seasons``, ``team_fielding_seasons``. ``player_id`` / ``team_id`` align with MLBAM ids (soft references; no FK required). Run-environment indices live in ``park_factors`` (``team_id``, ``season``): ``runs_factor`` plus optional component factors (``hr_factor``, ``hits_factor``, etc.), with a unique index for upserts and public read RLS matching other reference tables.

Unique indexes support upserts (see DDL above). The player profile API exposes the three player tables as ``historicalBatting``, ``historicalPitching``, and ``historicalFielding`` (newest ``season`` first).