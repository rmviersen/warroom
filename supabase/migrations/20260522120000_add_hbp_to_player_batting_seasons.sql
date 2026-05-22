ALTER TABLE public.player_batting_seasons
  ADD COLUMN IF NOT EXISTS hbp INTEGER;

COMMENT ON COLUMN public.player_batting_seasons.hbp IS
  'Hit by pitch — used in wOBA calculation';
