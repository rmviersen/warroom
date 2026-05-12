-- park_factors: rename legacy runs index column and add component factors + updated_at.
-- Idempotent: safe to run repeatedly in the Supabase SQL editor.

-- Rename park_factor -> runs_factor when the old name still exists.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'park_factors'
      AND column_name = 'park_factor'
  )
  AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'park_factors'
      AND column_name = 'runs_factor'
  ) THEN
    ALTER TABLE public.park_factors RENAME COLUMN park_factor TO runs_factor;
  END IF;
END $$;

-- New nullable component factors (NUMERIC(6,3)) and timestamp.
ALTER TABLE public.park_factors
  ADD COLUMN IF NOT EXISTS hr_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS hits_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS singles_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS doubles_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS triples_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS bb_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS so_factor NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
