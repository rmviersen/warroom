-- Team position WPR with MLB-wide rank at each position.
--
-- Wraps team_position_wpr_season with RANK() window functions partitioned by
-- (season, position) so every team row knows its rank vs the other 29 teams.
--
-- bwpr/fwpr/brwpr/wpr ranks are null for the P slot (pitchers have no batting WPR).
-- pwpr_rank is null for all non-P positions.
-- team_count gives the denominator ("3 of 28") to handle data-sparse positions.
--
-- Ordering: higher WPR = rank 1 (best). NULLS LAST so teams with no data
-- fall to the bottom rather than being ranked first.

CREATE OR REPLACE VIEW public.team_position_wpr_ranked AS
SELECT
  team_id,
  season,
  position,
  bwpr,
  fwpr,
  brwpr,
  wpr,
  pwpr,
  player_count,

  CASE WHEN position <> 'P'
    THEN RANK() OVER (PARTITION BY season, position ORDER BY bwpr  DESC NULLS LAST)
  END AS bwpr_rank,

  CASE WHEN position <> 'P'
    THEN RANK() OVER (PARTITION BY season, position ORDER BY fwpr  DESC NULLS LAST)
  END AS fwpr_rank,

  CASE WHEN position <> 'P'
    THEN RANK() OVER (PARTITION BY season, position ORDER BY brwpr DESC NULLS LAST)
  END AS brwpr_rank,

  CASE WHEN position <> 'P'
    THEN RANK() OVER (PARTITION BY season, position ORDER BY wpr   DESC NULLS LAST)
  END AS wpr_rank,

  CASE WHEN position = 'P'
    THEN RANK() OVER (PARTITION BY season, position ORDER BY pwpr  DESC NULLS LAST)
  END AS pwpr_rank,

  COUNT(*) OVER (PARTITION BY season, position) AS team_count

FROM public.team_position_wpr_season;

GRANT SELECT ON public.team_position_wpr_ranked TO anon, authenticated;
