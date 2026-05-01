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
-- player_id: MLBAM id; soft reference to players.id (no FK). Use for joins when a players row exists.
CREATE TABLE statcast_pitches (
  id BIGSERIAL PRIMARY KEY,
  player_id BIGINT,
  player_name TEXT,
  team_id BIGINT,
  game_date DATE,
  game_pk BIGINT,
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
-- player_id: soft reference to players.id (no FK), same as statcast_pitches
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
  status TEXT,
  venue TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

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

CREATE UNIQUE INDEX player_batting_seasons_player_season_team
  ON player_batting_seasons (player_id, season, team_id);
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

CREATE INDEX idx_player_batting_player_id ON player_batting_seasons(player_id);
CREATE INDEX idx_player_batting_season ON player_batting_seasons(season);
CREATE INDEX idx_player_pitching_player_id ON player_pitching_seasons(player_id);
CREATE INDEX idx_player_pitching_season ON player_pitching_seasons(season);
CREATE INDEX idx_player_fielding_player_id ON player_fielding_seasons(player_id);
CREATE INDEX idx_team_batting_team_id ON team_batting_seasons(team_id);
CREATE INDEX idx_team_pitching_team_id ON team_pitching_seasons(team_id);

-- ==============================================
-- Foreign Key References
-- ==============================================

ALTER TABLE statcast_pitches ADD CONSTRAINT fk_statcast_pitches_team
  FOREIGN KEY (team_id) REFERENCES teams(id);

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
CREATE INDEX idx_statcast_pitches_player_id ON statcast_pitches(player_id);
CREATE INDEX idx_statcast_pitches_game_date ON statcast_pitches(game_date);
CREATE INDEX idx_statcast_batting_player_id ON statcast_batting(player_id);
CREATE INDEX idx_statcast_batting_season ON statcast_batting(season);
CREATE INDEX idx_game_logs_game_date ON game_logs(game_date);

## ``statcast_pitches`` / ``statcast_batting`` ``player_id``

``player_id`` is the MLBAM batter id. It is **not** an enforced foreign key to ``players.id`` in Supabase; values may exist before a matching ``players`` row. Treat it as a **soft reference** for optional joins (e.g. ``LEFT JOIN players ON players.id = statcast_pitches.player_id``).

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

On the app, ``GET /api/players/[id]`` returns these as ``supabasePlayer`` when a row exists (soft reference / join aid to Statcast ``player_id``).

## statcast_batting ``pa`` column (migration)

For databases created before ``pa`` was added, run in Supabase SQL editor:

```sql
ALTER TABLE public.statcast_batting
  ADD COLUMN IF NOT EXISTS pa INTEGER;
```

- ``pa`` is populated by ``pipeline/seed_statcast_batting.py``: primary weight from Savant exit-velo / barrels **attempts**, fallback to expected-stats **pa**.

-- ==============================================
-- Row Level Security
-- ==============================================

ALTER TABLE players ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE statcast_pitches ENABLE ROW LEVEL SECURITY;
ALTER TABLE statcast_batting ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_batting_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_pitching_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_fielding_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_batting_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_pitching_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_fielding_seasons ENABLE ROW LEVEL SECURITY;

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

CREATE POLICY "Public can read game logs"
  ON game_logs FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Public can read player batting seasons"
  ON player_batting_seasons FOR SELECT
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

-- Social posts are server-only
-- (service role key bypasses RLS automatically)

## Additional Indexes

```sql
-- Required for statcast_batting upserts on (player_id, season)
CREATE UNIQUE INDEX IF NOT EXISTS statcast_batting_player_id_season_key
  ON statcast_batting (player_id, season);
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
END $$;
```

### Real-Time Behavior
- `statcast_pitches` — triggers the LIVE badge and toast notification 
  on the Statcast explorer page
- `statcast_batting` — triggers leaderboard refetch when aggregated 
  batting metrics are updated by the pipeline
- The existing RLS SELECT policy on both tables covers real-time events
- The frontend uses the anon key for subscriptions

## Historical season tables (reference)

Season-level totals for players are stored in ``player_batting_seasons``, ``player_pitching_seasons``, and ``player_fielding_seasons``; franchise seasons in ``team_batting_seasons``, ``team_pitching_seasons``, ``team_fielding_seasons``. ``player_id`` / ``team_id`` align with MLBAM ids (soft references; no FK required).

Unique indexes support upserts (see DDL above). The player profile API exposes the three player tables as ``historicalBatting``, ``historicalPitching``, and ``historicalFielding`` (newest ``season`` first).