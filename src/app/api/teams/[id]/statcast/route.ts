import { NextResponse } from "next/server";

import { supabase } from "@/lib/supabase";
import type {
  StatcastBatting,
  TeamStatcastAggregates,
  TeamStatcastApiResponse,
  TeamStatcastTopPlayer,
} from "@/types";

function parseTeamId(raw: string): number | null {
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) return null;
  return n;
}

function parseSeason(param: string | null): number | null {
  if (param == null || param === "") return new Date().getFullYear();
  const n = Number(param);
  if (!Number.isFinite(n) || n < 1900 || n > 2100) return null;
  return Math.trunc(n);
}

function toNum(v: unknown): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function toInt(v: unknown): number | null {
  const n = toNum(v);
  if (n == null) return null;
  const i = Math.trunc(n);
  return i >= 0 ? i : null;
}

function mapRow(r: Record<string, unknown>): StatcastBatting {
  return {
    id: toNum(r.id) ?? 0,
    player_id: toNum(r.player_id),
    player_name:
      r.player_name == null ? null : String(r.player_name),
    team_id: toNum(r.team_id),
    season: toNum(r.season),
    pa: toInt(r.pa),
    avg_exit_velocity: toNum(r.avg_exit_velocity),
    max_exit_velocity: toNum(r.max_exit_velocity),
    avg_launch_angle: toNum(r.avg_launch_angle),
    barrel_rate: toNum(r.barrel_rate),
    hard_hit_rate: toNum(r.hard_hit_rate),
    xba: toNum(r.xba),
    xslg: toNum(r.xslg),
    xwoba: toNum(r.xwoba),
    sprint_speed: toNum(r.sprint_speed),
    updated_at:
      r.updated_at == null ? null : String(r.updated_at),
  };
}

/**
 * ``sum(metric × pa) / sum(pa)`` for rows with pa > 0 and a finite metric.
 * If no qualifying weights, falls back to a simple mean over players with a
 * non-null metric.
 */
function weightedOrSimple(
  list: StatcastBatting[],
  getMetric: (r: StatcastBatting) => number | null,
): number | null {
  let numerator = 0;
  let denom = 0;
  const unweighted: number[] = [];

  for (const r of list) {
    const m = getMetric(r);
    if (m == null || !Number.isFinite(m)) continue;
    const pa = r.pa;
    if (pa != null && pa > 0 && Number.isFinite(pa)) {
      numerator += m * pa;
      denom += pa;
    } else {
      unweighted.push(m);
    }
  }

  if (denom > 0) return numerator / denom;
  if (unweighted.length > 0) {
    return unweighted.reduce((a, b) => a + b, 0) / unweighted.length;
  }
  return null;
}

function maxOfMetrics(list: StatcastBatting[]): number | null {
  const vals = list
    .map((r) => r.max_exit_velocity)
    .filter((v): v is number => v != null && Number.isFinite(v));
  if (vals.length === 0) return null;
  return Math.max(...vals);
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
  if (season == null) {
    return NextResponse.json(
      { error: "Invalid season; use a four-digit year" },
      { status: 400 },
    );
  }

  try {
    const { data: rows, error } = await supabase
      .from("statcast_batting")
      .select("*")
      .eq("team_id", teamId)
      .eq("season", season);

    if (error) {
      console.error("statcast_batting (team):", error.message);
      return NextResponse.json(
        { error: "Failed to load Statcast team data" },
        { status: 500 },
      );
    }

    const list = (rows ?? []).map((r) =>
      mapRow(r as Record<string, unknown>),
    );
    const playerCount = list.length;

    if (playerCount === 0) {
      const body: TeamStatcastApiResponse = {
        teamStatcast: null,
        topPlayers: [],
        playerCount: 0,
      };
      return NextResponse.json(body);
    }

    const total_pa = list.reduce((sum, r) => {
      const pa = r.pa;
      if (pa != null && pa > 0 && Number.isFinite(pa)) return sum + pa;
      return sum;
    }, 0);

    const teamStatcast: TeamStatcastAggregates = {
      season,
      total_pa,
      avg_exit_velocity: weightedOrSimple(list, (r) => r.avg_exit_velocity),
      max_exit_velocity: maxOfMetrics(list),
      avg_launch_angle: weightedOrSimple(list, (r) => r.avg_launch_angle),
      barrel_rate: weightedOrSimple(list, (r) => r.barrel_rate),
      hard_hit_rate: weightedOrSimple(list, (r) => r.hard_hit_rate),
      avg_xwoba: weightedOrSimple(list, (r) => r.xwoba),
      avg_sprint_speed: weightedOrSimple(list, (r) => r.sprint_speed),
    };

    const withEv = [...list].filter(
      (r) =>
        r.player_id != null &&
        r.avg_exit_velocity != null &&
        Number.isFinite(r.avg_exit_velocity),
    );
    withEv.sort(
      (a, b) => (b.avg_exit_velocity ?? 0) - (a.avg_exit_velocity ?? 0),
    );
    const topPlayers: TeamStatcastTopPlayer[] = withEv.slice(0, 5).map((r) => ({
      player_id: r.player_id as number,
      player_name: r.player_name,
      pa: r.pa,
      avg_exit_velocity: r.avg_exit_velocity,
      barrel_rate: r.barrel_rate,
      xwoba: r.xwoba,
    }));

    const body: TeamStatcastApiResponse = {
      teamStatcast,
      topPlayers,
      playerCount,
    };
    return NextResponse.json(body);
  } catch (e) {
    console.error("GET /api/teams/[id]/statcast:", e);
    return NextResponse.json(
      { error: "Failed to load team Statcast data" },
      { status: 500 },
    );
  }
}
