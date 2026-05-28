-- Per-player WPR attribution by position for each team-season.
--
-- Companion to team_position_wpr_season: where that view gives aggregated totals,
-- this view gives the individual rows that sum to those totals.
--
-- For position players:
--   inn_share = player's innings at this position / their total innings (all positions)
--   *_attr    = player's season *wpr × inn_share  (their fractional WPR at this slot)
--   inn       = raw innings at this position
--
-- For pitchers (position = 'P'):
--   inn       = IP for the season (semantically equivalent to "innings")
--   inn_share = their IP / team total IP  (share of team pitching load)
--   pwpr_attr = their pwpr (already their individual season contribution — no weighting)
--   bwpr/fwpr/brwpr/wpr attr = null

CREATE OR REPLACE VIEW public.team_position_wpr_players_season AS

WITH

-- Total innings per player-season-team (for share denominator)
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

-- Innings share per player at each non-pitcher, non-DH position
position_shares AS (
  SELECT
    f.player_id,
    f.player_name,
    f.season,
    f.team_id,
    f.position,
    f.inn,
    ROUND((f.inn / NULLIF(t.total_inn, 0))::numeric, 4) AS inn_share
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

-- Position player attribution rows
position_player_rows AS (
  SELECT
    ps.team_id,
    ps.season,
    ps.position,
    ps.player_id,
    COALESCE(ps.player_name, b.player_name)              AS player_name,
    ROUND(ps.inn::numeric, 1)                            AS inn,
    ps.inn_share,
    ROUND((ps.inn_share * COALESCE(b.bwpr,  0))::numeric, 1) AS bwpr_attr,
    ROUND((ps.inn_share * COALESCE(b.fwpr,  0))::numeric, 1) AS fwpr_attr,
    ROUND((ps.inn_share * COALESCE(b.brwpr, 0))::numeric, 1) AS brwpr_attr,
    ROUND((ps.inn_share * COALESCE(b.wpr,   0))::numeric, 1) AS wpr_attr,
    NULL::numeric                                        AS pwpr_attr
  FROM position_shares ps
  LEFT JOIN public.player_batting_seasons b
    ON  ps.player_id = b.player_id
    AND ps.season    = b.season
    AND ps.team_id   = b.team_id
),

-- Total IP per team-season (denominator for pitcher share)
pitcher_ip_totals AS (
  SELECT
    team_id,
    season,
    SUM(ip) AS total_ip
  FROM public.player_pitching_seasons
  WHERE ip IS NOT NULL AND ip > 0 AND team_id IS NOT NULL
  GROUP BY team_id, season
),

-- Pitcher attribution rows (P slot)
pitcher_rows AS (
  SELECT
    p.team_id,
    p.season,
    'P'                                                        AS position,
    p.player_id,
    p.player_name,
    ROUND(COALESCE(p.ip, 0)::numeric, 1)                       AS inn,
    ROUND((COALESCE(p.ip, 0) / NULLIF(t.total_ip, 0))::numeric, 4) AS inn_share,
    NULL::numeric                                              AS bwpr_attr,
    NULL::numeric                                              AS fwpr_attr,
    NULL::numeric                                              AS brwpr_attr,
    NULL::numeric                                              AS wpr_attr,
    p.pwpr                                                     AS pwpr_attr
  FROM public.player_pitching_seasons p
  LEFT JOIN pitcher_ip_totals t
    ON  p.team_id = t.team_id
    AND p.season  = t.season
  WHERE p.pwpr    IS NOT NULL
    AND p.team_id IS NOT NULL
)

SELECT team_id, season, position, player_id, player_name,
       inn, inn_share, bwpr_attr, fwpr_attr, brwpr_attr, wpr_attr, pwpr_attr
FROM position_player_rows
UNION ALL
SELECT team_id, season, position, player_id, player_name,
       inn, inn_share, bwpr_attr, fwpr_attr, brwpr_attr, wpr_attr, pwpr_attr
FROM pitcher_rows;

GRANT SELECT ON public.team_position_wpr_players_season TO anon, authenticated;
