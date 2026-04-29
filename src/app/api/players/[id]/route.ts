import { NextResponse } from "next/server";

import { mlbFetch } from "@/lib/mlb-api";
import { parseMlbPlayerSeasonStats } from "@/lib/mlb-player-stats";
import { supabase } from "@/lib/supabase";
import type { PlayerProfileApiResponse, StatcastBatting } from "@/types";

function parsePlayerId(raw: string): number | null {
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) return null;
  return n;
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

function mapStatcastBattingRow(row: Record<string, unknown>): StatcastBatting {
  return {
    id: toNum(row.id) ?? 0,
    player_id: toNum(row.player_id),
    player_name:
      row.player_name == null ? null : String(row.player_name),
    team_id: toNum(row.team_id),
    season: toNum(row.season),
    pa: toInt(row.pa),
    avg_exit_velocity: toNum(row.avg_exit_velocity),
    max_exit_velocity: toNum(row.max_exit_velocity),
    avg_launch_angle: toNum(row.avg_launch_angle),
    barrel_rate: toNum(row.barrel_rate),
    hard_hit_rate: toNum(row.hard_hit_rate),
    xba: toNum(row.xba),
    xslg: toNum(row.xslg),
    xwoba: toNum(row.xwoba),
    sprint_speed: toNum(row.sprint_speed),
    updated_at:
      row.updated_at == null ? null : String(row.updated_at),
  };
}

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id: idParam } = await context.params;
  const playerId = parsePlayerId(idParam);
  if (playerId == null) {
    return NextResponse.json({ error: "Invalid player id" }, { status: 400 });
  }

  const season = new Date().getFullYear();

  try {
    const endpoint = `/people/${playerId}?hydrate=stats(group=[hitting,pitching,fielding],type=[season]),currentTeam`;
    const mlbJson = (await mlbFetch(endpoint)) as { people?: unknown[] };

    const people = mlbJson.people;
    const person =
      Array.isArray(people) && people.length > 0
        ? (people[0] as Record<string, unknown>)
        : null;

    if (!person) {
      return NextResponse.json(
        { error: "Player not found" },
        { status: 404 },
      );
    }

    const primaryPosition = person.primaryPosition as
      | { code?: string }
      | undefined;
    const primaryPositionCode = primaryPosition?.code;

    const mlbStats = parseMlbPlayerSeasonStats(
      person.stats,
      season,
      primaryPositionCode,
    );

    const { data: sbRow, error: sbError } = await supabase
      .from("statcast_batting")
      .select("*")
      .eq("player_id", playerId)
      .eq("season", season)
      .maybeSingle();

    if (sbError) {
      console.error("statcast_batting:", sbError.message);
      return NextResponse.json(
        { error: "Failed to load Statcast batting data" },
        { status: 500 },
      );
    }

    const body: PlayerProfileApiResponse = {
      player: person,
      mlbStats,
      statcastBatting: sbRow
        ? mapStatcastBattingRow(sbRow as Record<string, unknown>)
        : null,
    };

    return NextResponse.json(body);
  } catch (e) {
    console.error("GET /api/players/[id]:", e);
    return NextResponse.json(
      { error: "Failed to load player profile" },
      { status: 500 },
    );
  }
}
