-- Replace season-level spin/movement / generic avg velo with fastball-only average;
-- per-pitch-type detail lives on statcast_pitching_arsenal.
ALTER TABLE public.statcast_pitching
  DROP COLUMN IF EXISTS avg_velo,
  DROP COLUMN IF EXISTS avg_spin_rate,
  DROP COLUMN IF EXISTS avg_h_movement,
  DROP COLUMN IF EXISTS avg_v_movement;

-- Mean release_speed on FF, SI, FC pitch types only (ETL definition).
ALTER TABLE public.statcast_pitching
  ADD COLUMN IF NOT EXISTS avg_fastball_velo NUMERIC;
