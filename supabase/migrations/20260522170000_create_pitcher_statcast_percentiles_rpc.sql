-- RPC: Statcast pitching percentiles vs IP-qualified seasonal population and arsenal cohorts (>=50 pitches / type-hand).

CREATE OR REPLACE FUNCTION public.get_pitcher_statcast_percentiles(
  p_pitcher_id BIGINT,
  p_season INTEGER
)
RETURNS JSON
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
DECLARE
  v_max_team_games INTEGER;
  v_gs INTEGER;
  v_g INTEGER;
  v_pitcher_ip NUMERIC;
  v_starter_pct NUMERIC;
  v_floor_ip NUMERIC;
  v_pop INTEGER;
BEGIN
  SELECT COALESCE(NULLIF(MAX(team_games), 0), 162)::INTEGER
  INTO v_max_team_games
  FROM (
    SELECT COUNT(*)::INTEGER AS team_games
    FROM game_logs gl
    WHERE EXTRACT(YEAR FROM gl.game_date)::INTEGER = p_season
      AND gl.status = 'Final'
    GROUP BY gl.home_team_id
  ) t;

  SELECT
    pps.gs,
    pps.g,
    pps.ip
  INTO
    v_gs,
    v_g,
    v_pitcher_ip
  FROM player_pitching_seasons pps
  WHERE pps.player_id = p_pitcher_id
    AND pps.season = p_season
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN json_build_object(
      'pitcher_id', p_pitcher_id,
      'season', p_season,
      'qualifies', FALSE,
      'floor_ip', NULL,
      'pitcher_ip', NULL,
      'population_size', 0,
      'overall', NULL,
      'arsenal', '[]'::json
    );
  END IF;

  IF COALESCE(v_g, 0) > 0 THEN
    v_starter_pct := v_gs::NUMERIC / v_g;
  ELSE
    v_starter_pct := 0;
  END IF;

  v_floor_ip := ROUND(
    (v_max_team_games * (0.3 + v_starter_pct * 0.7))::NUMERIC,
    1
  );

  SELECT COUNT(*)::INTEGER
  INTO v_pop
  FROM statcast_pitching sp
  INNER JOIN player_pitching_seasons pps
    ON pps.player_id = sp.pitcher_id
      AND pps.season = sp.season
  WHERE sp.season = p_season
    AND pps.ip IS NOT NULL
    AND pps.ip >= ROUND(
          (
            v_max_team_games
            * (
              0.3
              + (
                CASE
                  WHEN pps.g > 0 THEN pps.gs::NUMERIC / pps.g
                  ELSE 0
                END
              ) * 0.7
            )
          )::NUMERIC,
          1
        );

  IF NOT EXISTS (
    SELECT 1
    FROM statcast_pitching sc
    WHERE sc.pitcher_id = p_pitcher_id
      AND sc.season = p_season
  ) THEN
    RETURN json_build_object(
      'pitcher_id', p_pitcher_id,
      'season', p_season,
      'qualifies', FALSE,
      'floor_ip', v_floor_ip,
      'pitcher_ip', v_pitcher_ip,
      'population_size', v_pop,
      'overall', NULL,
      'arsenal', '[]'::json
    );
  END IF;

  RETURN (
    WITH
    mtx AS (
      SELECT v_max_team_games::INTEGER AS mx
    ),
    joined AS (
      SELECT
        sp.pitcher_id,
        sp.season,
        pps.ip AS p_ip,
        pps.g AS p_g,
        pps.gs AS p_gs,
        ROUND(
          (
            mtx.mx
            * (
              0.3
              + (
                CASE
                  WHEN pps.g > 0 THEN pps.gs::NUMERIC / pps.g
                  ELSE 0
                END
              ) * 0.7
            )
          )::NUMERIC,
          1
        ) AS floor_ip,
        sp.stuff_plus,
        sp.avg_fastball_velo,
        sp.max_velo,
        sp.whiff_rate,
        sp.chase_rate
      FROM statcast_pitching sp
      INNER JOIN player_pitching_seasons pps
        ON pps.player_id = sp.pitcher_id
          AND pps.season = sp.season
      CROSS JOIN mtx
      WHERE sp.season = p_season
    ),
    qualified AS (
      SELECT *
      FROM joined j
      WHERE j.p_ip IS NOT NULL
        AND j.p_ip >= j.floor_ip
    ),
    pop AS (
      SELECT COUNT(*)::INTEGER AS n FROM qualified
    ),
    tgt AS (
      SELECT *
      FROM joined j
      WHERE j.pitcher_id = p_pitcher_id
      LIMIT 1
    ),
    arsenal_rows AS (
      SELECT pa.*
      FROM statcast_pitching_arsenal pa
      WHERE pa.pitcher_id = p_pitcher_id
        AND pa.season = p_season
    )
    SELECT json_build_object(
      'pitcher_id', p_pitcher_id,
      'season', p_season,
      'qualifies',
        COALESCE(v_pitcher_ip >= v_floor_ip, FALSE),
      'floor_ip', v_floor_ip,
      'pitcher_ip', v_pitcher_ip,
      'population_size', po.n,
      'overall',
        json_build_object(
          'stuff_plus',
          json_build_object(
            'raw', tg.stuff_plus,
            'percentile', (
              SELECT ROUND(
                (
                  100.0
                  * COUNT(*) FILTER (
                      WHERE q.stuff_plus IS NOT NULL
                        AND tg.stuff_plus IS NOT NULL
                        AND q.stuff_plus <= tg.stuff_plus
                    )::NUMERIC
                  / NULLIF(COUNT(*) FILTER (WHERE q.stuff_plus IS NOT NULL), 0)
                )::NUMERIC,
                1
              )
              FROM qualified q
            ),
            'qualifies', tg.stuff_plus IS NOT NULL
          ),
          'avg_fastball_velo',
          json_build_object(
            'raw', tg.avg_fastball_velo,
            'percentile', (
              SELECT ROUND(
                (
                  100.0
                  * COUNT(*) FILTER (
                      WHERE q.avg_fastball_velo IS NOT NULL
                        AND tg.avg_fastball_velo IS NOT NULL
                        AND q.avg_fastball_velo <= tg.avg_fastball_velo
                    )::NUMERIC
                  / NULLIF(
                      COUNT(*) FILTER (WHERE q.avg_fastball_velo IS NOT NULL),
                      0
                    )
                )::NUMERIC,
                1
              )
              FROM qualified q
            ),
            'qualifies', tg.avg_fastball_velo IS NOT NULL
          ),
          'max_velo',
          json_build_object(
            'raw', tg.max_velo,
            'percentile', (
              SELECT ROUND(
                (
                  100.0
                  * COUNT(*) FILTER (
                      WHERE q.max_velo IS NOT NULL
                        AND tg.max_velo IS NOT NULL
                        AND q.max_velo <= tg.max_velo
                    )::NUMERIC
                  / NULLIF(COUNT(*) FILTER (WHERE q.max_velo IS NOT NULL), 0)
                )::NUMERIC,
                1
              )
              FROM qualified q
            ),
            'qualifies', tg.max_velo IS NOT NULL
          ),
          'whiff_rate',
          json_build_object(
            'raw', tg.whiff_rate,
            'percentile', (
              SELECT ROUND(
                (
                  100.0
                  * COUNT(*) FILTER (
                      WHERE q.whiff_rate IS NOT NULL
                        AND tg.whiff_rate IS NOT NULL
                        AND q.whiff_rate <= tg.whiff_rate
                    )::NUMERIC
                  / NULLIF(COUNT(*) FILTER (WHERE q.whiff_rate IS NOT NULL), 0)
                )::NUMERIC,
                1
              )
              FROM qualified q
            ),
            'qualifies', tg.whiff_rate IS NOT NULL
          ),
          'chase_rate',
          json_build_object(
            'raw', tg.chase_rate,
            'percentile', (
              SELECT ROUND(
                (
                  100.0
                  * COUNT(*) FILTER (
                      WHERE q.chase_rate IS NOT NULL
                        AND tg.chase_rate IS NOT NULL
                        AND q.chase_rate <= tg.chase_rate
                    )::NUMERIC
                  / NULLIF(COUNT(*) FILTER (WHERE q.chase_rate IS NOT NULL), 0)
                )::NUMERIC,
                1
              )
              FROM qualified q
            ),
            'qualifies', tg.chase_rate IS NOT NULL
          )
        ),
      'arsenal',
        COALESCE(
          (
            SELECT json_agg(s.pkg ORDER BY ar.pitches DESC NULLS LAST)
            FROM arsenal_rows ar
            CROSS JOIN LATERAL (
              SELECT json_build_object(
                  'pitch_type', ar.pitch_type,
                  'p_throws', ar.p_throws,
                  'pitches', ar.pitches,
                  'usage_rate', ar.usage_rate,
                  'qualifies', COALESCE(ar.pitches, 0) >= 50,
                  'population_size', (
                      SELECT COUNT(DISTINCT cohort.pitcher_id)::INTEGER
                      FROM statcast_pitching_arsenal cohort
                      WHERE cohort.season = p_season
                        AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                        AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                        AND cohort.pitches >= 50
                    ),
                  'avg_velo',
                  json_build_object(
                    'raw', ar.avg_velo,
                    'percentile',
                      CASE
                        WHEN (
                          SELECT COUNT(DISTINCT cohort.pitcher_id)
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        ) < 10 THEN NULL
                        ELSE (
                          SELECT ROUND(
                            (
                              100.0
                              * COUNT(*) FILTER (
                                  WHERE cohort.avg_velo IS NOT NULL
                                    AND ar.avg_velo IS NOT NULL
                                    AND cohort.avg_velo <= ar.avg_velo
                                )::NUMERIC
                              / NULLIF(
                                  COUNT(*) FILTER (WHERE cohort.avg_velo IS NOT NULL),
                                  0
                                )
                            )::NUMERIC,
                            1
                          )
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        )
                      END
                  ),
                  'avg_spin_rate',
                  json_build_object(
                    'raw', ar.avg_spin_rate,
                    'percentile',
                      CASE
                        WHEN (
                          SELECT COUNT(DISTINCT cohort.pitcher_id)
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        ) < 10 THEN NULL
                        ELSE (
                          SELECT ROUND(
                            (
                              100.0
                              * COUNT(*) FILTER (
                                  WHERE cohort.avg_spin_rate IS NOT NULL
                                    AND ar.avg_spin_rate IS NOT NULL
                                    AND cohort.avg_spin_rate <= ar.avg_spin_rate
                                )::NUMERIC
                              / NULLIF(
                                  COUNT(*) FILTER (
                                    WHERE cohort.avg_spin_rate IS NOT NULL
                                  ),
                                  0
                                )
                            )::NUMERIC,
                            1
                          )
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        )
                      END
                  ),
                  'avg_h_movement',
                  json_build_object(
                    'raw', ar.avg_h_movement,
                    'percentile',
                      CASE
                        WHEN (
                          SELECT COUNT(DISTINCT cohort.pitcher_id)
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        ) < 10 THEN NULL
                        ELSE (
                          SELECT ROUND(
                            (
                              100.0
                              * COUNT(*) FILTER (
                                  WHERE cohort.avg_h_movement IS NOT NULL
                                    AND ar.avg_h_movement IS NOT NULL
                                    AND cohort.avg_h_movement
                                      <= ar.avg_h_movement
                                )::NUMERIC
                              / NULLIF(
                                  COUNT(*) FILTER (
                                    WHERE cohort.avg_h_movement IS NOT NULL
                                  ),
                                  0
                                )
                            )::NUMERIC,
                            1
                          )
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        )
                      END
                  ),
                  'avg_v_movement',
                  json_build_object(
                    'raw', ar.avg_v_movement,
                    'percentile',
                      CASE
                        WHEN (
                          SELECT COUNT(DISTINCT cohort.pitcher_id)
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        ) < 10 THEN NULL
                        ELSE (
                          SELECT ROUND(
                            (
                              100.0
                              * COUNT(*) FILTER (
                                  WHERE cohort.avg_v_movement IS NOT NULL
                                    AND ar.avg_v_movement IS NOT NULL
                                    AND cohort.avg_v_movement
                                      <= ar.avg_v_movement
                                )::NUMERIC
                              / NULLIF(
                                  COUNT(*) FILTER (
                                    WHERE cohort.avg_v_movement IS NOT NULL
                                  ),
                                  0
                                )
                            )::NUMERIC,
                            1
                          )
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        )
                      END
                  ),
                  'whiff_rate',
                  json_build_object(
                    'raw', ar.whiff_rate,
                    'percentile',
                      CASE
                        WHEN (
                          SELECT COUNT(DISTINCT cohort.pitcher_id)
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        ) < 10 THEN NULL
                        ELSE (
                          SELECT ROUND(
                            (
                              100.0
                              * COUNT(*) FILTER (
                                  WHERE cohort.whiff_rate IS NOT NULL
                                    AND ar.whiff_rate IS NOT NULL
                                    AND cohort.whiff_rate <= ar.whiff_rate
                                )::NUMERIC
                              / NULLIF(
                                  COUNT(*) FILTER (
                                    WHERE cohort.whiff_rate IS NOT NULL
                                  ),
                                  0
                                )
                            )::NUMERIC,
                            1
                          )
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        )
                      END
                  ),
                  'chase_rate',
                  json_build_object(
                    'raw', ar.chase_rate,
                    'percentile',
                      CASE
                        WHEN (
                          SELECT COUNT(DISTINCT cohort.pitcher_id)
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        ) < 10 THEN NULL
                        ELSE (
                          SELECT ROUND(
                            (
                              100.0
                              * COUNT(*) FILTER (
                                  WHERE cohort.chase_rate IS NOT NULL
                                    AND ar.chase_rate IS NOT NULL
                                    AND cohort.chase_rate <= ar.chase_rate
                                )::NUMERIC
                              / NULLIF(
                                  COUNT(*) FILTER (
                                    WHERE cohort.chase_rate IS NOT NULL
                                  ),
                                  0
                                )
                            )::NUMERIC,
                            1
                          )
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        )
                      END
                  ),
                  'stuff_plus_pitch',
                  json_build_object(
                    'raw', ar.stuff_plus_pitch,
                    'percentile',
                      CASE
                        WHEN (
                          SELECT COUNT(DISTINCT cohort.pitcher_id)
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        ) < 10 THEN NULL
                        ELSE (
                          SELECT ROUND(
                            (
                              100.0
                              * COUNT(*) FILTER (
                                  WHERE cohort.stuff_plus_pitch IS NOT NULL
                                    AND ar.stuff_plus_pitch IS NOT NULL
                                    AND cohort.stuff_plus_pitch <= ar.stuff_plus_pitch
                                )::NUMERIC
                              / NULLIF(
                                  COUNT(*) FILTER (
                                    WHERE cohort.stuff_plus_pitch IS NOT NULL
                                  ),
                                  0
                                )
                            )::NUMERIC,
                            1
                          )
                          FROM statcast_pitching_arsenal cohort
                          WHERE cohort.season = p_season
                            AND cohort.pitch_type IS NOT DISTINCT FROM ar.pitch_type
                            AND cohort.p_throws IS NOT DISTINCT FROM ar.p_throws
                            AND cohort.pitches >= 50
                        )
                      END
                  )
              ) AS pkg
            ) s
          ),
          '[]'::json
        )
    )
    FROM pop po
    CROSS JOIN tgt tg
  );
END;
$function$;

GRANT EXECUTE ON FUNCTION public.get_pitcher_statcast_percentiles(BIGINT, INTEGER)
  TO anon, authenticated;
