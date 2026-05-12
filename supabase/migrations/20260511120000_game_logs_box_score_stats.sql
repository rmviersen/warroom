-- Nullable per-game box score counting stats for home and away teams.
-- Safe for existing rows: all columns are NULL unless backfilled.
-- Short names (hr / bb / so) match enrich_game_logs.py payloads.

ALTER TABLE public.game_logs
  ADD COLUMN IF NOT EXISTS home_hits INTEGER,
  ADD COLUMN IF NOT EXISTS home_hr INTEGER,
  ADD COLUMN IF NOT EXISTS home_bb INTEGER,
  ADD COLUMN IF NOT EXISTS home_so INTEGER,
  ADD COLUMN IF NOT EXISTS home_singles INTEGER,
  ADD COLUMN IF NOT EXISTS home_doubles INTEGER,
  ADD COLUMN IF NOT EXISTS home_triples INTEGER,
  ADD COLUMN IF NOT EXISTS away_hits INTEGER,
  ADD COLUMN IF NOT EXISTS away_hr INTEGER,
  ADD COLUMN IF NOT EXISTS away_bb INTEGER,
  ADD COLUMN IF NOT EXISTS away_so INTEGER,
  ADD COLUMN IF NOT EXISTS away_singles INTEGER,
  ADD COLUMN IF NOT EXISTS away_doubles INTEGER,
  ADD COLUMN IF NOT EXISTS away_triples INTEGER;
