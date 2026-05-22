CREATE TABLE IF NOT EXISTS public.statcast_pitching_arsenal (
  id BIGSERIAL PRIMARY KEY,
  pitcher_id BIGINT NOT NULL,
  pitcher_name TEXT,
  season INTEGER NOT NULL,
  pitch_type TEXT NOT NULL,
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_statcast_pitching_arsenal_pitcher_season_pitch
  ON public.statcast_pitching_arsenal (pitcher_id, season, pitch_type);

CREATE INDEX IF NOT EXISTS idx_statcast_pitching_arsenal_pitcher_id
  ON public.statcast_pitching_arsenal (pitcher_id);

CREATE INDEX IF NOT EXISTS idx_statcast_pitching_arsenal_season
  ON public.statcast_pitching_arsenal (season);

ALTER TABLE public.statcast_pitching_arsenal ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public can read statcast pitching arsenal"
  ON public.statcast_pitching_arsenal FOR SELECT
  TO anon, authenticated
  USING (true);
