-- Partial JSON payloads for ``player_batting_seasons`` / ``player_pitching_seasons``.
-- ON CONFLICT ``COALESCE(EXCLUDED.*, table.*)`` keeps existing values when a key is omitted,
-- so derived-metric scripts can patch rates without nulling counting stats.
--
-- RPC names align with table names: ``upsert_player_batting_seasons``,
-- ``upsert_player_pitching_seasons`` (no prior migration defined these; seed still uses PostgREST upsert).

CREATE OR REPLACE FUNCTION public.upsert_player_batting_seasons(
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
    INSERT INTO public.player_batting_seasons (
      player_id,
      player_name,
      season,
      team_id,
      team,
      league,
      g,
      ab,
      pa,
      r,
      h,
      doubles,
      triples,
      hr,
      rbi,
      sb,
      cs,
      bb,
      so,
      hbp,
      avg,
      obp,
      slg,
      ops,
      babip,
      iso,
      bb_pct,
      k_pct,
      ops_plus,
      woba,
      wrc_plus,
      war,
      cqi,
      updated_at
    )
    VALUES (
      (r->>'player_id')::BIGINT,
      (r->>'player_name')::TEXT,
      (r->>'season')::INTEGER,
      (r->>'team_id')::BIGINT,
      (r->>'team')::TEXT,
      (r->>'league')::TEXT,
      (r->>'g')::INTEGER,
      (r->>'ab')::INTEGER,
      (r->>'pa')::INTEGER,
      (r->>'r')::INTEGER,
      (r->>'h')::INTEGER,
      (r->>'doubles')::INTEGER,
      (r->>'triples')::INTEGER,
      (r->>'hr')::INTEGER,
      (r->>'rbi')::INTEGER,
      (r->>'sb')::INTEGER,
      (r->>'cs')::INTEGER,
      (r->>'bb')::INTEGER,
      (r->>'so')::INTEGER,
      (r->>'hbp')::INTEGER,
      (r->>'avg')::NUMERIC,
      (r->>'obp')::NUMERIC,
      (r->>'slg')::NUMERIC,
      (r->>'ops')::NUMERIC,
      (r->>'babip')::NUMERIC,
      (r->>'iso')::NUMERIC,
      (r->>'bb_pct')::NUMERIC,
      (r->>'k_pct')::NUMERIC,
      (r->>'ops_plus')::INTEGER,
      (r->>'woba')::NUMERIC,
      (r->>'wrc_plus')::INTEGER,
      (r->>'war')::NUMERIC,
      (r->>'cqi')::NUMERIC,
      NOW()
    )
    ON CONFLICT (player_id, season, team_id)
    DO UPDATE SET
      player_name = COALESCE(EXCLUDED.player_name, player_batting_seasons.player_name),
      team = COALESCE(EXCLUDED.team, player_batting_seasons.team),
      league = COALESCE(EXCLUDED.league, player_batting_seasons.league),
      g = COALESCE(EXCLUDED.g, player_batting_seasons.g),
      ab = COALESCE(EXCLUDED.ab, player_batting_seasons.ab),
      pa = COALESCE(EXCLUDED.pa, player_batting_seasons.pa),
      r = COALESCE(EXCLUDED.r, player_batting_seasons.r),
      h = COALESCE(EXCLUDED.h, player_batting_seasons.h),
      doubles = COALESCE(EXCLUDED.doubles, player_batting_seasons.doubles),
      triples = COALESCE(EXCLUDED.triples, player_batting_seasons.triples),
      hr = COALESCE(EXCLUDED.hr, player_batting_seasons.hr),
      rbi = COALESCE(EXCLUDED.rbi, player_batting_seasons.rbi),
      sb = COALESCE(EXCLUDED.sb, player_batting_seasons.sb),
      cs = COALESCE(EXCLUDED.cs, player_batting_seasons.cs),
      bb = COALESCE(EXCLUDED.bb, player_batting_seasons.bb),
      so = COALESCE(EXCLUDED.so, player_batting_seasons.so),
      hbp = COALESCE(EXCLUDED.hbp, player_batting_seasons.hbp),
      avg = COALESCE(EXCLUDED.avg, player_batting_seasons.avg),
      obp = COALESCE(EXCLUDED.obp, player_batting_seasons.obp),
      slg = COALESCE(EXCLUDED.slg, player_batting_seasons.slg),
      ops = COALESCE(EXCLUDED.ops, player_batting_seasons.ops),
      babip = COALESCE(EXCLUDED.babip, player_batting_seasons.babip),
      iso = COALESCE(EXCLUDED.iso, player_batting_seasons.iso),
      bb_pct = COALESCE(EXCLUDED.bb_pct, player_batting_seasons.bb_pct),
      k_pct = COALESCE(EXCLUDED.k_pct, player_batting_seasons.k_pct),
      ops_plus = COALESCE(EXCLUDED.ops_plus, player_batting_seasons.ops_plus),
      woba = COALESCE(EXCLUDED.woba, player_batting_seasons.woba),
      wrc_plus = COALESCE(EXCLUDED.wrc_plus, player_batting_seasons.wrc_plus),
      war = COALESCE(EXCLUDED.war, player_batting_seasons.war),
      cqi = COALESCE(EXCLUDED.cqi, player_batting_seasons.cqi),
      updated_at = NOW();
  END LOOP;
END;
$$;

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
      war,
      lob_pct,
      stuff_plus,
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
      (r->>'war')::NUMERIC,
      (r->>'lob_pct')::NUMERIC,
      (r->>'stuff_plus')::NUMERIC,
      NOW()
    )
    ON CONFLICT (player_id, season, team_id)
    DO UPDATE SET
      player_name = COALESCE(EXCLUDED.player_name, player_pitching_seasons.player_name),
      team = COALESCE(EXCLUDED.team, player_pitching_seasons.team),
      league = COALESCE(EXCLUDED.league, player_pitching_seasons.league),
      w = COALESCE(EXCLUDED.w, player_pitching_seasons.w),
      l = COALESCE(EXCLUDED.l, player_pitching_seasons.l),
      era = COALESCE(EXCLUDED.era, player_pitching_seasons.era),
      g = COALESCE(EXCLUDED.g, player_pitching_seasons.g),
      gs = COALESCE(EXCLUDED.gs, player_pitching_seasons.gs),
      cg = COALESCE(EXCLUDED.cg, player_pitching_seasons.cg),
      sho = COALESCE(EXCLUDED.sho, player_pitching_seasons.sho),
      sv = COALESCE(EXCLUDED.sv, player_pitching_seasons.sv),
      ip = COALESCE(EXCLUDED.ip, player_pitching_seasons.ip),
      h = COALESCE(EXCLUDED.h, player_pitching_seasons.h),
      r = COALESCE(EXCLUDED.r, player_pitching_seasons.r),
      er = COALESCE(EXCLUDED.er, player_pitching_seasons.er),
      hr = COALESCE(EXCLUDED.hr, player_pitching_seasons.hr),
      bb = COALESCE(EXCLUDED.bb, player_pitching_seasons.bb),
      so = COALESCE(EXCLUDED.so, player_pitching_seasons.so),
      whip = COALESCE(EXCLUDED.whip, player_pitching_seasons.whip),
      fip = COALESCE(EXCLUDED.fip, player_pitching_seasons.fip),
      xfip = COALESCE(EXCLUDED.xfip, player_pitching_seasons.xfip),
      k_per_9 = COALESCE(EXCLUDED.k_per_9, player_pitching_seasons.k_per_9),
      bb_per_9 = COALESCE(EXCLUDED.bb_per_9, player_pitching_seasons.bb_per_9),
      hr_per_9 = COALESCE(EXCLUDED.hr_per_9, player_pitching_seasons.hr_per_9),
      k_bb = COALESCE(EXCLUDED.k_bb, player_pitching_seasons.k_bb),
      era_plus = COALESCE(EXCLUDED.era_plus, player_pitching_seasons.era_plus),
      war = COALESCE(EXCLUDED.war, player_pitching_seasons.war),
      lob_pct = COALESCE(EXCLUDED.lob_pct, player_pitching_seasons.lob_pct),
      stuff_plus = COALESCE(EXCLUDED.stuff_plus, player_pitching_seasons.stuff_plus),
      updated_at = NOW();
  END LOOP;
END;
$$;
