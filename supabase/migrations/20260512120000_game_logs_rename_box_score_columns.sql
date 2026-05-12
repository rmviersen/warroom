-- Align game_logs box-score column names with enrich_game_logs.py (home_hr, home_bb, home_so, etc.).
-- Idempotent: skips each RENAME if the old column is already gone (e.g. already migrated).

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'game_logs' AND column_name = 'home_home_runs'
  ) THEN
    ALTER TABLE public.game_logs RENAME COLUMN home_home_runs TO home_hr;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'game_logs' AND column_name = 'home_walks'
  ) THEN
    ALTER TABLE public.game_logs RENAME COLUMN home_walks TO home_bb;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'game_logs' AND column_name = 'home_strikeouts'
  ) THEN
    ALTER TABLE public.game_logs RENAME COLUMN home_strikeouts TO home_so;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'game_logs' AND column_name = 'away_home_runs'
  ) THEN
    ALTER TABLE public.game_logs RENAME COLUMN away_home_runs TO away_hr;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'game_logs' AND column_name = 'away_walks'
  ) THEN
    ALTER TABLE public.game_logs RENAME COLUMN away_walks TO away_bb;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'game_logs' AND column_name = 'away_strikeouts'
  ) THEN
    ALTER TABLE public.game_logs RENAME COLUMN away_strikeouts TO away_so;
  END IF;
END $$;

-- Remove legacy names if they still exist (no-op after a successful RENAME above).
ALTER TABLE public.game_logs DROP COLUMN IF EXISTS home_home_runs;
ALTER TABLE public.game_logs DROP COLUMN IF EXISTS home_walks;
ALTER TABLE public.game_logs DROP COLUMN IF EXISTS home_strikeouts;
ALTER TABLE public.game_logs DROP COLUMN IF EXISTS away_home_runs;
ALTER TABLE public.game_logs DROP COLUMN IF EXISTS away_walks;
ALTER TABLE public.game_logs DROP COLUMN IF EXISTS away_strikeouts;
