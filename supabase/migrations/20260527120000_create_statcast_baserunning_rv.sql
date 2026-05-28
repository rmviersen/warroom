-- ---------------------------------------------------------------------------
-- statcast_baserunning_rv
-- ---------------------------------------------------------------------------
-- Stores per-player-season Statcast baserunning run values from the
-- Baseball Savant baserunning-run-value leaderboard (2016+).
--
-- runner_runs_tot  = total baserunning run value (stolen bases + extra bases).
--                   Used directly as the runs input to brWPR for 2016+ seasons,
--                   replacing the wSB + sprint-speed-proxy approach.
-- runner_runs_xb   = extra-bases-taken component only (advancing on hits,
--                   tagging up on flies, etc.) — not available from any
--                   counting-stat source.
-- runner_runs_sbx  = stolen-base component (more precise than wSB formula;
--                   accounts for leverage/game situation).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.statcast_baserunning_rv (
    id                              BIGSERIAL       PRIMARY KEY,
    player_id                       BIGINT          NOT NULL,
    player_name                     TEXT,
    team                            TEXT,
    season                          INTEGER         NOT NULL,

    -- Core run-value metrics
    runner_runs_tot                 NUMERIC(8, 4),   -- total: SB + XB combined
    runner_runs_xb                  NUMERIC(8, 4),   -- extra-bases component
    runner_runs_sbx                 NUMERIC(8, 4),   -- stolen-base component
    runner_runs_sb2                 NUMERIC(8, 4),   -- SB2 run value
    runner_runs_sb3                 NUMERIC(8, 4),   -- SB3 run value

    -- Extra-base sub-components (for display / deeper analytics)
    runner_runs_xb_swipe            NUMERIC(8, 4),   -- aggressive advance value
    runner_runs_xb_snipe            NUMERIC(8, 4),   -- taking extra base on hit
    runner_runs_xb_freeze           NUMERIC(8, 4),   -- avoiding bad outs

    -- Opportunity counts
    n_runner_moved                  INTEGER,         -- total opportunities
    n_runner_moved_xb               INTEGER,         -- extra-base opportunities
    n_runner_moved_sbx              INTEGER,         -- steal attempts
    sb2_count                       INTEGER,         -- raw SB2 count
    sb3_count                       INTEGER,         -- raw SB3 count

    updated_at                      TIMESTAMPTZ     DEFAULT NOW()
);

-- Uniqueness: one row per player per season
CREATE UNIQUE INDEX IF NOT EXISTS statcast_baserunning_rv_player_season_key
    ON public.statcast_baserunning_rv (player_id, season);

CREATE INDEX IF NOT EXISTS idx_statcast_baserunning_rv_player_id
    ON public.statcast_baserunning_rv (player_id);

CREATE INDEX IF NOT EXISTS idx_statcast_baserunning_rv_season
    ON public.statcast_baserunning_rv (season);

-- RLS: public read (matches all other Statcast tables)
ALTER TABLE public.statcast_baserunning_rv ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public can read statcast baserunning rv"
    ON public.statcast_baserunning_rv
    FOR SELECT TO anon, authenticated
    USING (true);
