-- Contact Quality Index on Statcast batting leaderboard (see SCHEMA.md, batting_calcs.calc_cqi)
ALTER TABLE public.statcast_batting
  ADD COLUMN IF NOT EXISTS cqi NUMERIC(6, 2);
