import { NextResponse } from "next/server";

import { supabase } from "@/lib/supabase";
import type { TeamPositionWprApiResponse, TeamPositionWprRow } from "@/types";

function parseTeamId(raw: string): number | null {
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) return null;
  return n;
}

function parseSeason(param: string | null): number {
  if (param == null || param === "") return new Date().getFullYear();
  const n = Number(param);
  if (!Number.isFinite(n) || n < 1900 || n > 2100) return new Date().getFullYear();
  return Math.trunc(n);
}

type RawRow = {
  team_id: number | string;
  position: string;
  bwpr: number | null;
  fwpr: number | null;
  brwpr: number | null;
  wpr: number | null;
  pwpr: number | null;
  player_count: number;
};

function sameTeamId(rowTeamId: number | string, targetTeamId: number): boolean {
  return Number(rowTeamId) === targetTeamId;
}

/** Rank all rows by a numeric metric (desc, nulls last). Returns 1-based rank. */
function rankDesc(rows: RawRow[], metric: keyof RawRow): Map<number, number> {
  const ranked = new Map<number, number>();
  const sorted = [...rows]
    .filter((r) => r[metric] != null)
    .sort((a, b) => (b[metric] as number) - (a[metric] as number));
  sorted.forEach((r, i) => ranked.set(Number(r.team_id), i + 1));
  return ranked;
}

/**
 * For each position, compute per-metric ranks across all 30 teams and attach
 * them to the target team's row. Uses team_position_wpr_season (the stable
 * aggregated view) rather than a ranked view, avoiding PostgREST issues with
 * window functions inside view definitions.
 */
function attachRanks(
  allRows: RawRow[],
  targetTeamId: number,
): TeamPositionWprRow[] {
  // Group all rows by position
  const byPosition = new Map<string, RawRow[]>();
  for (const row of allRows) {
    const list = byPosition.get(row.position) ?? [];
    list.push(row);
    byPosition.set(row.position, list);
  }

  const result: TeamPositionWprRow[] = [];

  for (const [position, rows] of byPosition) {
    const teamRow = rows.find((r) => sameTeamId(r.team_id, targetTeamId));
    if (!teamRow) continue;

    const teamCount = rows.length;
    const isPitcher = position === "P";

    const bwpr_rank  = isPitcher  ? null : (rankDesc(rows, "bwpr").get(targetTeamId)  ?? null);
    const fwpr_rank  = isPitcher  ? null : (rankDesc(rows, "fwpr").get(targetTeamId)  ?? null);
    const brwpr_rank = isPitcher  ? null : (rankDesc(rows, "brwpr").get(targetTeamId) ?? null);
    const wpr_rank   = isPitcher  ? null : (rankDesc(rows, "wpr").get(targetTeamId)   ?? null);
    const pwpr_rank  = !isPitcher ? null : (rankDesc(rows, "pwpr").get(targetTeamId)  ?? null);

    result.push({
      position,
      bwpr:       teamRow.bwpr,
      fwpr:       teamRow.fwpr,
      brwpr:      teamRow.brwpr,
      wpr:        teamRow.wpr,
      pwpr:       teamRow.pwpr,
      player_count: teamRow.player_count,
      bwpr_rank,
      fwpr_rank,
      brwpr_rank,
      wpr_rank,
      pwpr_rank,
      team_count: teamCount,
    });
  }

  return result;
}

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id: idParam } = await context.params;
  const teamId = parseTeamId(idParam);
  if (teamId == null) {
    return NextResponse.json({ error: "Invalid team id" }, { status: 400 });
  }

  const { searchParams } = new URL(request.url);
  const season = parseSeason(searchParams.get("season"));

  // Fetch all 30 teams' position data for this season (~270 rows) so we can
  // compute cross-team ranks without a database view using window functions.
  const { data, error } = await supabase
    .from("team_position_wpr_season")
    .select("team_id, position, bwpr, fwpr, brwpr, wpr, pwpr, player_count")
    .eq("season", season);

  if (error) {
    console.error("teams/[id]/position-wpr:", error);
    return NextResponse.json(
      { error: "Could not load position WPR data" },
      { status: 500 },
    );
  }

  const positions = attachRanks((data ?? []) as RawRow[], teamId);

  const body: TeamPositionWprApiResponse = { positions, season };
  return NextResponse.json(body);
}
