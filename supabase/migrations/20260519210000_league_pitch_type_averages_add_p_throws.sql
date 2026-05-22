-- Split league baselines by pitcher handedness (``p_throws``) so horizontal movement
-- is not averaged across LHP/RHP sign cancellation. Existing rows pre-date this split;
-- ``TRUNCATE`` clears them for a full re-run of ``calc_league_pitch_type_averages.py``.
ALTER TABLE public.league_pitch_type_averages
  ADD COLUMN IF NOT EXISTS p_throws TEXT;

DROP INDEX IF EXISTS public.idx_league_pitch_type_averages_season_pitch_type;

CREATE UNIQUE INDEX IF NOT EXISTS idx_league_pitch_type_averages_season_pitch_type_throws
  ON public.league_pitch_type_averages (season, pitch_type, p_throws);

TRUNCATE TABLE public.league_pitch_type_averages;
