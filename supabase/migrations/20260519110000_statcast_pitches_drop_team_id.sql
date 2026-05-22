-- statcast_pitches team_id retired; roster context uses home_team/away_team text on the row.

ALTER TABLE public.statcast_pitches
  DROP CONSTRAINT IF EXISTS fk_statcast_pitches_team;

ALTER TABLE public.statcast_pitches
  DROP CONSTRAINT IF EXISTS statcast_pitches_team_id_fkey;

ALTER TABLE public.statcast_pitches
  DROP COLUMN IF EXISTS team_id;
