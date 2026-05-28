/**
 * GET /api/status
 *
 * Queries every pipeline data source and returns a RAG (Red / Amber / Green)
 * health snapshot.  Uses the public anon key — all checked tables carry a
 * public-read RLS policy.
 *
 * Response is never cached so callers always get a live read.
 */

import { NextResponse } from "next/server";

import { supabase } from "@/lib/supabase";
import type {
  RagStatus,
  StatusApiResponse,
  StatusCategory,
  StatusCheck,
} from "@/types";

const CURRENT_SEASON = new Date().getFullYear();

// ---------------------------------------------------------------------------
// RAG logic helpers
// ---------------------------------------------------------------------------

/** Days between a date string (YYYY-MM-DD) and today. */
function daysAgo(dateStr: string): number {
  const ms = Date.now() - new Date(dateStr).getTime();
  return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)));
}

function dateRag(
  dateStr: string | null,
): { status: RagStatus; detail: string } {
  if (!dateStr) return { status: "red", detail: "No data found" };
  const d = daysAgo(dateStr);
  const age =
    d === 0 ? "today" : d === 1 ? "yesterday" : `${d} days ago`;
  const detail = `Latest: ${dateStr} (${age})`;
  if (d <= 2) return { status: "green", detail };
  if (d <= 5) return { status: "amber", detail };
  return { status: "red", detail };
}

/** Season-coverage check: any rows = green, zero = red. */
function presentRag(
  count: number | null,
  season: number,
): { status: RagStatus; detail: string } {
  if (count === null) return { status: "red", detail: "Query failed" };
  if (count === 0)
    return { status: "red", detail: `No ${season} rows found` };
  return { status: "green", detail: `${count.toLocaleString()} rows` };
}

/** WPR health check: needs a minimum number of non-null rows to be green. */
function wprRag(
  count: number | null,
  greenMin = 100,
): { status: RagStatus; detail: string } {
  if (count === null) return { status: "red", detail: "Query failed" };
  if (count === 0) return { status: "red", detail: "0 rows with value" };
  if (count < greenMin)
    return { status: "amber", detail: `${count} rows with value` };
  return { status: "green", detail: `${count.toLocaleString()} rows with value` };
}

// ---------------------------------------------------------------------------
// Query helpers — each wraps its own error handling
// ---------------------------------------------------------------------------

/** Return the MAX value of a date column (as YYYY-MM-DD string), or null. */
async function queryMaxDate(
  table: string,
  col: string,
): Promise<string | null> {
  try {
    const { data, error } = await supabase
      .from(table)
      .select(col)
      .order(col, { ascending: false })
      .limit(1)
      .maybeSingle();
    if (error || !data) return null;
    const raw = (data as unknown as Record<string, unknown>)[col];
    if (raw == null) return null;
    return String(raw).slice(0, 10); // ensure YYYY-MM-DD
  } catch {
    return null;
  }
}

/** Return row count for a table filtered to a season (with optional IS NOT NULL). */
async function queryCount(
  table: string,
  season: number,
  notNullCol?: string,
): Promise<number | null> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let q: any = supabase
      .from(table)
      .select("*", { count: "exact", head: true })
      .eq("season", season);
    if (notNullCol) {
      q = q.not(notNullCol, "is", null);
    }
    const { count, error } = await q;
    if (error) return null;
    return count ?? null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Main handler
// ---------------------------------------------------------------------------

export async function GET() {
  const season = CURRENT_SEASON;

  // Fire all queries in parallel — fast even with 15 round-trips since they
  // all use indexed lookups / HEAD count requests.
  const [
    pitchDate,
    gameLogDate,
    statcastBattingCount,
    statcastPitchingCount,
    oaaCount,
    runningCount,
    baserunningCount,
    leagueBattingCount,
    leaguePitchingCount,
    leaguePitchTypeCount,
    bwprCount,
    fwprCount,
    brwprCount,
    wprCount,
    pwprCount,
  ] = await Promise.all([
    queryMaxDate("statcast_pitches", "game_date"),
    queryMaxDate("game_logs", "game_date"),
    queryCount("statcast_batting", season),
    queryCount("statcast_pitching", season),
    queryCount("statcast_fielding_oaa", season),
    queryCount("statcast_running", season),
    queryCount("statcast_baserunning_rv", season),
    queryCount("league_batting_averages", season),
    queryCount("league_pitching_averages", season),
    queryCount("league_pitch_type_averages", season),
    queryCount("player_batting_seasons", season, "bwpr"),
    queryCount("player_batting_seasons", season, "fwpr"),
    queryCount("player_batting_seasons", season, "brwpr"),
    queryCount("player_season_wpr_totals", season),
    queryCount("player_pitching_seasons", season, "pwpr"),
  ]);

  function check(
    id: string,
    label: string,
    category: StatusCategory,
    rag: { status: RagStatus; detail: string },
  ): StatusCheck {
    return { id, label, category, ...rag };
  }

  const checks: StatusCheck[] = [
    // ── Pitch ingest (date-based freshness) ─────────────────────────────────
    check("statcast_pitches", "Statcast pitches",    "pitch_ingest", dateRag(pitchDate)),
    check("game_logs",        "Game logs",           "pitch_ingest", dateRag(gameLogDate)),

    // ── Season seeds (has current-season rows?) ──────────────────────────────
    check("statcast_batting",       "Statcast batting",           "season_seeds", presentRag(statcastBattingCount,  season)),
    check("statcast_pitching",      "Statcast pitching",          "season_seeds", presentRag(statcastPitchingCount, season)),
    check("statcast_oaa",           "Statcast OAA (fielding)",    "season_seeds", presentRag(oaaCount,              season)),
    check("statcast_running",       "Sprint speed",               "season_seeds", presentRag(runningCount,          season)),
    check("statcast_baserunning_rv","Baserunning run values",      "season_seeds", presentRag(baserunningCount,      season)),
    check("league_batting_avgs",    "League batting averages",    "season_seeds", presentRag(leagueBattingCount,    season)),
    check("league_pitching_avgs",   "League pitching averages",   "season_seeds", presentRag(leaguePitchingCount,   season)),
    check("league_pitch_type_avgs", "League pitch type averages", "season_seeds", presentRag(leaguePitchTypeCount,  season)),

    // ── WPR health (non-null metric rows for current season) ─────────────────
    check("bwpr",  "bWPR",      "wpr_health", wprRag(bwprCount)),
    check("fwpr",  "fWPR",      "wpr_health", wprRag(fwprCount)),
    check("brwpr", "brWPR",     "wpr_health", wprRag(brwprCount)),
    check("wpr",   "Total WPR", "wpr_health", wprRag(wprCount)),
    check("pwpr",  "pWPR",      "wpr_health", wprRag(pwprCount)),
  ];

  const summary = {
    green: checks.filter((c) => c.status === "green").length,
    amber:  checks.filter((c) => c.status === "amber").length,
    red:    checks.filter((c) => c.status === "red").length,
  };

  const body: StatusApiResponse = {
    checks,
    season,
    generatedAt: new Date().toISOString(),
    summary,
  };

  return NextResponse.json(body, {
    headers: { "Cache-Control": "no-store" },
  });
}
