-- Create statcast_running table for Savant sprint speed leaderboard data.
-- One row per (player_id, season). Seeded by pipeline/seed_statcast_running.py (2015+).
-- Consumed by calc_baserunning_season_metrics.py for brWPR sprint-speed component.

CREATE TABLE IF NOT EXISTS public.statcast_running (
  id               BIGSERIAL PRIMARY KEY,
  player_id        BIGINT        NOT NULL,
  player_name      TEXT,
  team_id          BIGINT,
  team             TEXT,
  season           INTEGER       NOT NULL,
  position         TEXT,
  age              INTEGER,
  sprint_speed     NUMERIC(5,2),
  hp_to_1b         NUMERIC(5,3),
  bolts            INTEGER,
  competitive_runs INTEGER,
  bolt_rate        NUMERIC(7,4),
  updated_at       TIMESTAMPTZ   DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS statcast_running_player_season_key
  ON public.statcast_running (player_id, season);

CREATE INDEX IF NOT EXISTS idx_statcast_running_player_id
  ON public.statcast_running (player_id);

CREATE INDEX IF NOT EXISTS idx_statcast_running_season
  ON public.statcast_running (season);

ALTER TABLE public.statcast_running ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public can read statcast running"
  ON public.statcast_running FOR SELECT
  TO anon, authenticated
  USING (true);

COMMENT ON TABLE public.statcast_running IS
  'Per-player per-season Statcast sprint speed leaderboard data (2015+). '
  'Columns: sprint_speed (ft/sec), hp_to_1b (seconds home-to-first), '
  'bolts (elite sprint event count), competitive_runs (opportunities), '
  'bolt_rate (bolts / competitive_runs). '
  'Seeded by seed_statcast_running.py; consumed by calc_baserunning_season_metrics.py.';
