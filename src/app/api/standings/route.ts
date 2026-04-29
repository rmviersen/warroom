import { NextResponse } from 'next/server';

import { mlbFetch } from '@/lib/mlb-api';

export async function GET() {
  try {
    const year = new Date().getFullYear();
    const data = (await mlbFetch(
      `/standings?leagueId=103,104&season=${year}&standingsTypes=regularSeason&hydrate=team`,
    )) as { records?: unknown[] };
    return NextResponse.json({ records: data.records ?? [] });
  } catch {
    return NextResponse.json(
      { error: 'Failed to fetch standings from MLB API' },
      { status: 500 },
    );
  }
}
