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
CREATE TABLE statcast_pitches (
  id BIGSERIAL PRIMARY KEY,
  player_id BIGINT REFERENCES players(id),
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

-- Statcast batting leaderboard table
CREATE TABLE statcast_batting (
  id BIGSERIAL PRIMARY KEY,
  player_id BIGINT REFERENCES players(id),
  player_name TEXT,
  team_id BIGINT,
  season INTEGER,
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
-- Indexes
-- ==============================================

CREATE INDEX idx_players_team_id ON players(team_id);
CREATE INDEX idx_statcast_pitches_player_id ON statcast_pitches(player_id);
CREATE INDEX idx_statcast_pitches_game_date ON statcast_pitches(game_date);
CREATE INDEX idx_statcast_batting_player_id ON statcast_batting(player_id);
CREATE INDEX idx_statcast_batting_season ON statcast_batting(season);
CREATE INDEX idx_game_logs_game_date ON game_logs(game_date);

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