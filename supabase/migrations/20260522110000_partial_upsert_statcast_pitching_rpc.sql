-- Partial payloads for pitching RPCs (mirrors batting COALESCE pattern).
-- Omitted JSON fields become NULL on INSERT; COALESCE preserves existing row values on UPDATE.

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
      p_throws,
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
      (r->>'p_throws')::TEXT,
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
    ON CONFLICT (pitcher_id, season, pitch_type, p_throws)
    DO UPDATE SET
      pitcher_name = COALESCE(EXCLUDED.pitcher_name, statcast_pitching_arsenal.pitcher_name),
      pitch_category = COALESCE(EXCLUDED.pitch_category, statcast_pitching_arsenal.pitch_category),
      pitches = COALESCE(EXCLUDED.pitches, statcast_pitching_arsenal.pitches),
      usage_rate = COALESCE(EXCLUDED.usage_rate, statcast_pitching_arsenal.usage_rate),
      avg_velo = COALESCE(EXCLUDED.avg_velo, statcast_pitching_arsenal.avg_velo),
      avg_spin_rate = COALESCE(EXCLUDED.avg_spin_rate, statcast_pitching_arsenal.avg_spin_rate),
      avg_h_movement = COALESCE(EXCLUDED.avg_h_movement, statcast_pitching_arsenal.avg_h_movement),
      avg_v_movement = COALESCE(EXCLUDED.avg_v_movement, statcast_pitching_arsenal.avg_v_movement),
      whiff_rate = COALESCE(EXCLUDED.whiff_rate, statcast_pitching_arsenal.whiff_rate),
      chase_rate = COALESCE(EXCLUDED.chase_rate, statcast_pitching_arsenal.chase_rate),
      stuff_plus_pitch = COALESCE(EXCLUDED.stuff_plus_pitch, statcast_pitching_arsenal.stuff_plus_pitch),
      updated_at = NOW();
  END LOOP;
END;
$$;

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
      pitcher_name = COALESCE(EXCLUDED.pitcher_name, statcast_pitching.pitcher_name),
      pitches = COALESCE(EXCLUDED.pitches, statcast_pitching.pitches),
      avg_fastball_velo = COALESCE(EXCLUDED.avg_fastball_velo, statcast_pitching.avg_fastball_velo),
      max_velo = COALESCE(EXCLUDED.max_velo, statcast_pitching.max_velo),
      whiff_rate = COALESCE(EXCLUDED.whiff_rate, statcast_pitching.whiff_rate),
      chase_rate = COALESCE(EXCLUDED.chase_rate, statcast_pitching.chase_rate),
      stuff_plus = COALESCE(EXCLUDED.stuff_plus, statcast_pitching.stuff_plus),
      updated_at = NOW();
  END LOOP;
END;
$$;
