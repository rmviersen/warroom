-- Per-position batting splits (MLBAM player_id / team_id; soft references).
-- Documented in SCHEMA.md.

CREATE TABLE IF NOT EXISTS public.player_position_seasons (
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

CREATE UNIQUE INDEX IF NOT EXISTS player_position_seasons_player_season_team_pos
  ON public.player_position_seasons (player_id, season, team_id, position);

CREATE INDEX IF NOT EXISTS idx_player_position_player_id
  ON public.player_position_seasons (player_id);
CREATE INDEX IF NOT EXISTS idx_player_position_season
  ON public.player_position_seasons (season);

ALTER TABLE public.player_position_seasons ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public can read player position seasons" ON public.player_position_seasons;
CREATE POLICY "Public can read player position seasons"
  ON public.player_position_seasons FOR SELECT
  TO anon, authenticated
  USING (true);
