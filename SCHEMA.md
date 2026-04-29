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