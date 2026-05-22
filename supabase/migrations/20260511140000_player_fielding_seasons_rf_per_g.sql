-- Range factor per game (see pipeline/seed_player_fielding_seasons.py, fielding_calcs.calc_rf_per_g)
ALTER TABLE player_fielding_seasons
  ADD COLUMN IF NOT EXISTS rf_per_g NUMERIC(5, 2);
