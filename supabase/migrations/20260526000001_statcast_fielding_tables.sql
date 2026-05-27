-- Statcast OAA leaderboard-style fielding aggregates (per player / season / position)
-- plus catcher defensive metrics from Savant leaderboard.

CREATE TABLE public.statcast_fielding_oaa (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  player_id BIGINT NOT NULL,
  player_name TEXT,
  season INTEGER NOT NULL,
  position TEXT NOT NULL,
  team TEXT,
  fielding_runs_prevented INTEGER,
  oaa INTEGER,
  oaa_infront INTEGER,
  oaa_lateral_3b INTEGER,
  oaa_lateral_1b INTEGER,
  oaa_behind INTEGER,
  oaa_rhh INTEGER,
  oaa_lhh INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT statcast_fielding_oaa_player_id_season_position_key UNIQUE (player_id, season, position)
);

CREATE INDEX IF NOT EXISTS idx_statcast_fielding_oaa_player_id
  ON public.statcast_fielding_oaa (player_id);

CREATE INDEX IF NOT EXISTS idx_statcast_fielding_oaa_season
  ON public.statcast_fielding_oaa (season);

CREATE INDEX IF NOT EXISTS idx_statcast_fielding_oaa_season_position
  ON public.statcast_fielding_oaa (season, position);


CREATE TABLE public.statcast_catcher_defense (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  player_id BIGINT NOT NULL,
  player_name TEXT,
  season INTEGER NOT NULL,
  team_id BIGINT,
  max_eff_arm_2b_3b NUMERIC,
  exchange_2b_3b NUMERIC,
  pop_2b_sba_count INTEGER,
  pop_2b_sba NUMERIC,
  pop_2b_cs NUMERIC,
  pop_2b_sb NUMERIC,
  pop_3b_sba_count INTEGER,
  pop_3b_sba NUMERIC,
  pop_3b_cs NUMERIC,
  pop_3b_sb NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT statcast_catcher_defense_player_id_season_key UNIQUE (player_id, season)
);

CREATE INDEX IF NOT EXISTS idx_statcast_catcher_defense_player_id
  ON public.statcast_catcher_defense (player_id);

CREATE INDEX IF NOT EXISTS idx_statcast_catcher_defense_season
  ON public.statcast_catcher_defense (season);


ALTER TABLE public.statcast_fielding_oaa ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public can read statcast fielding oaa"
  ON public.statcast_fielding_oaa FOR SELECT
  TO anon, authenticated
  USING (true);


ALTER TABLE public.statcast_catcher_defense ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public can read statcast catcher defense"
  ON public.statcast_catcher_defense FOR SELECT
  TO anon, authenticated
  USING (true);
