import { NextResponse } from "next/server";

import { mlbFetch } from "@/lib/mlb-api";
import { parseMlbPlayerSeasonStats } from "@/lib/mlb-player-stats";
import { supabase } from "@/lib/supabase";
import type {
  PlayerProfileApiResponse,
  StatcastBatting,
  PlayerRow,
  PlayerBattingSeasonRow,
  PlayerPitchingSeasonRow,
  PlayerFieldingSeasonRow,
} from "@/types";

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

function mapPlayersRow(row: Record<string, unknown>): PlayerRow {
  return {
    id: toNum(row.id) ?? 0,
    full_name: row.full_name == null ? "" : String(row.full_name),
    team: row.team == null ? null : String(row.team),
    team_id: toNum(row.team_id),
    position: row.position == null ? null : String(row.position),
    jersey_number:
      row.jersey_number == null ? null : String(row.jersey_number),
    bats: row.bats == null ? null : String(row.bats),
    throws: row.throws == null ? null : String(row.throws),
    birth_date: row.birth_date == null ? null : String(row.birth_date),
    debut_date: row.debut_date == null ? null : String(row.debut_date),
    final_game: row.final_game == null ? null : String(row.final_game),
    name_first: row.name_first == null ? null : String(row.name_first),
    name_last: row.name_last == null ? null : String(row.name_last),
    birth_city: row.birth_city == null ? null : String(row.birth_city),
    birth_country:
      row.birth_country == null ? null : String(row.birth_country),
    height: row.height == null ? null : String(row.height),
    weight: toInt(row.weight),
    active:
      row.active === null || row.active === undefined
        ? null
        : Boolean(row.active),
    created_at:
      row.created_at == null ? null : String(row.created_at),
    updated_at:
      row.updated_at == null ? null : String(row.updated_at),
  };
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
    const [
      mlbJson,
      sbResult,
      plResult,
      batHist,
      pitHist,
      fldHist,
    ] = await Promise.all([
      mlbFetch(endpoint) as Promise<{ people?: unknown[] }>,
      supabase
        .from("statcast_batting")
        .select("*")
        .eq("player_id", playerId)
        .eq("season", season)
        .maybeSingle(),
      supabase.from("players").select("*").eq("id", playerId).maybeSingle(),
      supabase
        .from("player_batting_seasons")
        .select("*")
        .eq("player_id", playerId)
        .order("season", { ascending: false }),
      supabase
        .from("player_pitching_seasons")
        .select("*")
        .eq("player_id", playerId)
        .order("season", { ascending: false }),
      supabase
        .from("player_fielding_seasons")
        .select("*")
        .eq("player_id", playerId)
        .order("season", { ascending: false }),
    ]);

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

    if (sbResult.error) {
      console.error("statcast_batting:", sbResult.error.message);
      return NextResponse.json(
        { error: "Failed to load Statcast batting data" },
        { status: 500 },
      );
    }

    if (plResult.error) {
      console.error("players:", plResult.error.message);
    }

    if (batHist.error) {
      console.error("player_batting_seasons:", batHist.error.message);
    }
    if (pitHist.error) {
      console.error("player_pitching_seasons:", pitHist.error.message);
    }
    if (fldHist.error) {
      console.error("player_fielding_seasons:", fldHist.error.message);
    }

    const supabasePlayer = plResult.data
      ? mapPlayersRow(plResult.data as Record<string, unknown>)
      : null;

    const body: PlayerProfileApiResponse = {
      player: person,
      mlbStats,
      statcastBatting: sbResult.data
        ? mapStatcastBattingRow(sbResult.data as Record<string, unknown>)
        : null,
      supabasePlayer,
      historicalBatting: (batHist.data ?? []) as PlayerBattingSeasonRow[],
      historicalPitching: (pitHist.data ?? []) as PlayerPitchingSeasonRow[],
      historicalFielding: (fldHist.data ?? []) as PlayerFieldingSeasonRow[],
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
