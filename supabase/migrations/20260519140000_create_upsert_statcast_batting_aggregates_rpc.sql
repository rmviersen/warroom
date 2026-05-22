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
      pa = EXCLUDED.pa,
      avg_exit_velocity = EXCLUDED.avg_exit_velocity,
      max_exit_velocity = EXCLUDED.max_exit_velocity,
      avg_launch_angle = EXCLUDED.avg_launch_angle,
      barrel_rate = EXCLUDED.barrel_rate,
      hard_hit_rate = EXCLUDED.hard_hit_rate,
      cqi = EXCLUDED.cqi,
      updated_at = NOW();
  END LOOP;
END;
$$;
