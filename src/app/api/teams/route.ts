import { NextResponse } from 'next/server';

import { mlbFetch } from '@/lib/mlb-api';

type MlbDivision = { id?: number; name?: string };
type MlbLeague = { id?: number; name?: string };
type MlbVenue = { name?: string };

type MlbTeamRaw = {
  id: number;
  name?: string;
  abbreviation?: string;
  teamName?: string;
  locationName?: string;
  division?: MlbDivision;
  league?: MlbLeague;
  venue?: MlbVenue | string;
};

function mapTeam(team: MlbTeamRaw) {
  const venue =
    typeof team.venue === 'string'
      ? team.venue
      : team.venue?.name ?? null;

  return {
    id: team.id,
    name: team.name ?? null,
    abbreviation: team.abbreviation ?? null,
    team_name: team.teamName ?? null,
    location_name: team.locationName ?? null,
    division: team.division?.name ?? null,
    division_id: team.division?.id ?? null,
    league: team.league?.name ?? null,
    league_id: team.league?.id ?? null,
    venue,
  };
}

export async function GET() {
  try {
    const data = (await mlbFetch('/teams?sportId=1')) as {
      teams?: MlbTeamRaw[];
    };
    const teams = (data.teams ?? []).map(mapTeam);
    return NextResponse.json({ teams });
  } catch {
    return NextResponse.json(
      { error: 'Failed to fetch teams from MLB API' },
      { status: 500 },
    );
  }
}
