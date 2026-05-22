-- Batter vs pitcher column names on statcast_pitches
-- (see SCHEMA.md)
--
-- Unique index statcast_pitches_game_atbat_pitch_key (game_pk, at_bat_number, pitch_number) is unchanged.

ALTER TABLE public.statcast_pitches
  RENAME COLUMN player_id TO batter_id;

ALTER TABLE public.statcast_pitches
  RENAME COLUMN player_name TO pitcher_name;

ALTER TABLE public.statcast_pitches
  ADD COLUMN IF NOT EXISTS pitcher_id BIGINT,
  ADD COLUMN IF NOT EXISTS batter_name TEXT;

ALTER INDEX public.idx_statcast_pitches_player_id RENAME TO idx_statcast_pitches_batter_id;
