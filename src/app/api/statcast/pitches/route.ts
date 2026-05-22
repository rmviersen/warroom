import { NextResponse } from "next/server";

import { supabase } from "@/lib/supabase";

/** Row from `statcast_pitches` for this endpoint (batter vs pitcher columns). */
type StatcastPitchesApiRow = {
  id: number;
  batter_id: number | null;
  batter_name: string | null;
  pitcher_id: number | null;
  pitcher_name: string | null;
  game_date: string | null;
  game_pk: number | null;
  pitch_type: string | null;
  pitch_name: string | null;
  release_speed: number | null;
  release_spin_rate: number | null;
  pfx_x: number | null;
  pfx_z: number | null;
  plate_x: number | null;
  plate_z: number | null;
  launch_angle: number | null;
  launch_speed: number | null;
  hit_distance: number | null;
  events: string | null;
  description: string | null;
  zone: number | null;
  stand: string | null;
  p_throws: string | null;
  home_team: string | null;
  away_team: string | null;
  created_at: string | null;
};

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const playerIdRaw = searchParams.get("player_id");
    const dateRaw = searchParams.get("date");
    const limitRaw = searchParams.get("limit");

    let limit =
      limitRaw != null && limitRaw !== ""
        ? parseInt(limitRaw, 10)
        : 100;
    if (!Number.isFinite(limit) || limit < 1) limit = 100;
    if (limit > 500) limit = 500;

    let query = supabase
      .from("statcast_pitches")
      .select(
        `
        id,
        batter_id,
        batter_name,
        pitcher_id,
        pitcher_name,
        game_date,
        game_pk,
        pitch_type,
        pitch_name,
        release_speed,
        release_spin_rate,
        pfx_x,
        pfx_z,
        plate_x,
        plate_z,
        launch_angle,
        launch_speed,
        hit_distance,
        events,
        description,
        zone,
        stand,
        p_throws,
        home_team,
        away_team,
        created_at
      `,
      );

    if (playerIdRaw != null && playerIdRaw !== "") {
      const playerId = parseInt(playerIdRaw, 10);
      if (!Number.isFinite(playerId)) {
        return NextResponse.json(
          { error: "Invalid player_id" },
          { status: 400 },
        );
      }
      query = query.eq("batter_id", playerId);
    }

    if (dateRaw != null && dateRaw !== "") {
      const d = dateRaw.trim();
      if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) {
        return NextResponse.json(
          { error: "date must be YYYY-MM-DD" },
          { status: 400 },
        );
      }
      query = query.eq("game_date", d);
    }

    query = query.order("created_at", { ascending: false }).limit(limit);

    const { data, error } = await query;

    if (error) {
      console.error("statcast pitches:", error);
      return NextResponse.json(
        { error: "Could not load pitches" },
        { status: 500 },
      );
    }

    return NextResponse.json({
      pitches: (data ?? []) as StatcastPitchesApiRow[],
    });
  } catch (e) {
    console.error("statcast pitches:", e);
    return NextResponse.json(
      { error: "Unexpected server error" },
      { status: 500 },
    );
  }
}
