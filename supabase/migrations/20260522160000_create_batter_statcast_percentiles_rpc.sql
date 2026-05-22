-- RPC: percentile-style Statcast batting metrics vs qualified season population (PA floor from team games).

CREATE OR REPLACE FUNCTION public.get_batter_statcast_percentiles(
  p_player_id BIGINT,
  p_season INTEGER
)
RETURNS JSON
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
BEGIN
  RETURN (
    WITH
    max_team_games AS (
      SELECT COALESCE(NULLIF(MAX(team_games), 0), 162)::INTEGER AS mx
      FROM (
        SELECT COUNT(*)::INTEGER AS team_games
        FROM game_logs gl
        WHERE EXTRACT(YEAR FROM gl.game_date)::INTEGER = p_season
          AND gl.status = 'Final'
        GROUP BY gl.home_team_id
      ) t
    ),
    params AS (
      SELECT GREATEST(10, 3 * mx)::INTEGER AS min_pa
      FROM max_team_games
    ),
    qualified AS (
      SELECT sb.*
      FROM statcast_batting sb
      CROSS JOIN params p
      WHERE sb.season = p_season
        AND sb.pa >= p.min_pa
    ),
    pop AS (
      SELECT COUNT(*)::INTEGER AS n FROM qualified
    ),
    tgt AS (
      SELECT sb.*
      FROM statcast_batting sb
      WHERE sb.player_id = p_player_id
        AND sb.season = p_season
      LIMIT 1
    )
    SELECT json_build_object(
      'player_id', p_player_id,
      'season', p_season,
      'qualifies', COALESCE(tg.pa >= pr.min_pa, false),
      'min_pa_required', pr.min_pa,
      'player_pa', tg.pa,
      'population_size', po.n,
      'metrics',
        CASE
          WHEN tg.player_id IS NULL THEN NULL::JSON
          ELSE json_build_object(
            'avg_exit_velocity',
            json_build_object(
              'raw', tg.avg_exit_velocity,
              'percentile', (
                SELECT ROUND(
                  (
                    100.0
                    * COUNT(*) FILTER (
                        WHERE q.avg_exit_velocity IS NOT NULL
                          AND tg.avg_exit_velocity IS NOT NULL
                          AND q.avg_exit_velocity <= tg.avg_exit_velocity
                      )::numeric
                    / NULLIF(
                        COUNT(*) FILTER (WHERE q.avg_exit_velocity IS NOT NULL),
                        0
                      )
                  )::numeric,
                  1
                )
                FROM qualified q
              ),
              'qualifies', tg.avg_exit_velocity IS NOT NULL
            ),
            'barrel_rate',
            json_build_object(
              'raw', tg.barrel_rate,
              'percentile', (
                SELECT ROUND(
                  (
                    100.0
                    * COUNT(*) FILTER (
                        WHERE q.barrel_rate IS NOT NULL
                          AND tg.barrel_rate IS NOT NULL
                          AND q.barrel_rate <= tg.barrel_rate
                      )::numeric
                    / NULLIF(COUNT(*) FILTER (WHERE q.barrel_rate IS NOT NULL), 0)
                  )::numeric,
                  1
                )
                FROM qualified q
              ),
              'qualifies', tg.barrel_rate IS NOT NULL
            ),
            'hard_hit_rate',
            json_build_object(
              'raw', tg.hard_hit_rate,
              'percentile', (
                SELECT ROUND(
                  (
                    100.0
                    * COUNT(*) FILTER (
                        WHERE q.hard_hit_rate IS NOT NULL
                          AND tg.hard_hit_rate IS NOT NULL
                          AND q.hard_hit_rate <= tg.hard_hit_rate
                      )::numeric
                    / NULLIF(COUNT(*) FILTER (WHERE q.hard_hit_rate IS NOT NULL), 0)
                  )::numeric,
                  1
                )
                FROM qualified q
              ),
              'qualifies', tg.hard_hit_rate IS NOT NULL
            ),
            'avg_launch_angle',
            json_build_object(
              'raw', tg.avg_launch_angle,
              'percentile', (
                SELECT ROUND(
                  (
                    100.0
                    * COUNT(*) FILTER (
                        WHERE q.avg_launch_angle IS NOT NULL
                          AND tg.avg_launch_angle IS NOT NULL
                          AND q.avg_launch_angle <= tg.avg_launch_angle
                      )::numeric
                    / NULLIF(
                        COUNT(*) FILTER (WHERE q.avg_launch_angle IS NOT NULL),
                        0
                      )
                  )::numeric,
                  1
                )
                FROM qualified q
              ),
              'qualifies', tg.avg_launch_angle IS NOT NULL
            ),
            'xwoba',
            json_build_object(
              'raw', tg.xwoba,
              'percentile', (
                SELECT ROUND(
                  (
                    100.0
                    * COUNT(*) FILTER (
                        WHERE q.xwoba IS NOT NULL
                          AND tg.xwoba IS NOT NULL
                          AND q.xwoba <= tg.xwoba
                      )::numeric
                    / NULLIF(COUNT(*) FILTER (WHERE q.xwoba IS NOT NULL), 0)
                  )::numeric,
                  1
                )
                FROM qualified q
              ),
              'qualifies', tg.xwoba IS NOT NULL
            ),
            'sprint_speed',
            json_build_object(
              'raw', tg.sprint_speed,
              'percentile', (
                SELECT ROUND(
                  (
                    100.0
                    * COUNT(*) FILTER (
                        WHERE q.sprint_speed IS NOT NULL
                          AND tg.sprint_speed IS NOT NULL
                          AND q.sprint_speed <= tg.sprint_speed
                      )::numeric
                    / NULLIF(COUNT(*) FILTER (WHERE q.sprint_speed IS NOT NULL), 0)
                  )::numeric,
                  1
                )
                FROM qualified q
              ),
              'qualifies', tg.sprint_speed IS NOT NULL
            ),
            'cqi',
            json_build_object(
              'raw', tg.cqi,
              'percentile', (
                SELECT ROUND(
                  (
                    100.0
                    * COUNT(*) FILTER (
                        WHERE q.cqi IS NOT NULL
                          AND tg.cqi IS NOT NULL
                          AND q.cqi <= tg.cqi
                      )::numeric
                    / NULLIF(COUNT(*) FILTER (WHERE q.cqi IS NOT NULL), 0)
                  )::numeric,
                  1
                )
                FROM qualified q
              ),
              'qualifies', tg.cqi IS NOT NULL
            )
          )
        END
    )
    FROM params pr
    CROSS JOIN pop po
    LEFT JOIN tgt tg ON true
  );
END;
$function$;

GRANT EXECUTE ON FUNCTION public.get_batter_statcast_percentiles(BIGINT, INTEGER)
  TO anon, authenticated;
