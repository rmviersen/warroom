CREATE TABLE IF NOT EXISTS public.league_pitch_type_averages (
  id BIGSERIAL PRIMARY KEY,
  season INTEGER NOT NULL,
  pitch_type TEXT NOT NULL,
  pitch_category TEXT NOT NULL,
  pitch_count INTEGER,
  avg_velo NUMERIC,
  avg_spin_rate NUMERIC,
  avg_h_movement NUMERIC,
  avg_v_movement NUMERIC,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_league_pitch_type_averages_season_pitch_type
  ON public.league_pitch_type_averages (season, pitch_type);

CREATE INDEX IF NOT EXISTS idx_league_pitch_type_averages_season
  ON public.league_pitch_type_averages (season);

ALTER TABLE public.league_pitch_type_averages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public can read league pitch type averages"
  ON public.league_pitch_type_averages FOR SELECT
  TO anon, authenticated
  USING (true);
