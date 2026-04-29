import { NextResponse } from "next/server";

import { mlbFetch } from "@/lib/mlb-api";
import { parseMlbTeamSeasonStats } from "@/lib/mlb-team-stats";
import type {
  TeamDetailApiResponse,
  TeamRosterPlayer,
  TeamRosterPositionGroup,
} from "@/types";

const POSITION_GROUP_ORDER: Record<TeamRosterPositionGroup, number> = {
  pitchers: 0,
  catchers: 1,
  infielders: 2,
  outfielders: 3,
  dh: 4,
  other: 5,
};

function parseTeamId(raw: string): number | null {
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) return null;
  return n;
}

function positionGroupFromCode(
  code: string | null | undefined,
): TeamRosterPositionGroup {
  if (code == null) return "other";
  const c = String(code).trim();
  switch (c) {
    case "1":
      return "pitchers";
    case "2":
      return "catchers";
    case "3":
    case "4":
    case "5":
    case "6":
      return "infielders";
    case "7":
    case "8":
    case "9":
      return "outfielders";
    case "10":
      return "dh";
    case "O":
      return "outfielders";
    case "I":
      return "infielders";
    default:
      return "other";
  }
}

function mapRosterEntry(raw: unknown): TeamRosterPlayer | null {
  if (!raw || typeof raw !== "object") return null;
  const entry = raw as Record<string, unknown>;
  const person = entry.person as Record<string, unknown> | undefined;
  const pid = person?.id;
  const playerId =
    typeof pid === "number"
      ? pid
      : typeof pid === "string" && /^\d+$/.test(pid)
        ? Number(pid)
        : NaN;
  if (!Number.isFinite(playerId)) return null;

  const pos =
    (entry.position as Record<string, unknown> | undefined) ??
    (person?.primaryPosition as Record<string, unknown> | undefined);
  const code = pos?.code != null ? String(pos.code) : null;
  const abbrev = pos?.abbreviation != null ? String(pos.abbreviation) : null;
  const posName = pos?.name != null ? String(pos.name) : null;

  const bat = person?.batSide as Record<string, unknown> | undefined;
  const pit = person?.pitchHand as Record<string, unknown> | undefined;
  const batCode = bat?.code != null ? String(bat.code) : null;
  const pitCode = pit?.code != null ? String(pit.code) : null;

  const jn = entry.jerseyNumber;
  const jerseyNumber =
    jn == null || jn === ""
      ? null
      : typeof jn === "number"
        ? String(jn)
        : String(jn).trim() || null;

  const fullName =
    person?.fullName != null ? String(person.fullName) : "Unknown";

  return {
    playerId,
    fullName,
    jerseyNumber,
    positionAbbrev: abbrev,
    positionName: posName,
    positionCode: code,
    positionGroup: positionGroupFromCode(code),
    batSide: batCode,
    pitchHand: pitCode,
  };
}


export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id: idParam } = await context.params;
  const teamId = parseTeamId(idParam);
  if (teamId == null) {
    return NextResponse.json({ error: "Invalid team id" }, { status: 400 });
  }

  const season = new Date().getFullYear();

  try {
    const teamEndpoint = `/teams/${teamId}?hydrate=venue,division,league`;
    const rosterEndpoint = `/teams/${teamId}/roster?rosterType=active&hydrate=person,stats`;
    const statsEndpoint = `/teams/${teamId}/stats?stats=season&group=hitting,pitching&season=${season}`;

    const [teamJson, rosterJson] = await Promise.all([
      mlbFetch(teamEndpoint) as Promise<{ teams?: unknown[] }>,
      mlbFetch(rosterEndpoint) as Promise<{ roster?: unknown[] }>,
    ]);

    const teams = teamJson.teams;
    const team =
      Array.isArray(teams) && teams.length > 0
        ? (teams[0] as Record<string, unknown>)
        : null;

    if (!team) {
      return NextResponse.json({ error: "Team not found" }, { status: 404 });
    }

    let statsParsed = null;
    try {
      const statsJson = (await mlbFetch(statsEndpoint)) as {
        stats?: unknown;
      };
      statsParsed = parseMlbTeamSeasonStats(statsJson.stats, season);
    } catch (statsErr) {
      console.warn("GET /api/teams/[id]: team stats unavailable:", statsErr);
    }

    const rosterRaw = rosterJson.roster ?? [];
    const roster: TeamRosterPlayer[] = [];
    for (const row of rosterRaw) {
      const mapped = mapRosterEntry(row);
      if (mapped) roster.push(mapped);
    }

    roster.sort((a, b) => {
      const ga = POSITION_GROUP_ORDER[a.positionGroup];
      const gb = POSITION_GROUP_ORDER[b.positionGroup];
      if (ga !== gb) return ga - gb;
      return a.fullName.localeCompare(b.fullName, undefined, {
        sensitivity: "base",
      });
    });

    const body: TeamDetailApiResponse = {
      team,
      roster,
      stats: statsParsed,
    };

    return NextResponse.json(body);
  } catch (e) {
    console.error("GET /api/teams/[id]:", e);
    return NextResponse.json(
      { error: "Failed to load team from MLB API" },
      { status: 500 },
    );
  }
}
