-- Innings-weighted WPR by position for each team-season.
--
-- For position players (C, 1B, 2B, 3B, SS, LF, CF, RF, OF):
--   Each player's bwpr/fwpr/brwpr/wpr is allocated across positions in
--   proportion to their innings at each position (player_fielding_seasons.inn).
--   Example: a player with bWPR=3.0 who splits evenly between SS and 2B
--   contributes 1.5 to SS and 1.5 to 2B.
--
-- For pitchers (position = 'P'):
--   pwpr is summed from player_pitching_seasons for the team-season.
--   P slot carries null for bwpr/fwpr/brwpr/wpr.
--
-- Positions DH, PH, PR are excluded — they are not defensive field slots.
--
-- Traded-player note: the join is on (player_id, season, team_id) so
-- per-team splits in both tables are matched correctly.

CREATE OR REPLACE VIEW public.team_position_wpr_season AS

WITH

-- Total innings per player-season-team (denominator for share calc)
player_inn_totals AS (
  SELECT
    player_id,
    season,
    team_id,
    SUM(inn) AS total_inn
  FROM public.player_fielding_seasons
  WHERE inn     IS NOT NULL
    AND inn     >  0
    AND team_id IS NOT NULL
  GROUP BY player_id, season, team_id
),

-- Innings share per player at each fielding position (pitchers + DH excluded)
position_shares AS (
  SELECT
    f.player_id,
    f.season,
    f.team_id,
    f.position,
    f.inn,
    f.inn / NULLIF(t.total_inn, 0) AS share
  FROM public.player_fielding_seasons f
  JOIN player_inn_totals t
    ON  f.player_id = t.player_id
    AND f.season    = t.season
    AND f.team_id   = t.team_id
  WHERE f.inn     IS NOT NULL
    AND f.inn     >  0
    AND f.team_id IS NOT NULL
    AND f.position NOT IN ('P', 'DH', 'PH', 'PR')
),

-- Weighted WPR summed by team-season-position for position players
position_player_wpr AS (
  SELECT
    ps.team_id,
    ps.season,
    ps.position,
    ROUND(SUM(ps.share * COALESCE(b.bwpr,  0))::numeric, 1) AS bwpr,
    ROUND(SUM(ps.share * COALESCE(b.fwpr,  0))::numeric, 1) AS fwpr,
    ROUND(SUM(ps.share * COALESCE(b.brwpr, 0))::numeric, 1) AS brwpr,
    ROUND(SUM(ps.share * COALESCE(b.wpr,   0))::numeric, 1) AS wpr,
    NULL::numeric                                             AS pwpr,
    COUNT(DISTINCT ps.player_id)                             AS player_count
  FROM position_shares ps
  LEFT JOIN public.player_batting_seasons b
    ON  ps.player_id = b.player_id
    AND ps.season    = b.season
    AND ps.team_id   = b.team_id
  GROUP BY ps.team_id, ps.season, ps.position
),

-- Pitcher WPR summed to the P slot
pitcher_wpr AS (
  SELECT
    p.team_id,
    p.season,
    'P'           AS position,
    NULL::numeric AS bwpr,
    NULL::numeric AS fwpr,
    NULL::numeric AS brwpr,
    NULL::numeric AS wpr,
    ROUND(SUM(COALESCE(p.pwpr, 0))::numeric, 1) AS pwpr,
    COUNT(DISTINCT p.player_id)                  AS player_count
  FROM public.player_pitching_seasons p
  WHERE p.pwpr    IS NOT NULL
    AND p.team_id IS NOT NULL
  GROUP BY p.team_id, p.season
)

SELECT team_id, season, position, bwpr, fwpr, brwpr, wpr, pwpr, player_count
FROM position_player_wpr
UNION ALL
SELECT team_id, season, position, bwpr, fwpr, brwpr, wpr, pwpr, player_count
FROM pitcher_wpr;

GRANT SELECT ON public.team_position_wpr_season TO anon, authenticated;
