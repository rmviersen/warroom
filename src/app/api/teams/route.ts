import { NextResponse } from "next/server";

import { mlbFetch } from "@/lib/mlb-api";
import { buildTeamOverviews } from "@/lib/mlb-team-overview";

type MlbTeamRaw = {
  id: number;
  name?: string;
  abbreviation?: string;
  teamName?: string;
  locationName?: string;
  division?: { id?: number; name?: string };
  league?: { id?: number; name?: string };
};

const STANDINGS_PATH = (year: number) =>
  `/standings?leagueId=103,104&season=${year}&hydrate=team,division&standingsTypes=regularSeason`;

const WILDCARD_STANDINGS_PATH = (year: number) =>
  `/standings?leagueId=103,104&season=${year}&hydrate=team,division&standingsTypes=wildCard`;

const TEAM_STATS_PATH = (year: number, group: "hitting" | "pitching") =>
  `/teams/stats?season=${year}&stats=season&group=${group}&sportId=1`;

export async function GET() {
  try {
    const season = new Date().getFullYear();

    const [teamsData, standingsData, wildCardData, hittingStats, pitchingStats] =
      await Promise.all([
        mlbFetch("/teams?sportId=1") as Promise<{ teams?: MlbTeamRaw[] }>,
        mlbFetch(STANDINGS_PATH(season)) as Promise<{ records?: unknown[] }>,
        mlbFetch(WILDCARD_STANDINGS_PATH(season)) as Promise<{
          records?: unknown[];
        }>,
        mlbFetch(TEAM_STATS_PATH(season, "hitting")),
        mlbFetch(TEAM_STATS_PATH(season, "pitching")),
      ]);

    const teams = buildTeamOverviews({
      teams: teamsData.teams ?? [],
      standingsRecords: standingsData.records ?? [],
      wildCardRecords: wildCardData.records ?? [],
      hittingStats,
      pitchingStats,
    });

    return NextResponse.json({ teams, season });
  } catch {
    return NextResponse.json(
      { error: "Failed to fetch teams from MLB API" },
      { status: 500 },
    );
  }
}
