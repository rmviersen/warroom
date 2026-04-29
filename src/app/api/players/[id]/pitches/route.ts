import { NextResponse } from "next/server";

import { supabase } from "@/lib/supabase";
import type { PlayerProfilePitchesApiResponse, StatcastPitch } from "@/types";

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

function mapPitchRow(row: Record<string, unknown>): StatcastPitch {
  return {
    id: toNum(row.id) ?? 0,
    player_id: toNum(row.player_id),
    player_name:
      row.player_name == null ? null : String(row.player_name),
    team_id: toNum(row.team_id),
    game_date: row.game_date == null ? null : String(row.game_date),
    game_pk: toNum(row.game_pk),
    pitch_type:
      row.pitch_type == null ? null : String(row.pitch_type),
    pitch_name:
      row.pitch_name == null ? null : String(row.pitch_name),
    release_speed: toNum(row.release_speed),
    release_spin_rate: toNum(row.release_spin_rate),
    pfx_x: toNum(row.pfx_x),
    pfx_z: toNum(row.pfx_z),
    plate_x: toNum(row.plate_x),
    plate_z: toNum(row.plate_z),
    launch_angle: toNum(row.launch_angle),
    launch_speed: toNum(row.launch_speed),
    hit_distance: toNum(row.hit_distance),
    events: row.events == null ? null : String(row.events),
    description:
      row.description == null ? null : String(row.description),
    zone: toNum(row.zone),
    stand: row.stand == null ? null : String(row.stand),
    p_throws: row.p_throws == null ? null : String(row.p_throws),
    home_team:
      row.home_team == null ? null : String(row.home_team),
    away_team:
      row.away_team == null ? null : String(row.away_team),
    created_at:
      row.created_at == null ? null : String(row.created_at),
  };
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id: idParam } = await context.params;
  const playerId = parsePlayerId(idParam);
  if (playerId == null) {
    return NextResponse.json({ error: "Invalid player id" }, { status: 400 });
  }

  const { searchParams } = new URL(request.url);
  const dateRaw = searchParams.get("date");
  if (dateRaw != null && dateRaw !== "" && !DATE_RE.test(dateRaw)) {
    return NextResponse.json(
      { error: "Invalid date; use YYYY-MM-DD" },
      { status: 400 },
    );
  }

  try {
    let q = supabase
      .from("statcast_pitches")
      .select("*")
      .eq("player_id", playerId)
      .order("created_at", { ascending: false })
      .limit(200);

    if (dateRaw) {
      q = q.eq("game_date", dateRaw);
    }

    const { data, error } = await q;

    if (error) {
      console.error("statcast_pitches:", error.message);
      return NextResponse.json(
        { error: "Failed to load pitch data" },
        { status: 500 },
      );
    }

    const pitches = (data ?? []).map((r) =>
      mapPitchRow(r as Record<string, unknown>),
    );
    const body: PlayerProfilePitchesApiResponse = { pitches };

    return NextResponse.json(body);
  } catch (e) {
    console.error("GET /api/players/[id]/pitches:", e);
    return NextResponse.json(
      { error: "Failed to load pitches" },
      { status: 500 },
    );
  }
}
