CREATE TABLE IF NOT EXISTS public.statcast_pitching (
  id BIGSERIAL PRIMARY KEY,
  pitcher_id BIGINT,
  pitcher_name TEXT,
  season INTEGER,
  pitches INTEGER,
  avg_velo NUMERIC,
  max_velo NUMERIC,
  avg_spin_rate NUMERIC,
  avg_h_movement NUMERIC,
  avg_v_movement NUMERIC,
  whiff_rate NUMERIC,
  chase_rate NUMERIC,
  stuff_plus NUMERIC,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_statcast_pitching_pitcher_season
  ON public.statcast_pitching (pitcher_id, season);

CREATE INDEX IF NOT EXISTS idx_statcast_pitching_season
  ON public.statcast_pitching (season);
