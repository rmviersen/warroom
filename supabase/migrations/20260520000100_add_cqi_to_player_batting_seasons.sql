ALTER TABLE public.player_batting_seasons
  ADD COLUMN IF NOT EXISTS cqi NUMERIC(6,1);

COMMENT ON COLUMN public.player_batting_seasons.cqi IS 
  'Contact Quality Index — WARroom custom batting metric, 100 = league average';
