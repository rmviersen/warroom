-- Create a unified Total WPR view across all player types.
--
-- player_batting_seasons carries wpr  = bwpr + fwpr + brwpr (position players).
-- player_pitching_seasons carries pwpr (pitchers).
-- A FULL OUTER JOIN covers every player-season with at least one WPR component:
--   • Pure batters:   total_wpr = wpr
--   • Pure pitchers:  total_wpr = pwpr
--   • Two-way players (e.g. Ohtani): total_wpr = wpr + pwpr
--
-- Idempotent: CREATE OR REPLACE VIEW.
-- GRANT SELECT to anon/authenticated so PostgREST exposes this via the anon key.

CREATE OR REPLACE VIEW public.player_season_wpr_totals AS
SELECT
  COALESCE(b.player_id,   p.player_id)   AS player_id,
  COALESCE(b.player_name, p.player_name) AS player_name,
  COALESCE(b.season,      p.season)      AS season,
  COALESCE(b.team_id,     p.team_id)     AS team_id,
  COALESCE(b.team,        p.team)        AS team,
  b.bwpr,
  b.fwpr,
  b.brwpr,
  b.wpr,
  p.pwpr,
  ROUND(
    (COALESCE(b.wpr, 0.0) + COALESCE(p.pwpr, 0.0))::numeric,
    1
  ) AS total_wpr
FROM public.player_batting_seasons  b
FULL OUTER JOIN public.player_pitching_seasons p
  ON  b.player_id = p.player_id
 AND  b.season    = p.season
WHERE b.wpr  IS NOT NULL
   OR p.pwpr IS NOT NULL;

GRANT SELECT ON public.player_season_wpr_totals TO anon, authenticated;
