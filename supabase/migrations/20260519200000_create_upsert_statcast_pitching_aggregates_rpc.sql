CREATE OR REPLACE FUNCTION public.upsert_statcast_pitching_aggregates(
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
    INSERT INTO public.statcast_pitching (
      pitcher_id,
      pitcher_name,
      season,
      pitches,
      avg_fastball_velo,
      max_velo,
      whiff_rate,
      chase_rate,
      stuff_plus,
      updated_at
    )
    VALUES (
      (r->>'pitcher_id')::BIGINT,
      (r->>'pitcher_name')::TEXT,
      (r->>'season')::INTEGER,
      (r->>'pitches')::INTEGER,
      (r->>'avg_fastball_velo')::NUMERIC,
      (r->>'max_velo')::NUMERIC,
      (r->>'whiff_rate')::NUMERIC,
      (r->>'chase_rate')::NUMERIC,
      (r->>'stuff_plus')::NUMERIC,
      NOW()
    )
    ON CONFLICT (pitcher_id, season)
    DO UPDATE SET
      pitcher_name = EXCLUDED.pitcher_name,
      pitches = EXCLUDED.pitches,
      avg_fastball_velo = EXCLUDED.avg_fastball_velo,
      max_velo = EXCLUDED.max_velo,
      whiff_rate = EXCLUDED.whiff_rate,
      chase_rate = EXCLUDED.chase_rate,
      stuff_plus = EXCLUDED.stuff_plus,
      updated_at = NOW();
  END LOOP;
END;
$$;
