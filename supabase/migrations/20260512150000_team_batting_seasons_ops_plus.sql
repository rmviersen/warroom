-- OPS+ at team level (see pipeline/seed_team_batting_seasons.py, batting_calcs.calc_ops_plus)
ALTER TABLE team_batting_seasons
  ADD COLUMN IF NOT EXISTS ops_plus INTEGER;
