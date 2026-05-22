CREATE OR REPLACE FUNCTION public.upsert_statcast_pitching_arsenal(
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
    INSERT INTO public.statcast_pitching_arsenal (
      pitcher_id,
      pitcher_name,
      season,
      pitch_type,
      pitch_category,
      pitches,
      usage_rate,
      avg_velo,
      avg_spin_rate,
      avg_h_movement,
      avg_v_movement,
      whiff_rate,
      chase_rate,
      stuff_plus_pitch,
      updated_at
    )
    VALUES (
      (r->>'pitcher_id')::BIGINT,
      (r->>'pitcher_name')::TEXT,
      (r->>'season')::INTEGER,
      (r->>'pitch_type')::TEXT,
      (r->>'pitch_category')::TEXT,
      (r->>'pitches')::INTEGER,
      (r->>'usage_rate')::NUMERIC,
      (r->>'avg_velo')::NUMERIC,
      (r->>'avg_spin_rate')::NUMERIC,
      (r->>'avg_h_movement')::NUMERIC,
      (r->>'avg_v_movement')::NUMERIC,
      (r->>'whiff_rate')::NUMERIC,
      (r->>'chase_rate')::NUMERIC,
      (r->>'stuff_plus_pitch')::NUMERIC,
      NOW()
    )
    ON CONFLICT (pitcher_id, season, pitch_type)
    DO UPDATE SET
      pitcher_name = EXCLUDED.pitcher_name,
      pitch_category = EXCLUDED.pitch_category,
      pitches = EXCLUDED.pitches,
      usage_rate = EXCLUDED.usage_rate,
      avg_velo = EXCLUDED.avg_velo,
      avg_spin_rate = EXCLUDED.avg_spin_rate,
      avg_h_movement = EXCLUDED.avg_h_movement,
      avg_v_movement = EXCLUDED.avg_v_movement,
      whiff_rate = EXCLUDED.whiff_rate,
      chase_rate = EXCLUDED.chase_rate,
      stuff_plus_pitch = EXCLUDED.stuff_plus_pitch,
      updated_at = NOW();
  END LOOP;
END;
$$;
