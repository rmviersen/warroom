-- Savant pitch sequence + natural key for idempotent pipeline upserts
-- (see pipeline/statcast_pipeline.py, SCHEMA.md)

ALTER TABLE public.statcast_pitches
  ADD COLUMN IF NOT EXISTS at_bat_number INTEGER;

ALTER TABLE public.statcast_pitches
  ADD COLUMN IF NOT EXISTS pitch_number INTEGER;

CREATE UNIQUE INDEX IF NOT EXISTS statcast_pitches_game_atbat_pitch_key
  ON public.statcast_pitches (game_pk, at_bat_number, pitch_number);
