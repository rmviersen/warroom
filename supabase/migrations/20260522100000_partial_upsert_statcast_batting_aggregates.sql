-- Allow ``upsert_statcast_batting_aggregates`` rows that omit nullable stat columns.
-- Omitting a field inserts NULL into EXCLUDED; COALESCE preserves the existing DB value,
-- enabling CQI-only updates from ``pipeline/calc_batting_metrics.py``.

CREATE OR REPLACE FUNCTION public.upsert_statcast_batting_aggregates(
  rows JSONB
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  r JSONB;
BEGIN
  FOR r IN SELECT * FROM jsonb_array_elements(rows)
  LOOP
    INSERT INTO public.statcast_batting (
      player_id,
      season,
      pa,
      avg_exit_velocity,
      max_exit_velocity,
      avg_launch_angle,
      barrel_rate,
      hard_hit_rate,
      cqi,
      updated_at
    )
    VALUES (
      (r->>'player_id')::BIGINT,
      (r->>'season')::INTEGER,
      (r->>'pa')::INTEGER,
      (r->>'avg_exit_velocity')::NUMERIC,
      (r->>'max_exit_velocity')::NUMERIC,
      (r->>'avg_launch_angle')::NUMERIC,
      (r->>'barrel_rate')::NUMERIC,
      (r->>'hard_hit_rate')::NUMERIC,
      (r->>'cqi')::NUMERIC,
      NOW()
    )
    ON CONFLICT (player_id, season)
    DO UPDATE SET
      pa = COALESCE(EXCLUDED.pa, statcast_batting.pa),
      avg_exit_velocity = COALESCE(EXCLUDED.avg_exit_velocity, statcast_batting.avg_exit_velocity),
      max_exit_velocity = COALESCE(EXCLUDED.max_exit_velocity, statcast_batting.max_exit_velocity),
      avg_launch_angle = COALESCE(EXCLUDED.avg_launch_angle, statcast_batting.avg_launch_angle),
      barrel_rate = COALESCE(EXCLUDED.barrel_rate, statcast_batting.barrel_rate),
      hard_hit_rate = COALESCE(EXCLUDED.hard_hit_rate, statcast_batting.hard_hit_rate),
      cqi = COALESCE(EXCLUDED.cqi, statcast_batting.cqi),
      updated_at = NOW();
  END LOOP;
END;
$$;
