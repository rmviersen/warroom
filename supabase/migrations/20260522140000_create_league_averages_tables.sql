-- Season-level league batting / pitching rate bundles (canonical warehouse lines).

CREATE TABLE public.league_batting_averages (
  season INTEGER PRIMARY KEY,
  lg_pa BIGINT,
  lg_ab BIGINT,
  lg_h BIGINT,
  lg_2b BIGINT,
  lg_3b BIGINT,
  lg_hr BIGINT,
  lg_r BIGINT,
  lg_bb BIGINT,
  lg_so BIGINT,
  lg_hbp BIGINT,
  lg_avg NUMERIC(6, 4),
  lg_obp NUMERIC(6, 4),
  lg_slg NUMERIC(6, 4),
  lg_ops NUMERIC(6, 4),
  lg_woba NUMERIC(6, 4),
  lg_iso NUMERIC(6, 4),
  lg_babip NUMERIC(6, 4),
  lg_bb_pct NUMERIC(6, 4),
  lg_k_pct NUMERIC(6, 4),
  lg_runs_per_pa NUMERIC(8, 6),
  lg_wrc_per_pa NUMERIC(8, 6),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.league_batting_averages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public can read league batting averages"
  ON public.league_batting_averages FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE TABLE public.league_pitching_averages (
  season INTEGER PRIMARY KEY,
  lg_ip NUMERIC(10, 1),
  lg_er BIGINT,
  lg_hr BIGINT,
  lg_bb BIGINT,
  lg_so BIGINT,
  lg_h BIGINT,
  lg_era NUMERIC(6, 3),
  lg_fip NUMERIC(6, 3),
  lg_whip NUMERIC(6, 3),
  lg_k_per_9 NUMERIC(6, 3),
  lg_bb_per_9 NUMERIC(6, 3),
  lg_hr_per_9 NUMERIC(6, 3),
  fip_constant NUMERIC(6, 3),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.league_pitching_averages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public can read league pitching averages"
  ON public.league_pitching_averages FOR SELECT
  TO anon, authenticated
  USING (true);
