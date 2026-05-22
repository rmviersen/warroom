ALTER TABLE public.player_pitching_seasons
  ADD COLUMN IF NOT EXISTS stuff_plus NUMERIC(6,1);

COMMENT ON COLUMN public.player_pitching_seasons.stuff_plus IS 
  'Stuff+ Score — WARroom custom pitching metric, 100 = league average';
