-- Add pitcher_role to player_pitching_seasons and update the upsert RPC.
--
-- Classification rule (computed by calc_pitching_season_metrics.py):
--   gs / g >= 0.5  →  'SP'
--   gs / g <  0.5  →  'RP'
--   g = 0 / null   →  NULL
--
-- This lets every downstream consumer (banner, leaderboards, WPR views) filter
-- or group pitchers by role with a simple .eq("pitcher_role", "SP") call.

ALTER TABLE public.player_pitching_seasons
  ADD COLUMN IF NOT EXISTS pitcher_role TEXT;

-- ── Updated upsert RPC ─────────────────────────────────────────────────────
-- NOTE: war was renamed to pwpr in migration 20260522150000. This RPC uses
-- pwpr throughout — do not reintroduce the war column name.

CREATE OR REPLACE FUNCTION public.upsert_player_pitching_seasons(
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
    INSERT INTO public.player_pitching_seasons (
      player_id,
      player_name,
      season,
      team_id,
      team,
      league,
      w,
      l,
      era,
      g,
      gs,
      cg,
      sho,
      sv,
      ip,
      h,
      r,
      er,
      hr,
      bb,
      so,
      whip,
      fip,
      xfip,
      k_per_9,
      bb_per_9,
      hr_per_9,
      k_bb,
      era_plus,
      pwpr,
      lob_pct,
      stuff_plus,
      pitcher_role,
      updated_at
    )
    VALUES (
      (r->>'player_id')::BIGINT,
      (r->>'player_name')::TEXT,
      (r->>'season')::INTEGER,
      (r->>'team_id')::BIGINT,
      (r->>'team')::TEXT,
      (r->>'league')::TEXT,
      (r->>'w')::INTEGER,
      (r->>'l')::INTEGER,
      (r->>'era')::NUMERIC,
      (r->>'g')::INTEGER,
      (r->>'gs')::INTEGER,
      (r->>'cg')::INTEGER,
      (r->>'sho')::INTEGER,
      (r->>'sv')::INTEGER,
      (r->>'ip')::NUMERIC,
      (r->>'h')::INTEGER,
      (r->>'r')::INTEGER,
      (r->>'er')::INTEGER,
      (r->>'hr')::INTEGER,
      (r->>'bb')::INTEGER,
      (r->>'so')::INTEGER,
      (r->>'whip')::NUMERIC,
      (r->>'fip')::NUMERIC,
      (r->>'xfip')::NUMERIC,
      (r->>'k_per_9')::NUMERIC,
      (r->>'bb_per_9')::NUMERIC,
      (r->>'hr_per_9')::NUMERIC,
      (r->>'k_bb')::NUMERIC,
      (r->>'era_plus')::INTEGER,
      (r->>'pwpr')::NUMERIC,
      (r->>'lob_pct')::NUMERIC,
      (r->>'stuff_plus')::NUMERIC,
      (r->>'pitcher_role')::TEXT,
      NOW()
    )
    ON CONFLICT (player_id, season, team_id)
    DO UPDATE SET
      player_name   = COALESCE(EXCLUDED.player_name,   player_pitching_seasons.player_name),
      team          = COALESCE(EXCLUDED.team,           player_pitching_seasons.team),
      league        = COALESCE(EXCLUDED.league,         player_pitching_seasons.league),
      w             = COALESCE(EXCLUDED.w,              player_pitching_seasons.w),
      l             = COALESCE(EXCLUDED.l,              player_pitching_seasons.l),
      era           = COALESCE(EXCLUDED.era,            player_pitching_seasons.era),
      g             = COALESCE(EXCLUDED.g,              player_pitching_seasons.g),
      gs            = COALESCE(EXCLUDED.gs,             player_pitching_seasons.gs),
      cg            = COALESCE(EXCLUDED.cg,             player_pitching_seasons.cg),
      sho           = COALESCE(EXCLUDED.sho,            player_pitching_seasons.sho),
      sv            = COALESCE(EXCLUDED.sv,             player_pitching_seasons.sv),
      ip            = COALESCE(EXCLUDED.ip,             player_pitching_seasons.ip),
      h             = COALESCE(EXCLUDED.h,              player_pitching_seasons.h),
      r             = COALESCE(EXCLUDED.r,              player_pitching_seasons.r),
      er            = COALESCE(EXCLUDED.er,             player_pitching_seasons.er),
      hr            = COALESCE(EXCLUDED.hr,             player_pitching_seasons.hr),
      bb            = COALESCE(EXCLUDED.bb,             player_pitching_seasons.bb),
      so            = COALESCE(EXCLUDED.so,             player_pitching_seasons.so),
      whip          = COALESCE(EXCLUDED.whip,           player_pitching_seasons.whip),
      fip           = COALESCE(EXCLUDED.fip,            player_pitching_seasons.fip),
      xfip          = COALESCE(EXCLUDED.xfip,           player_pitching_seasons.xfip),
      k_per_9       = COALESCE(EXCLUDED.k_per_9,        player_pitching_seasons.k_per_9),
      bb_per_9      = COALESCE(EXCLUDED.bb_per_9,       player_pitching_seasons.bb_per_9),
      hr_per_9      = COALESCE(EXCLUDED.hr_per_9,       player_pitching_seasons.hr_per_9),
      k_bb          = COALESCE(EXCLUDED.k_bb,           player_pitching_seasons.k_bb),
      era_plus      = COALESCE(EXCLUDED.era_plus,       player_pitching_seasons.era_plus),
      pwpr          = COALESCE(EXCLUDED.pwpr,           player_pitching_seasons.pwpr),
      lob_pct       = COALESCE(EXCLUDED.lob_pct,        player_pitching_seasons.lob_pct),
      stuff_plus    = COALESCE(EXCLUDED.stuff_plus,     player_pitching_seasons.stuff_plus),
      pitcher_role  = COALESCE(EXCLUDED.pitcher_role,   player_pitching_seasons.pitcher_role),
      updated_at    = NOW();
  END LOOP;
END;
$$;
