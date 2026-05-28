import { NextResponse } from "next/server";

import { supabase } from "@/lib/supabase";
import type { TeamPositionWprPlayersApiResponse } from "@/types";

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

  const { data, error } = await supabase
    .from("team_position_wpr_players_season")
    .select(
      "position, player_id, player_name, inn, inn_share, bwpr_attr, fwpr_attr, brwpr_attr, wpr_attr, pwpr_attr",
    )
    .eq("team_id", teamId)
    .eq("season", season)
    .order("position")
    .order("inn", { ascending: false });

  if (error) {
    console.error("teams/[id]/position-wpr/players:", error);
    return NextResponse.json(
      { error: "Could not load position WPR player breakdown" },
      { status: 500 },
    );
  }

  const body: TeamPositionWprPlayersApiResponse = {
    players: data ?? [],
    season,
  };

  return NextResponse.json(body);
}
