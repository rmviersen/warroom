import { NextResponse } from 'next/server';

import { mlbFetch } from '@/lib/mlb-api';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const teamId = searchParams.get('teamId');
  const search = searchParams.get('search');

  if (!teamId && !search) {
    return NextResponse.json(
      { error: 'Provide teamId or search query parameter' },
      { status: 400 },
    );
  }

  try {
    if (teamId) {
      const data = (await mlbFetch(
        `/teams/${encodeURIComponent(teamId)}/roster?rosterType=active`,
      )) as { roster?: unknown[] };
      return NextResponse.json({ roster: data.roster ?? [] });
    }

    const data = (await mlbFetch(
      `/people/search?names=${encodeURIComponent(search!)}&hydrate=currentTeam,team`,
    )) as { people?: unknown[] };
    return NextResponse.json({ players: data.people ?? [] });
  } catch {
    return NextResponse.json(
      { error: 'Failed to fetch players from MLB API' },
      { status: 500 },
    );
  }
}
