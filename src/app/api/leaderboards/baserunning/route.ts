import { NextResponse } from "next/server";

import { supabase } from "@/lib/supabase";

const DEFAULT_SEASON = 2026;
const DEFAULT_LIMIT = 100;
const MAX_LIMIT = 100;

type BattingSeasonRow = {
  id: number;
  player_id: number;
  team_id: number | null;
  season: number;
  sb: number | null;
  cs: number | null;
  brwpr: number | null;
};

type BaserunningRvRow = {
  player_id: number;
  runner_runs_tot: number | null;
  runner_runs_xb: number | null;
  runner_runs_sbx: number | null;
};

type PlayerRow = {
  id: number;
  full_name: string | null;
};

type TeamRow = {
  id: number;
  abbreviation: string | null;
};

function parseSeason(raw: string | null): number | null {
  if (raw == null || raw === "") return DEFAULT_SEASON;
  const n = parseInt(raw, 10);
  if (!Number.isFinite(n)) return null;
  return n;
}

function parseLimit(raw: string | null): number {
  if (raw == null || raw === "") return DEFAULT_LIMIT;
  const n = parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 1) return DEFAULT_LIMIT;
  return Math.min(n, MAX_LIMIT);
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);

    const season = parseSeason(searchParams.get("season"));
    if (season === null) {
      return NextResponse.json(
        { error: "Invalid season query param" },
        { status: 400 },
      );
    }

    const limit = parseLimit(searchParams.get("limit"));

    const { data: battingRows, error: battingError } = await supabase
      .from("player_batting_seasons")
      .select(
        `
        id,
        player_id,
        team_id,
        season,
        sb,
        cs,
        brwpr
      `,
      )
      .eq("season", season)
      .order("brwpr", { ascending: false, nullsFirst: false })
      .limit(limit);

    if (battingError) {
      console.error("leaderboards baserunning batting:", battingError);
      return NextResponse.json(
        { error: "Could not load baserunning leaderboard" },
        { status: 500 },
      );
    }

    const rows = (battingRows ?? []) as BattingSeasonRow[];
    if (rows.length === 0) {
      return NextResponse.json({ players: [], season });
    }

    const playerIds = [...new Set(rows.map((r) => r.player_id))];
    const teamIds = [
      ...new Set(
        rows
          .map((r) => r.team_id)
          .filter((id): id is number => id != null && Number.isFinite(id)),
      ),
    ];

    const [rvResult, playersResult, teamsResult] = await Promise.all([
      supabase
        .from("statcast_baserunning_rv")
        .select(
          "player_id, runner_runs_tot, runner_runs_xb, runner_runs_sbx",
        )
        .eq("season", season)
        .in("player_id", playerIds),
      supabase.from("players").select("id, full_name").in("id", playerIds),
      teamIds.length > 0
        ? supabase.from("teams").select("id, abbreviation").in("id", teamIds)
        : Promise.resolve({ data: [] as TeamRow[], error: null }),
    ]);

    if (rvResult.error) {
      console.error("leaderboards baserunning rv:", rvResult.error);
      return NextResponse.json(
        { error: "Could not load baserunning leaderboard" },
        { status: 500 },
      );
    }

    if (playersResult.error) {
      console.error("leaderboards baserunning players:", playersResult.error);
      return NextResponse.json(
        { error: "Could not load baserunning leaderboard" },
        { status: 500 },
      );
    }

    if (teamsResult.error) {
      console.error("leaderboards baserunning teams:", teamsResult.error);
    }

    const rvByPlayer = new Map<number, BaserunningRvRow>();
    for (const rv of (rvResult.data ?? []) as BaserunningRvRow[]) {
      rvByPlayer.set(rv.player_id, rv);
    }

    const nameByPlayer = new Map<number, string | null>();
    for (const p of (playersResult.data ?? []) as PlayerRow[]) {
      nameByPlayer.set(p.id, p.full_name);
    }

    const abbrevByTeam = new Map<number, string>();
    for (const t of (teamsResult.data ?? []) as TeamRow[]) {
      const abbr = t.abbreviation?.trim();
      if (abbr) abbrevByTeam.set(t.id, abbr);
    }

    const players = rows.map((row) => {
      const rv = rvByPlayer.get(row.player_id);
      const teamId =
        row.team_id != null && Number.isFinite(row.team_id)
          ? row.team_id
          : null;

      return {
        player_id: row.player_id,
        full_name: nameByPlayer.get(row.player_id) ?? null,
        team_id: teamId,
        team_abbreviation:
          teamId != null ? (abbrevByTeam.get(teamId) ?? null) : null,
        season: row.season,
        sb: row.sb,
        cs: row.cs,
        brwpr: row.brwpr,
        runner_runs_tot: rv?.runner_runs_tot ?? null,
        runner_runs_xb: rv?.runner_runs_xb ?? null,
        runner_runs_sbx: rv?.runner_runs_sbx ?? null,
      };
    });

    return NextResponse.json({ players, season });
  } catch (e) {
    console.error("leaderboards baserunning:", e);
    return NextResponse.json(
      { error: "Unexpected server error" },
      { status: 500 },
    );
  }
}
