-- Drop team_position_wpr_ranked: CASE WHEN + RANK() inside a view caused
-- PostgREST to return empty results via the anon key. Rankings are now
-- computed in the API handler (teams/[id]/position-wpr/route.ts) instead,
-- fetching all teams' data from team_position_wpr_season and ranking in
-- TypeScript. Avoids window-function-in-view compatibility issues entirely.

DROP VIEW IF EXISTS public.team_position_wpr_ranked;
