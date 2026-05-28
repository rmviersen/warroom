import { NextResponse } from "next/server";

import { supabase } from "@/lib/supabase";
import type { TeamPositionWprApiResponse } from "@/types";

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
    .from("team_position_wpr_ranked")
    .select(
      "position, bwpr, fwpr, brwpr, wpr, pwpr, player_count, bwpr_rank, fwpr_rank, brwpr_rank, wpr_rank, pwpr_rank, team_count",
    )
    .eq("team_id", teamId)
    .eq("season", season);

  if (error) {
    console.error("teams/[id]/position-wpr:", error);
    return NextResponse.json(
      { error: "Could not load position WPR data" },
      { status: 500 },
    );
  }

  const body: TeamPositionWprApiResponse = {
    positions: data ?? [],
    season,
  };

  return NextResponse.json(body);
}
