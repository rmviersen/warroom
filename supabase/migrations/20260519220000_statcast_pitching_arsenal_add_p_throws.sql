-- Store pitcher handedness on each arsenal row; align grain with ``league_pitch_type_averages``
-- for ``stuff_plus_pitch`` baselines. Old rows (no ``p_throws``) are dropped — re-run
-- ``aggregate_statcast_pitching.py`` after migration ``20260519220100`` updates the upsert RPC.
ALTER TABLE public.statcast_pitching_arsenal
  ADD COLUMN IF NOT EXISTS p_throws TEXT;

DROP INDEX IF EXISTS public.idx_statcast_pitching_arsenal_pitcher_season_pitch;

CREATE UNIQUE INDEX IF NOT EXISTS idx_statcast_pitching_arsenal_pitcher_season_pitch_throws
  ON public.statcast_pitching_arsenal (pitcher_id, season, pitch_type, p_throws);

TRUNCATE TABLE public.statcast_pitching_arsenal;
