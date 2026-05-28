import { NextResponse } from "next/server";

import { mlbFetch } from "@/lib/mlb-api";
import { parseTeamStandingsDetail } from "@/lib/mlb-standings-detail";
import {
  buildTeamBannerResponse,
  mapDbRows,
} from "@/lib/team-banner-build";
import { supabase } from "@/lib/supabase";
import type { TeamBannerApiResponse } from "@/types";

const STANDINGS_PATH = (year: number) =>
  `/standings?leagueId=103,104&season=${year}&hydrate=team,division&standingsTypes=regularSeason`;

const WILDCARD_STANDINGS_PATH = (year: number) =>
  `/standings?leagueId=103,104&season=${year}&hydrate=team,division&standingsTypes=wildCard`;

const PAGE_SIZE = 1000;

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

async function fetchAllRows(
  table: string,
  season: number,
  select: string,
): Promise<Record<string, unknown>[]> {
  const rows: Record<string, unknown>[] = [];
  let offset = 0;

  while (true) {
    const { data, error } = await supabase
      .from(table)
      .select(select)
      .eq("season", season)
      .range(offset, offset + PAGE_SIZE - 1);

    if (error) {
      throw new Error(`${table}: ${error.message}`);
    }

    const batch = (data ?? []) as unknown as Record<string, unknown>[];
    rows.push(...batch);
    if (batch.length < PAGE_SIZE) break;
    offset += PAGE_SIZE;
  }

  return rows;
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

  try {
    const [
      standingsJson,
      wildCardJson,
      battingRows,
      pitchingRows,
      fieldingRows,
      statcastBattingRows,
      statcastPitchingRows,
      pitcherSeasonRows,
      oaaRows,
      playerTeamRows,
      wprRows,
    ] = await Promise.all([
      mlbFetch(STANDINGS_PATH(season)) as Promise<{ records?: unknown[] }>,
      mlbFetch(WILDCARD_STANDINGS_PATH(season)) as Promise<{
        records?: unknown[];
      }>,
      fetchAllRows(
        "team_batting_seasons",
        season,
        "team_id,avg,obp,slg,ops,r,hr,woba,wrc_plus,iso,pa,bb,so",
      ),
      fetchAllRows(
        "team_pitching_seasons",
        season,
        "team_id,era,whip,r,so,bb,ip,h,fip",
      ),
      fetchAllRows("team_fielding_seasons", season, "team_id,fld_pct,e"),
      fetchAllRows(
        "statcast_batting",
        season,
        "team_id,pa,avg_exit_velocity,max_exit_velocity,avg_launch_angle,barrel_rate,hard_hit_rate,xwoba,sprint_speed,cqi",
      ),
      fetchAllRows(
        "statcast_pitching",
        season,
        "pitcher_id,pitches,stuff_plus",
      ),
      fetchAllRows(
        "player_pitching_seasons",
        season,
        "player_id,team_id,ip,xfip",
      ),
      fetchAllRows("statcast_fielding_oaa", season, "player_id,oaa"),
      fetchAllRows("player_batting_seasons", season, "player_id,team_id"),
      fetchAllRows(
        "team_position_wpr_season",
        season,
        "team_id,position,bwpr,fwpr,brwpr,wpr,pwpr",
      ),
    ]);

    const standings = parseTeamStandingsDetail(
      teamId,
      standingsJson.records ?? [],
      wildCardJson.records ?? [],
    );

    const mapped = mapDbRows({
      batting: battingRows,
      pitching: pitchingRows,
      fielding: fieldingRows,
      statcastBatting: statcastBattingRows,
      statcastPitching: statcastPitchingRows,
      pitcherSeasons: pitcherSeasonRows,
      oaaRows,
      playerTeamRows,
      wprRows,
    });

    const body: TeamBannerApiResponse = buildTeamBannerResponse({
      teamId,
      season,
      standings,
      ...mapped,
    });

    return NextResponse.json(body);
  } catch (e) {
    console.error("GET /api/teams/[id]/banner:", e);
    return NextResponse.json(
      { error: "Failed to load team banner metrics" },
      { status: 500 },
    );
  }
}
