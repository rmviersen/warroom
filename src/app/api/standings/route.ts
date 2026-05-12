import { NextResponse } from 'next/server';

import { mlbFetch } from '@/lib/mlb-api';

const STANDINGS_BASE = (year: number) =>
  `/standings?leagueId=103,104&season=${year}&hydrate=team,division`;

export async function GET() {
  try {
    const year = new Date().getFullYear();
    const [regularSeason, wildCard] = await Promise.all([
      mlbFetch(
        `${STANDINGS_BASE(year)}&standingsTypes=regularSeason`,
      ) as Promise<{ records?: unknown[] }>,
      mlbFetch(`${STANDINGS_BASE(year)}&standingsTypes=wildCard`) as Promise<{
        records?: unknown[];
      }>,
    ]);
    return NextResponse.json({
      records: regularSeason.records ?? [],
      wildCard: wildCard.records ?? [],
    });
  } catch {
    return NextResponse.json(
      { error: 'Failed to fetch standings from MLB API' },
      { status: 500 },
    );
  }
}
